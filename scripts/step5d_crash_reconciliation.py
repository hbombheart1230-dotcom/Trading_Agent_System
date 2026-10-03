"""P0-B (restart-safety hardening, 2026-09-17) -- Step5D crash reconciliation.

Detects orphaned `physical_order_claim` leases (Step5C's fail-closed guard,
`libs/supervisor/intent_state_store.py::claim_physical_order`) left behind by
a process crash between "CAS claim won" and "execution result persisted",
and provides an explicit, audited, operator-confirmed resolution path.

WHY THIS IS MANUAL_REQUIRED, NOT AUTOMATIC (read this before "fixing" it):

Automatic reconciliation would need to (a) recover WHAT the orphaned claim's
underlying order actually was (symbol/side/qty/price), then (b) match that
against real broker order/fill evidence (the `account.orders` skill, kt00007)
to determine ACCEPTED vs. NOT_SENT, then (c) transition the SQLite row
accordingly with no human in the loop.

Step (a) is not safely possible today: `physical_order_claim` stores only the
one-way SHA-256 hash of the order content
(`libs/execution/intent_identity.py::physical_order_fingerprint`) -- the hash
cannot be reversed, and neither `claim_execution` nor `admit_intent` persist
the human-readable order fields into `intent_journal.meta_json` (verified
directly: both write `'{}'`/`{"source": ...}` only, never symbol/qty/price).
The only place that content might still exist is `data/logs/events.jsonl`
(size ~953 MB at last check, unbounded, no index), which is not a reliable
correlation source for an automated tool (a crash can lose the very log line
that would have proven the match, and the file is not indexed by
physical_order_key or intent_id).

Given that, an automatic "assume it probably went through" or "assume it
probably failed" would be exactly the guess-and-retry behavior this task
explicitly forbids ("broker evidence 없이 '아마 주문 실패했겠지'라고 판단하여
retry하는 것은 금지"). This tool therefore only DETECTS and REPORTS orphaned
claims, and provides a `--resolve` command that requires an operator to
supply the real outcome themselves (after checking the broker's own order/
fill history), with the resolution fully audited (who, when, why, what
evidence) in `data/state/step5d_manual_reconciliation.jsonl`.

This module makes NO change to Step5C's CAS transition logic or table
schema, and calls `finish_execution`/`release_physical_order` exactly as
Step5C's own `execute_owned_order` would on a genuine terminal outcome --
it is a caller of the existing, frozen contract, never a modification of it.

RUNBOOK (manual steps an operator follows for each orphaned claim):
  1. Run `--report` to list every active physical_order_claim older than
     the grace period, with its intent_id, owner, claimed_at, and age.
  2. For each one, query the broker directly for that day's order/fill
     history around `claimed_at` (the real `account.orders` skill, kt00007,
     qry_tp=1 or 2 covers "all orders"; qry_tp=4 covers "fills only") via
     the operator's own broker UI or `scripts/query_intent_state_store.py`-
     style tooling -- this script does not perform that broker query
     itself, since it has no symbol/qty/price to filter by (see above).
  3. Determine, from that real evidence, whether the order was ultimately
     ACCEPTED (ended up on the broker's books, filled or not) or genuinely
     NEVER SENT / REJECTED.
  4. Run `--resolve <physical_order_key> --intent-id <intent_id>
     --outcome executed|failed --confirmed-by <name> --evidence "<free text
     citing the broker record checked>"` to close the claim. This transitions
     the SQLite intent_state row EXECUTING -> EXECUTED/FAILED via the exact
     same `finish_execution`/`release_physical_order` calls Step5C's own
     execute_owned_order uses on a genuine terminal outcome, and appends an
     audit record.
  5. If evidence is genuinely insufficient/ambiguous, do NOT resolve --
     leave the claim held (fail-closed is correct) and escalate.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.path_isolation import resolve_runtime_write_path
from libs.supervisor.intent_state_store import (
    INTENT_STATE_EXECUTED,
    INTENT_STATE_FAILED,
    SQLiteIntentStateStore,
    resolve_intent_state_db_path,
)

_DEFAULT_GRACE_SEC = 120  # a legitimate broker round-trip should resolve well within this
_DEFAULT_AUDIT_LOG = "data/state/step5d_manual_reconciliation.jsonl"


def _audit_log_path(explicit: Optional[str] = None) -> Path:
    raw = str(explicit or _DEFAULT_AUDIT_LOG)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(__file__).resolve().parents[1] / candidate
    return resolve_runtime_write_path(candidate)


def report(*, db_path: Optional[str], grace_sec: int, limit: int) -> Dict[str, Any]:
    store = SQLiteIntentStateStore(db_path or str(resolve_intent_state_db_path()))
    now = int(time.time())
    claims = store.list_active_physical_claims(limit=max(1, int(limit)))
    orphans: List[Dict[str, Any]] = []
    for row in claims:
        age = max(0, now - int(row.get("claimed_at") or now))
        if age < max(0, int(grace_sec)):
            continue
        intent_id = str(row.get("intent_id") or "")
        intent_state = store.get_state(intent_id)
        orphans.append({
            "physical_order_key": row.get("physical_order_key"),
            "intent_id": intent_id,
            "owner": row.get("owner"),
            "claimed_at": row.get("claimed_at"),
            "age_seconds": age,
            "claim_state": row.get("state"),
            "intent_state": (intent_state or {}).get("state"),
            "journal": store.list_journal(intent_id, limit=10),
        })
    return {
        "ok": True,
        "db_path": str(store.path),
        "grace_seconds": int(grace_sec),
        "generated_at": now,
        "orphan_count": len(orphans),
        "manual_reconciliation_required": len(orphans) > 0,
        "orphans": orphans,
        "runbook": (
            "For each orphan: query the broker's real order/fill history "
            "(account.orders skill, kt00007) for the time window around "
            "claimed_at; determine ACCEPTED vs NOT_SENT/REJECTED from that "
            "real evidence; then run --resolve. Never guess."
        ),
    }


def resolve(
    *,
    db_path: Optional[str],
    physical_order_key: str,
    intent_id: str,
    outcome: str,
    confirmed_by: str,
    evidence: str,
    audit_log: Optional[str],
) -> Dict[str, Any]:
    outcome_norm = str(outcome or "").strip().lower()
    if outcome_norm not in ("executed", "failed"):
        return {"ok": False, "error": "outcome must be 'executed' or 'failed'"}
    if not confirmed_by.strip():
        return {"ok": False, "error": "confirmed_by is required (operator identity for the audit trail)"}
    if not evidence.strip():
        return {"ok": False, "error": "evidence is required (what real broker record was checked)"}

    store = SQLiteIntentStateStore(db_path or str(resolve_intent_state_db_path()))
    claim = store.get_physical_claim(physical_order_key)
    if claim is None:
        return {"ok": False, "error": "no active physical_order_claim for that key"}
    if str(claim.get("intent_id")) != str(intent_id):
        return {
            "ok": False,
            "error": "intent_id does not match the claim's own holder -- refusing to resolve someone else's lease",
            "holder_intent_id": claim.get("intent_id"),
        }

    broker_outcome = "ACCEPTED" if outcome_norm == "executed" else "NOT_SENT"
    owner = str(claim.get("owner") or "")
    try:
        target = store.finish_execution(
            intent_id,
            owner=owner,
            execution={
                "broker_outcome": broker_outcome,
                "reconciliation": "step5d_manual",
                "confirmed_by": confirmed_by,
                "evidence": evidence,
            },
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if target in (INTENT_STATE_EXECUTED, INTENT_STATE_FAILED):
        try:
            store.release_physical_order(physical_order_key, intent_id=intent_id)
        except Exception:
            pass

    record = {
        "ts": int(time.time()),
        "physical_order_key": physical_order_key,
        "intent_id": intent_id,
        "owner": owner,
        "resolved_state": target,
        "confirmed_by": confirmed_by,
        "evidence": evidence,
    }
    log_path = _audit_log_path(audit_log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"ok": True, "resolved_state": target, "audit_log": str(log_path), "record": record}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Step5D crash reconciliation: detect and manually resolve orphaned physical_order_claim leases.")
    p.add_argument("--state-db-path", default="")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    rep = sub.add_parser("report", help="List orphaned (stuck) physical-order claims.")
    rep.add_argument("--grace-sec", type=int, default=_DEFAULT_GRACE_SEC)
    rep.add_argument("--limit", type=int, default=200)

    res = sub.add_parser("resolve", help="Manually, explicitly resolve one orphaned claim with confirmed broker evidence.")
    res.add_argument("--physical-order-key", required=True)
    res.add_argument("--intent-id", required=True)
    res.add_argument("--outcome", required=True, choices=["executed", "failed"])
    res.add_argument("--confirmed-by", required=True)
    res.add_argument("--evidence", required=True)
    res.add_argument("--audit-log", default="")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    db_path = str(args.state_db_path or "").strip() or None

    if args.cmd == "report":
        result = report(db_path=db_path, grace_sec=int(args.grace_sec), limit=int(args.limit))
    else:
        result = resolve(
            db_path=db_path,
            physical_order_key=str(args.physical_order_key),
            intent_id=str(args.intent_id),
            outcome=str(args.outcome),
            confirmed_by=str(args.confirmed_by),
            evidence=str(args.evidence),
            audit_log=str(args.audit_log or "") or None,
        )

    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result)
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
