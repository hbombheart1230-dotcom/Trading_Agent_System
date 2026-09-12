from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.core.path_isolation import resolve_runtime_write_path

_DEFAULT_INTENT_STATE_DB_PATH = "data/state/intent_state.db"

# Step5C Fix3 (HIGH2): a bare format check is not sufficient authorization
# on its own (existence + approved-state is what actually matters, enforced
# in claim_execution), but it does reject unambiguous garbage up front --
# Codex's exact reproduction ("bad id" containing a space, "@@@") -- before
# it ever reaches a SQL parameter. Covers both this codebase's own
# identity schemes (a bare uuid4 hex from TwoPhaseSupervisor.create_intent,
# and bind_intent's "intent-v1-<sha256 hex>") plus the free-form
# alphanumeric/hyphen/underscore synthetic ids this repo's own test/ops
# tooling (e.g. scripts/run_m24_guard_precedence_check.py) uses.
_INTENT_ID_FORMAT_RE = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_intent_state_db_path(explicit: Optional[str] = None) -> Path:
    """Single canonical resolver for the intent-ownership database.

    Every execution entry point (automated packet path, manual approval
    service/CLI, reconciliation/query scripts, tests) must resolve to the
    same absolute file so "one owner per intent_id" holds across processes
    regardless of working directory or which caller constructed the store.
    Precedence, matching the Step5C Fix2 contract:
      - explicit path argument, absolute -> used as-is
      - explicit path argument, relative -> anchored to the repository root
      - INTENT_STATE_DB_PATH env var, absolute -> used as-is
      - INTENT_STATE_DB_PATH env var, relative -> anchored to the repository
        root (Fix2: previously a bare relative env value was returned
        unresolved -- resolve_runtime_write_path is a no-op outside pytest,
        so two processes with the same relative INTENT_STATE_DB_PATH but
        different working directories silently resolved to different
        physical files)
      - neither given -> repository-root/data/state/intent_state.db
    """
    raw = str(explicit).strip() if explicit else (os.getenv("INTENT_STATE_DB_PATH", "") or "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = _repo_root() / candidate
    else:
        candidate = _repo_root() / _DEFAULT_INTENT_STATE_DB_PATH
    return resolve_runtime_write_path(candidate)


INTENT_STATE_PENDING = "pending_approval"
INTENT_STATE_APPROVED = "approved"
INTENT_STATE_EXECUTING = "executing"
INTENT_STATE_EXECUTED = "executed"
INTENT_STATE_FAILED = "failed"
INTENT_STATE_REJECTED = "rejected"

INTENT_ALLOWED_STATES = {
    INTENT_STATE_PENDING,
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTING,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_FAILED,
    INTENT_STATE_REJECTED,
}

INTENT_TERMINAL_STATES = {
    INTENT_STATE_EXECUTED,
    INTENT_STATE_FAILED,
    INTENT_STATE_REJECTED,
}

_ALLOWED_TRANSITIONS = {
    INTENT_STATE_PENDING: {INTENT_STATE_APPROVED, INTENT_STATE_REJECTED},
    # Step5C Fix2: approved->failed (direct, no EXECUTING in between) covers
    # a caller failing before ever reaching claim_execution -- e.g. an
    # exception raised by execute_fn's own request-building code, prior to
    # any dispatch attempt. There is no dispatch ambiguity in that case (no
    # claim was ever taken), so it is safe to record FAILED directly rather
    # than forcing an artificial EXECUTING hop. approved->executing remains
    # the only path into EXECUTING, and only claim_execution's atomic CAS
    # performs it.
    INTENT_STATE_APPROVED: {INTENT_STATE_EXECUTING, INTENT_STATE_FAILED},
    INTENT_STATE_EXECUTING: {INTENT_STATE_EXECUTED, INTENT_STATE_FAILED},
    INTENT_STATE_EXECUTED: set(),
    INTENT_STATE_FAILED: set(),
    INTENT_STATE_REJECTED: set(),
}


def _now_epoch() -> int:
    return int(time.time())


def _as_state(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in INTENT_ALLOWED_STATES:
        return s
    return ""


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    from_state: str
    to_state: str
    reason: str
    changed: bool


class IntentStateMachine:
    """Strict intent state transition validator (M24-1)."""

    @staticmethod
    def can_transition(from_state: str, to_state: str) -> bool:
        f = _as_state(from_state)
        t = _as_state(to_state)
        if not f or not t:
            return False
        return t in _ALLOWED_TRANSITIONS.get(f, set())

    @staticmethod
    def apply(
        from_state: str,
        to_state: str,
        *,
        allow_terminal_idempotent: bool = True,
    ) -> TransitionResult:
        f = _as_state(from_state)
        t = _as_state(to_state)
        if not f or not t:
            return TransitionResult(
                ok=False,
                from_state=f or str(from_state or ""),
                to_state=t or str(to_state or ""),
                reason="invalid_state",
                changed=False,
            )

        if f == t:
            # Optional idempotent retry semantics for terminal writes.
            if allow_terminal_idempotent and t in INTENT_TERMINAL_STATES:
                return TransitionResult(ok=True, from_state=f, to_state=t, reason="idempotent_terminal", changed=False)
            return TransitionResult(ok=False, from_state=f, to_state=t, reason="no_state_change", changed=False)

        if t in _ALLOWED_TRANSITIONS.get(f, set()):
            return TransitionResult(ok=True, from_state=f, to_state=t, reason="allowed", changed=True)

        return TransitionResult(ok=False, from_state=f, to_state=t, reason="invalid_transition", changed=False)


class SQLiteIntentStateStore:
    """SQLite-first intent state/journal store (M24-1 scaffold)."""

    def __init__(self, path: Optional[str] = None):
        # Call-time isolation check (not a bare default-parameter value):
        # default expressions are evaluated once at module import, before
        # PYTEST_CURRENT_TEST is set, so this must run here to see the
        # correct running-under-pytest state. resolve_intent_state_db_path
        # (not isolate_canonical_path_for_pytest's exact-literal match) so
        # any repository-relative path -- not just the exact canonical
        # default -- is isolated under pytest, e.g.
        # SQLiteIntentStateStore("data/custom.db") or
        # SQLiteIntentStateStore("custom.db"). An explicit path argument is
        # preserved verbatim (existing callers passing their own path are
        # unaffected); only the no-argument/None default now routes through
        # the canonical, cwd-independent resolver (Step5C Fix1 -- previously
        # this default was a bare relative path, silently cwd-dependent in
        # production since resolve_runtime_write_path is a no-op outside
        # pytest).
        self.path = resolve_intent_state_db_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        # Step5C Fix5 (MEDIUM, admission schema readiness): every table this
        # store owns is created here, at construction, rather than lazily
        # inside individual read/write methods. Codex's audit confirmed a
        # real operational DB existed with intent_state/intent_journal but
        # no intent_admission table yet -- get_admission() issuing a bare
        # SELECT against a missing table would raise sqlite3.OperationalError
        # instead of returning None. Schema readiness is now guaranteed for
        # every consumer (claim_execution, admit_intent, get_admission,
        # claim_physical_order, etc.) the moment the store is constructed,
        # on both a brand-new DB and an existing one created before this
        # table existed.
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_state (
                    intent_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_ts INTEGER NOT NULL,
                    version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    reason TEXT,
                    meta_json TEXT,
                    execution_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_intent_journal_intent_ts
                ON intent_journal(intent_id, ts)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_execution_binding (
                    intent_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    owner TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intent_admission (
                    intent_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    source TEXT NOT NULL,
                    admitted_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS physical_order_claim (
                    physical_order_key TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    claimed_at INTEGER NOT NULL,
                    state TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def ensure_intent(self, intent_id: str, *, initial_state: str = INTENT_STATE_PENDING) -> Dict[str, Any]:
        iid = str(intent_id or "").strip()
        if not iid:
            raise ValueError("intent_id is required")
        init = _as_state(initial_state)
        if init != INTENT_STATE_PENDING:
            raise ValueError("initial_state must be pending_approval")

        row = self.get_state(iid)
        if row is not None:
            return row

        ts = _now_epoch()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO intent_state(intent_id, state, updated_ts, version) VALUES(?, ?, ?, ?)",
                (iid, init, ts, 1),
            )
            conn.execute(
                """
                INSERT INTO intent_journal(intent_id, ts, from_state, to_state, reason, meta_json, execution_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (iid, ts, "", init, "init", "{}", None),
            )
            conn.commit()
        return self.get_state(iid) or {"intent_id": iid, "state": init, "updated_ts": ts, "version": 1}

    def get_state(self, intent_id: str) -> Optional[Dict[str, Any]]:
        iid = str(intent_id or "").strip()
        if not iid:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT intent_id, state, updated_ts, version FROM intent_state WHERE intent_id = ?",
                (iid,),
            ).fetchone()
            if row is None:
                return None
            return {
                "intent_id": str(row["intent_id"]),
                "state": str(row["state"]),
                "updated_ts": int(row["updated_ts"]),
                "version": int(row["version"]),
            }

    def transition(
        self,
        *,
        intent_id: str,
        to_state: str,
        expected_from_state: Optional[str] = None,
        reason: str = "",
        meta: Optional[Dict[str, Any]] = None,
        execution: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        iid = str(intent_id or "").strip()
        if not iid:
            raise ValueError("intent_id is required")

        cur = self.get_state(iid)
        if cur is None:
            cur = self.ensure_intent(iid)

        from_state = str(cur.get("state") or "")
        expected = _as_state(expected_from_state) if expected_from_state is not None else ""
        if expected_from_state is not None and not expected:
            raise ValueError(f"Invalid expected_from_state: {expected_from_state}")
        if expected and from_state != expected:
            raise ValueError(f"State mismatch: expected={expected}, current={from_state}")

        tr = IntentStateMachine.apply(from_state, to_state, allow_terminal_idempotent=True)
        if not tr.ok:
            raise ValueError(f"Invalid intent state transition: {from_state} -> {to_state} ({tr.reason})")

        ts = _now_epoch()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        execution_json = json.dumps(execution, ensure_ascii=False) if isinstance(execution, dict) else None

        with self._connect() as conn:
            if tr.changed:
                next_version = int(cur.get("version") or 1) + 1
                if expected:
                    c = conn.execute(
                        """
                        UPDATE intent_state
                        SET state = ?, updated_ts = ?, version = ?
                        WHERE intent_id = ? AND state = ?
                        """,
                        (tr.to_state, ts, next_version, iid, expected),
                    )
                    if int(c.rowcount or 0) != 1:
                        conn.rollback()
                        latest = self.get_state(iid) or {}
                        raise ValueError(
                            f"State mismatch during CAS update: expected={expected}, current={latest.get('state')}"
                        )
                else:
                    conn.execute(
                        "UPDATE intent_state SET state = ?, updated_ts = ?, version = ? WHERE intent_id = ?",
                        (tr.to_state, ts, next_version, iid),
                    )
            else:
                next_version = int(cur.get("version") or 1)
                conn.execute(
                    "UPDATE intent_state SET updated_ts = ? WHERE intent_id = ?",
                    (ts, iid),
                )

            conn.execute(
                """
                INSERT INTO intent_journal(intent_id, ts, from_state, to_state, reason, meta_json, execution_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (iid, ts, tr.from_state, tr.to_state, reason or tr.reason, meta_json, execution_json),
            )
            conn.commit()

        out = self.get_state(iid) or {}
        out["transition"] = {
            "from_state": tr.from_state,
            "to_state": tr.to_state,
            "changed": tr.changed,
            "reason": tr.reason,
        }
        return out

    def claim_execution(self, intent_id: str, *, fingerprint: str, owner: str) -> Dict[str, Any]:
        """Atomically claim an already-admitted, approved order for execution.

        Step5C Fix5 (HIGH2, consumer-only authority): claim_execution() is
        strictly a CONSUMER of authority that some other, explicit upstream
        boundary already established (ApprovalService.approve(),
        libs.execution.intent_admission.admit_order_intent, an authorized
        automatic/child-cancel admission call, ...). It never creates,
        approves, or repairs anything -- it only:
          1. validates the intent_id format
          2. loads the persisted intent      -> absent -> INTENT_NOT_FOUND
          3. loads the persisted admission   -> absent -> ADMISSION_NOT_FOUND
          4. compares the submitted fingerprint to the admitted one
             -> mismatch -> PAYLOAD_MISMATCH
          5. verifies state == approved      -> pending -> NOT_APPROVED;
             any other non-approved state -> intent_already_owned_or_not_approved
          6. checks the execution-binding fingerprint (a second, later
             comparison covering an already-claimed intent replayed with a
             different payload) -> mismatch -> intent_identity_conflict
          7. performs the atomic APPROVED -> EXECUTING CAS
          8. records the (now confirmed, not invented) owner binding

        Fix4's own version of this method still auto-created an
        "intent_admission" row (reason "legacy_approved_state") for ANY
        approved intent that reached here with no admission row at all --
        Codex's audit reproduced this as a real attack: persist intent X as
        BUY 005930 qty=1 MARKET with admission NEVER granted, then submit a
        completely different payload (BUY 000660 qty=99 MARKET) under the
        same intent_id -- claim_execution manufactured an admission FROM
        THE SUBMITTED PAYLOAD and dispatched it (broker calls == 1, expected
        0). That auto-admission branch is deleted outright, with no
        replacement inside this method. A legacy APPROVED row with no
        admission is refused as ADMISSION_NOT_FOUND, full stop -- closing
        that gap requires an explicit, separately-authorized migration
        step (not implemented here; out of scope for Fix5), never an
        implicit repair inside the execution claim path itself.
        """
        if not intent_id or not fingerprint or not owner:
            raise ValueError('execution identity, fingerprint and owner required')
        if not _INTENT_ID_FORMAT_RE.match(str(intent_id)):
            return {'claimed': False, 'reason': 'INVALID_INTENT_ID'}
        ts = _now_epoch()
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT state FROM intent_state WHERE intent_id=?', (intent_id,)).fetchone()
            if not current:
                return {'claimed': False, 'reason': 'INTENT_NOT_FOUND'}
            admission = conn.execute(
                'SELECT fingerprint, source FROM intent_admission WHERE intent_id=?', (intent_id,)
            ).fetchone()
            if not admission:
                return {'claimed': False, 'reason': 'ADMISSION_NOT_FOUND'}
            if str(admission['fingerprint']) != str(fingerprint):
                return {'claimed': False, 'reason': 'PAYLOAD_MISMATCH'}
            if current['state'] == INTENT_STATE_PENDING:
                return {'claimed': False, 'reason': 'NOT_APPROVED', 'state': current['state']}
            if current['state'] != INTENT_STATE_APPROVED:
                return {'claimed': False, 'reason': 'intent_already_owned_or_not_approved', 'state': current['state']}
            binding = conn.execute('SELECT fingerprint FROM intent_execution_binding WHERE intent_id=?', (intent_id,)).fetchone()
            if binding and binding['fingerprint'] != fingerprint:
                return {'claimed': False, 'reason': 'intent_identity_conflict'}
            updated = conn.execute('UPDATE intent_state SET state=?,updated_ts=?,version=version+1 '
                                   'WHERE intent_id=? AND state=?',
                                   (INTENT_STATE_EXECUTING, ts, intent_id, INTENT_STATE_APPROVED))
            if updated.rowcount != 1:
                raise RuntimeError('intent_CAS_expected_approved')
            conn.execute('INSERT INTO intent_execution_binding VALUES(?,?,?) '
                         'ON CONFLICT(intent_id) DO UPDATE SET owner=excluded.owner', (intent_id, fingerprint, owner))
            conn.execute('INSERT INTO intent_journal(intent_id,ts,from_state,to_state,reason,meta_json) VALUES(?,?,?,?,?,?)',
                         (intent_id, ts, INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING, 'execution_owner_CAS', '{}'))
        return {'claimed': True, 'state': INTENT_STATE_EXECUTING, 'owner': owner}

    def admit_intent(self, intent_id: str, *, fingerprint: str, source: str) -> Dict[str, Any]:
        """Persist explicit upstream execution authority before claiming."""
        iid = str(intent_id or '').strip()
        if not _INTENT_ID_FORMAT_RE.match(iid) or not fingerprint or not source:
            return {'admitted': False, 'reason': 'INVALID_ADMISSION'}
        ts = _now_epoch()
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute(
                'CREATE TABLE IF NOT EXISTS intent_admission '
                '(intent_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, source TEXT NOT NULL, admitted_at INTEGER NOT NULL)'
            )
            row = conn.execute('SELECT state FROM intent_state WHERE intent_id=?', (iid,)).fetchone()
            binding = conn.execute('SELECT fingerprint FROM intent_admission WHERE intent_id=?', (iid,)).fetchone()
            if binding and str(binding['fingerprint']) != str(fingerprint):
                return {'admitted': False, 'reason': 'intent_identity_conflict'}
            if row and str(row['state']) not in (INTENT_STATE_PENDING, INTENT_STATE_APPROVED):
                return {'admitted': False, 'reason': 'intent_not_admissible', 'state': str(row['state'])}
            if not row:
                conn.execute('INSERT INTO intent_state VALUES (?, ?, ?, ?)', (iid, INTENT_STATE_PENDING, ts, 1))
                conn.execute(
                    'INSERT INTO intent_journal(intent_id,ts,from_state,to_state,reason,meta_json) VALUES(?,?,?,?,?,?)',
                    (iid, ts, '', INTENT_STATE_PENDING, 'intent_created', json.dumps({'source': source})),
                )
            conn.execute(
                'INSERT INTO intent_admission VALUES(?,?,?,?) '
                'ON CONFLICT(intent_id) DO NOTHING',
                (iid, fingerprint, source, ts),
            )
            current = conn.execute('SELECT state FROM intent_state WHERE intent_id=?', (iid,)).fetchone()
            if current and str(current['state']) == INTENT_STATE_PENDING:
                conn.execute(
                    'UPDATE intent_state SET state=?,updated_ts=?,version=version+1 WHERE intent_id=? AND state=?',
                    (INTENT_STATE_APPROVED, ts, iid, INTENT_STATE_PENDING),
                )
                conn.execute(
                    'INSERT INTO intent_journal(intent_id,ts,from_state,to_state,reason,meta_json) VALUES(?,?,?,?,?,?)',
                    (iid, ts, INTENT_STATE_PENDING, INTENT_STATE_APPROVED, 'intent_admitted', json.dumps({'source': source})),
                )
        return {'admitted': True, 'state': INTENT_STATE_APPROVED, 'source': source}

    def get_owner(self, intent_id: str) -> Optional[str]:
        """The owner token durably bound to intent_id's execution claim, if any."""
        iid = str(intent_id or "").strip()
        if not iid:
            return None
        with self._connect() as conn:
            row = conn.execute('SELECT owner FROM intent_execution_binding WHERE intent_id=?', (iid,)).fetchone()
        return str(row['owner']) if row else None

    def get_admission(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Return the persisted authority provenance for an intent."""
        iid = str(intent_id or '').strip()
        if not iid:
            return None
        with self._connect() as conn:
            row = conn.execute(
                'SELECT intent_id, fingerprint, source, admitted_at '
                'FROM intent_admission WHERE intent_id=?',
                (iid,),
            ).fetchone()
        return dict(row) if row else None

    def verify_ownership(self, intent_id: str, owner: str) -> bool:
        """True only if intent_id is currently EXECUTING and owner matches
        the durably bound capability token.

        Step5C Fix3 (LOW, documented per the audit's Option B): this is an
        observability/debug helper, not a production authorization gate --
        no code path in this repository calls it before dispatching to a
        broker. The actual safety invariant ("EXECUTING state alone is
        never permission to execute", Fix2 HIGH1) comes from there being
        exactly one call site, execute_owned_order(), that ever performs
        the claim_execution() CAS in the same call that dispatches -- not
        from a second, separate verification step. Use this method to
        inspect/debug a specific claim's current owner from outside that
        call stack (e.g. tooling, tests); do not read "capability
        authorization" as this method's production role.
        """
        iid = str(intent_id or "").strip()
        own = str(owner or "").strip()
        if not iid or not own:
            return False
        with self._connect() as conn:
            row = conn.execute(
                'SELECT s.state AS state FROM intent_state s '
                'JOIN intent_execution_binding b ON b.intent_id = s.intent_id '
                'WHERE s.intent_id=? AND b.owner=?',
                (iid, own),
            ).fetchone()
        return bool(row and row['state'] == INTENT_STATE_EXECUTING)

    def finish_execution(self, intent_id: str, *, owner: str, execution: Dict[str, Any]) -> str:
        outcome = execution.get('broker_outcome')
        target = INTENT_STATE_EXECUTED if outcome == 'ACCEPTED' else (
            INTENT_STATE_FAILED if outcome in {'NOT_SENT', 'REJECTED'} else INTENT_STATE_EXECUTING)
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            updated = conn.execute('UPDATE intent_state SET state=?,updated_ts=?,version=version+1 '
                'WHERE intent_id=? AND state=? AND EXISTS '
                '(SELECT 1 FROM intent_execution_binding WHERE intent_id=? AND owner=?)',
                (target, _now_epoch(), intent_id, INTENT_STATE_EXECUTING, intent_id, owner))
            if updated.rowcount != 1:
                raise RuntimeError('intent_execution_owner_mismatch')
            conn.execute('INSERT INTO intent_journal(intent_id,ts,from_state,to_state,reason,meta_json,execution_json) '
                'VALUES(?,?,?,?,?,?,?)', (intent_id, _now_epoch(), INTENT_STATE_EXECUTING, target,
                 'broker_outcome_recorded', '{}', json.dumps(execution, ensure_ascii=False, default=str)))
        return target

    # ---------- physical-order duplicate guard (Step5C Fix2) ------------
    #
    # Separate from, and composed with, intent ownership above: two
    # DIFFERENT intent_id values (e.g. one from the automated content-hash
    # scheme, one from the manual uuid4 scheme) can still describe the same
    # real-world broker mutation. This table is a system-level execution
    # safety guard -- not a strategy/policy guard -- that ensures at most
    # one intent holds an active "lease" on a given physical order shape at
    # a time, regardless of which path (automatic, manual approval,
    # APPROVAL_MODE=auto, direct runner invocation) is attempting it.
    #
    # Deliberately no automatic release on crash/UNKNOWN (Option A,
    # consistent with the rest of this store): a lease is released only
    # when its owning intent reaches a genuine terminal state (EXECUTED /
    # FAILED). An ambiguous outcome leaves the lease held -- fail closed,
    # reconciliation required -- rather than risk a duplicate physical
    # dispatch. Step5D owns automatic reconciliation; it is not implemented
    # here.

    def claim_physical_order(self, physical_order_key: str, *, intent_id: str, owner: str) -> Dict[str, Any]:
        if not physical_order_key or not intent_id or not owner:
            raise ValueError('physical_order_key, intent_id and owner required')
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute(
                'CREATE TABLE IF NOT EXISTS physical_order_claim '
                '(physical_order_key TEXT PRIMARY KEY, intent_id TEXT NOT NULL, '
                'owner TEXT NOT NULL, claimed_at INTEGER NOT NULL, state TEXT NOT NULL)'
            )
            row = conn.execute(
                'SELECT intent_id, owner, state FROM physical_order_claim WHERE physical_order_key=?',
                (physical_order_key,),
            ).fetchone()
            if row:
                if str(row['intent_id']) == str(intent_id):
                    # The same logical intent re-entering its own already-held
                    # lease (e.g. a naive replay after a persistence failure).
                    # Not a NEW physical duplicate -- claim_execution's own
                    # intent-level CAS is what must reject this replay.
                    return {'claimed': True, 'state': row['state'], 'reused': True}
                return {
                    'claimed': False,
                    'reason': 'physical_order_already_claimed',
                    'holder_intent_id': str(row['intent_id']),
                    'state': str(row['state']),
                }
            conn.execute(
                'INSERT INTO physical_order_claim VALUES (?,?,?,?,?)',
                (physical_order_key, intent_id, owner, _now_epoch(), 'active'),
            )
        return {'claimed': True, 'state': 'active', 'reused': False}

    def release_physical_order(self, physical_order_key: str, *, intent_id: str) -> None:
        """Release a lease this intent_id itself holds, on genuine terminal
        outcome only. A no-op if the row is absent or held by another
        intent (never releases someone else's lease)."""
        if not physical_order_key or not intent_id:
            return
        with closing(self._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute(
                'CREATE TABLE IF NOT EXISTS physical_order_claim '
                '(physical_order_key TEXT PRIMARY KEY, intent_id TEXT NOT NULL, '
                'owner TEXT NOT NULL, claimed_at INTEGER NOT NULL, state TEXT NOT NULL)'
            )
            conn.execute(
                'DELETE FROM physical_order_claim WHERE physical_order_key=? AND intent_id=?',
                (physical_order_key, intent_id),
            )

    # ---------- physical claim introspection (Step5C Fix3, MEDIUM1) -----
    #
    # Read-only. No automatic release/recovery is implemented here -- an
    # orphaned lease (the owning process crashed between claim_physical_
    # order succeeding and finish_execution running, or claim_execution
    # itself raised) stays held, fail-closed, until an operator or a future
    # Step5D reconciliation process acts on it. These two methods exist so
    # that orphan state is at least *observable* rather than silently
    # invisible -- ownership resolution/cleanup is explicitly out of scope
    # for this Fix.

    def get_physical_claim(self, physical_order_key: str) -> Optional[Dict[str, Any]]:
        """The current physical_order_claim row for one key, if any."""
        key = str(physical_order_key or "").strip()
        if not key:
            return None
        with self._connect() as conn:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS physical_order_claim '
                '(physical_order_key TEXT PRIMARY KEY, intent_id TEXT NOT NULL, '
                'owner TEXT NOT NULL, claimed_at INTEGER NOT NULL, state TEXT NOT NULL)'
            )
            row = conn.execute(
                'SELECT physical_order_key, intent_id, owner, claimed_at, state '
                'FROM physical_order_claim WHERE physical_order_key=?',
                (key,),
            ).fetchone()
        if not row:
            return None
        return {
            "physical_order_key": str(row["physical_order_key"]),
            "intent_id": str(row["intent_id"]),
            "owner": str(row["owner"]),
            "claimed_at": int(row["claimed_at"]),
            "state": str(row["state"]),
        }

    def list_active_physical_claims(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        """Every currently-held physical_order_claim row (there is no
        "expired"/TTL concept -- a row here is either actively backing an
        in-flight intent, or is an orphan awaiting operator/Step5D
        attention; get_physical_claim's caller can cross-reference
        intent_id against get_state/list_journal to tell the two apart)."""
        lim = max(1, int(limit))
        with self._connect() as conn:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS physical_order_claim '
                '(physical_order_key TEXT PRIMARY KEY, intent_id TEXT NOT NULL, '
                'owner TEXT NOT NULL, claimed_at INTEGER NOT NULL, state TEXT NOT NULL)'
            )
            rows = conn.execute(
                'SELECT physical_order_key, intent_id, owner, claimed_at, state '
                'FROM physical_order_claim ORDER BY claimed_at ASC LIMIT ?',
                (lim,),
            ).fetchall()
        return [
            {
                "physical_order_key": str(r["physical_order_key"]),
                "intent_id": str(r["intent_id"]),
                "owner": str(r["owner"]),
                "claimed_at": int(r["claimed_at"]),
                "state": str(r["state"]),
            }
            for r in rows
        ]

    def list_journal(self, intent_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        iid = str(intent_id or "").strip()
        if not iid:
            return []
        lim = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, intent_id, ts, from_state, to_state, reason, meta_json, execution_json
                FROM intent_journal
                WHERE intent_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (iid, lim),
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            meta_json = str(r["meta_json"] or "").strip()
            execution_json = str(r["execution_json"] or "").strip()
            meta: Dict[str, Any] = {}
            execution: Optional[Dict[str, Any]] = None
            if meta_json:
                try:
                    mj = json.loads(meta_json)
                    if isinstance(mj, dict):
                        meta = mj
                except Exception:
                    meta = {}
            if execution_json:
                try:
                    ej = json.loads(execution_json)
                    if isinstance(ej, dict):
                        execution = ej
                except Exception:
                    execution = None

            row: Dict[str, Any] = {
                "id": int(r["id"]),
                "intent_id": str(r["intent_id"]),
                "ts": int(r["ts"]),
                "from_state": str(r["from_state"] or ""),
                "to_state": str(r["to_state"] or ""),
                "reason": str(r["reason"] or ""),
                "meta": meta,
            }
            if execution is not None:
                row["execution"] = execution
            out.append(row)
        return out
