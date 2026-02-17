from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    INTENT_STATE_FAILED,
    INTENT_STATE_PENDING,
    INTENT_STATE_REJECTED,
    SQLiteIntentStateStore,
)

_FINAL_TO_PATH = {
    INTENT_STATE_PENDING: [INTENT_STATE_PENDING],
    INTENT_STATE_APPROVED: [INTENT_STATE_PENDING, INTENT_STATE_APPROVED],
    INTENT_STATE_EXECUTING: [INTENT_STATE_PENDING, INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING],
    INTENT_STATE_EXECUTED: [INTENT_STATE_PENDING, INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING, INTENT_STATE_EXECUTED],
    INTENT_STATE_FAILED: [INTENT_STATE_PENDING, INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING, INTENT_STATE_FAILED],
    INTENT_STATE_REJECTED: [INTENT_STATE_PENDING, INTENT_STATE_REJECTED],
}


def _normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return INTENT_STATE_PENDING
    if raw in ("pending", "pending_approval", "needs_approval", "created", "stored", "init"):
        return INTENT_STATE_PENDING
    if raw in (
        INTENT_STATE_APPROVED,
        INTENT_STATE_EXECUTING,
        INTENT_STATE_EXECUTED,
        INTENT_STATE_FAILED,
        INTENT_STATE_REJECTED,
    ):
        return raw
    return INTENT_STATE_PENDING


def _extract_intent_id(row: Dict[str, Any]) -> str:
    iid = str(row.get("intent_id") or "").strip()
    if iid:
        return iid
    intent = row.get("intent")
    if isinstance(intent, dict):
        return str(intent.get("intent_id") or "").strip()
    return ""


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                obj["_line"] = idx + 1
                out.append(obj)
    return out


def _sort_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _k(r: Dict[str, Any]) -> Tuple[int, int]:
        ts_raw = r.get("ts")
        try:
            ts = int(float(ts_raw))
        except Exception:
            ts = 0
        line = int(r.get("_line") or 0)
        return ts, line

    return sorted(rows, key=_k)


def _expected_state_by_intent(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    expected: Dict[str, str] = {}
    for r in _sort_rows(rows):
        iid = _extract_intent_id(r)
        if not iid:
            continue
        st = _normalize_status(r.get("status"))
        expected[iid] = st
    return expected


def _load_sqlite_states(db_path: Path) -> Dict[str, str]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT intent_id, state FROM intent_state").fetchall()
        except sqlite3.Error:
            return {}
    out: Dict[str, str] = {}
    for r in rows:
        out[str(r["intent_id"])] = str(r["state"] or "")
    return out


def _reset_intent(db_path: Path, intent_id: str) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DELETE FROM intent_journal WHERE intent_id = ?", (intent_id,))
        conn.execute("DELETE FROM intent_state WHERE intent_id = ?", (intent_id,))
        conn.commit()


def _replay_intent_to_final(db_path: Path, intent_id: str, final_state: str) -> None:
    store = SQLiteIntentStateStore(str(db_path))
    store.ensure_intent(intent_id, initial_state=INTENT_STATE_PENDING)
    path = _FINAL_TO_PATH.get(final_state, _FINAL_TO_PATH[INTENT_STATE_PENDING])
    # first state is always pending and ensured by ensure_intent
    for to_state in path[1:]:
        expected_from = path[path.index(to_state) - 1]
        store.transition(
            intent_id=intent_id,
            to_state=to_state,
            expected_from_state=expected_from,
            reason="reconcile_replay",
            meta={"source": "reconcile_intent_state_store"},
        )


def _repair_intent(db_path: Path, intent_id: str, final_state: str) -> Optional[str]:
    try:
        _reset_intent(db_path, intent_id)
        _replay_intent_to_final(db_path, intent_id, final_state)
        return None
    except Exception as e:
        return str(e)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reconcile JSONL intent journal and SQLite intent state store.")
    p.add_argument("--intent-log-path", default="data/logs/intents.jsonl")
    p.add_argument("--state-db-path", default="")
    p.add_argument("--repair", action="store_true", help="Repair missing/mismatched SQLite states by replaying from JSONL.")
    p.add_argument("--limit-details", type=int, default=20)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    log_path = Path(str(args.intent_log_path).strip())
    db_raw = str(args.state_db_path or "").strip()
    if db_raw:
        db_path = Path(db_raw)
    else:
        env_db = str((os.getenv("INTENT_STATE_DB_PATH", "") or "").strip())
        db_path = Path(env_db) if env_db else log_path.with_suffix(".db")

    rows = _load_jsonl(log_path)
    expected = _expected_state_by_intent(rows)
    sqlite_before = _load_sqlite_states(db_path)

    missing = sorted([iid for iid in expected.keys() if iid not in sqlite_before])
    mismatch = sorted(
        [iid for iid, st in expected.items() if iid in sqlite_before and str(sqlite_before.get(iid) or "") != st]
    )
    orphan = sorted([iid for iid in sqlite_before.keys() if iid not in expected])

    repaired: List[str] = []
    repair_errors: Dict[str, str] = {}
    if bool(args.repair):
        for iid in (missing + mismatch):
            err = _repair_intent(db_path, iid, expected.get(iid, INTENT_STATE_PENDING))
            if err:
                repair_errors[iid] = err
            else:
                repaired.append(iid)

    sqlite_after = _load_sqlite_states(db_path)
    missing_after = sorted([iid for iid in expected.keys() if iid not in sqlite_after])
    mismatch_after = sorted(
        [iid for iid, st in expected.items() if iid in sqlite_after and str(sqlite_after.get(iid) or "") != st]
    )

    ok = (len(missing_after) == 0) and (len(mismatch_after) == 0) and (len(repair_errors) == 0)
    lim = max(1, int(args.limit_details))
    summary = {
        "ok": bool(ok),
        "intent_log_path": str(log_path),
        "state_db_path": str(db_path),
        "jsonl_intent_total": int(len(expected)),
        "sqlite_intent_total_before": int(len(sqlite_before)),
        "sqlite_intent_total_after": int(len(sqlite_after)),
        "missing_total_before": int(len(missing)),
        "mismatch_total_before": int(len(mismatch)),
        "orphan_total_before": int(len(orphan)),
        "missing_total_after": int(len(missing_after)),
        "mismatch_total_after": int(len(mismatch_after)),
        "repaired_total": int(len(repaired)),
        "repair_error_total": int(len(repair_errors)),
        "details": {
            "missing_before": missing[:lim],
            "mismatch_before": mismatch[:lim],
            "orphan_before": orphan[:lim],
            "missing_after": missing_after[:lim],
            "mismatch_after": mismatch_after[:lim],
            "repaired": repaired[:lim],
            "repair_errors": {k: v for k, v in list(repair_errors.items())[:lim]},
        },
    }

    if bool(args.json):
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"ok={summary['ok']} jsonl_intent_total={summary['jsonl_intent_total']} "
            f"missing_before={summary['missing_total_before']} mismatch_before={summary['mismatch_total_before']} "
            f"repaired_total={summary['repaired_total']} missing_after={summary['missing_total_after']} "
            f"mismatch_after={summary['mismatch_total_after']}"
        )
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
