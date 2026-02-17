from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    INTENT_STATE_APPROVED: {INTENT_STATE_EXECUTING},
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

    def __init__(self, path: str = "data/state/intent_state.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
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
