"""P0-D (real-readiness hardening, 2026-09-17): single-runtime execution
ownership, CAS-guarded via SQLite -- replaces PID-existence as the source of
truth for "which runtime instance may currently dispatch."

Why PID existence is not authoritative (empirically proven in this repo's
own Mock Docker validation, prior phase): two containers on the same host
have independent PID namespaces. Container B, checking Container A's
lock-file PID (libs/runtime/live_loop_lock.py::pid_exists()) from *inside
Container B's own PID namespace*, correctly finds no such PID -- and
concludes A is dead when A is alive and healthy. B then deleted A's lock and
took over while A kept running: a real split-brain, not a hypothetical one.

This module never asks "does a PID exist." It asks "does a still-valid,
explicitly-acquired lease exist, identified by an unforgeable per-process
UUID token (`instance_id`)" -- a question answered identically on bare
metal, inside one container, or across two containers sharing this SQLite
file via a mounted volume. It deliberately reuses the existing SQLite/CAS
pattern already proven in libs/supervisor/intent_state_store.py rather than
introducing any new distributed-coordination infrastructure (no Redis, no
etcd, no Kubernetes Lease object) -- out of scope for this task and
unnecessary for a single-owner, single-host-volume lease.

The existing PID-file heartbeat lock (live_loop_lock.py) is NOT removed or
replaced by this module -- it stays as-is, a coarse, host-local liveness
signal. This store is an ADDITIONAL, separate AUTHORITY signal layered
alongside it.

Semantics:

  ACQUIRE  -- no row yet, or the current row's lease has already expired AND
              the caller explicitly opted into takeover (`allow_stale_
              takeover=True`) -> this instance becomes owner, `generation`
              increments. A live (non-expired) lease held by a DIFFERENT
              instance_id -> FAIL CLOSED, always, regardless of
              `allow_stale_takeover` -- this store never deletes or
              overwrites another holder's still-valid lease.
  REFRESH  -- the caller's instance_id must exactly match the current
              owner's (an ownership-scoped CAS, mirroring intent_state's own
              expected-state CAS) -> heartbeat_at/lease_expires_at extended.
              A mismatch (someone else now owns it -- e.g. this process's
              own lease already expired and was taken over while it kept
              running) -> FAIL CLOSED: `refresh()` returns `ok=False,
              reason="lost_ownership"` and the caller MUST stop dispatching
              immediately, not keep running as if nothing happened.
  RELEASE  -- deletes a row ONLY if this exact instance_id currently owns
              it (the graceful-shutdown path). Never a bare "release
              whoever is there" -- that could let a crashed/hung process's
              ownership be silently discarded by an unrelated caller.

IMPORTANT -- lease expiry is NOT execution readiness. A newly-ACQUIREd
lease, especially via the stale-takeover path (`recovery_required=True` on
the result), only proves this process now holds exclusive dispatch
AUTHORITY. It says nothing about whether it is SAFE to dispatch yet. The
caller (libs/runtime/live_loop_runner.py) must still run its own state
recovery -> Step5C orphan check -> Step5D orphan check -> position
reconciliation -> pending/open-order reconciliation chain before ever
setting EXECUTION_READY = true. This store has no opinion on any of that;
it only answers "who, if anyone, may attempt to dispatch right now."
"""

from __future__ import annotations

import os
import socket
import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from libs.core.path_isolation import resolve_runtime_write_path

_DEFAULT_RUNTIME_OWNERSHIP_DB_PATH = "data/state/runtime_ownership.db"
_DEFAULT_LEASE_SECONDS = 30.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_runtime_ownership_db_path(explicit: Optional[str] = None) -> Path:
    """Single canonical resolver for the runtime-ownership database.

    Mirrors libs/supervisor/intent_state_store.py::resolve_intent_state_db_path's
    own precedence exactly, so this new store is cwd-independent and
    pytest-isolated the same way: explicit path argument (absolute used
    as-is, relative anchored to the repository root) > RUNTIME_OWNERSHIP_DB_PATH
    env var (same rule) > repository-root/data/state/runtime_ownership.db.
    """
    raw = str(explicit).strip() if explicit else (os.getenv("RUNTIME_OWNERSHIP_DB_PATH", "") or "").strip()
    if raw:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = _repo_root() / candidate
    else:
        candidate = _repo_root() / _DEFAULT_RUNTIME_OWNERSHIP_DB_PATH
    return resolve_runtime_write_path(candidate)


def new_runtime_instance_id() -> str:
    """One UUID4 hex per process startup -- the ownership token. Never
    reused across a restart: a crashed-and-restarted process must
    re-ACQUIRE (through either the no-prior-owner or the stale-takeover
    path), never assume an old lease it once held is still valid."""
    return uuid.uuid4().hex


def default_owner_label() -> str:
    """Human-readable-only (never used as the CAS identity -- that is
    always instance_id)."""
    return f"{socket.gethostname()}:{os.getpid()}"


@dataclass(frozen=True)
class OwnershipResult:
    ok: bool
    reason: str
    instance_id: str
    generation: int
    acquired_at: float
    lease_expires_at: float
    recovery_required: bool
    holder: Optional[Dict[str, Any]] = None


class SQLiteRuntimeOwnershipStore:
    """Single-owner execution-authority lease over one singleton row."""

    def __init__(self, path: Optional[str] = None):
        self.path = resolve_runtime_ownership_db_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_ownership (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    owner_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    boot_id TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL,
                    lease_expires_at REAL NOT NULL,
                    generation INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _row(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT owner_id, instance_id, boot_id, acquired_at, heartbeat_at, "
            "lease_expires_at, generation FROM runtime_ownership WHERE id = 1"
        ).fetchone()

    @staticmethod
    def _as_holder(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "owner_id": str(row["owner_id"]),
            "instance_id": str(row["instance_id"]),
            "boot_id": str(row["boot_id"]),
            "acquired_at": float(row["acquired_at"]),
            "heartbeat_at": float(row["heartbeat_at"]),
            "lease_expires_at": float(row["lease_expires_at"]),
            "generation": int(row["generation"]),
        }

    def acquire(
        self,
        *,
        instance_id: str,
        owner_id: str = "",
        boot_id: str = "",
        lease_seconds: float = _DEFAULT_LEASE_SECONDS,
        allow_stale_takeover: bool = False,
    ) -> OwnershipResult:
        iid = str(instance_id or "").strip()
        if not iid:
            raise ValueError("instance_id is required")
        oid = str(owner_id or "").strip() or default_owner_label()
        now = time.time()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row(conn)
            if row is None:
                conn.execute(
                    "INSERT INTO runtime_ownership "
                    "(id, owner_id, instance_id, boot_id, acquired_at, heartbeat_at, lease_expires_at, generation) "
                    "VALUES (1, ?, ?, ?, ?, ?, ?, 1)",
                    (oid, iid, boot_id, now, now, now + float(lease_seconds)),
                )
                return OwnershipResult(
                    ok=True, reason="acquired_no_prior_owner", instance_id=iid,
                    generation=1, acquired_at=now, lease_expires_at=now + float(lease_seconds),
                    recovery_required=False,
                )

            holder = self._as_holder(row)
            if holder["instance_id"] == iid:
                # Idempotent re-acquire by the SAME token (e.g. a caller
                # retrying acquire() before its first refresh) -- treated
                # as a refresh, not a new takeover; generation unchanged.
                conn.execute(
                    "UPDATE runtime_ownership SET heartbeat_at = ?, lease_expires_at = ? "
                    "WHERE id = 1 AND instance_id = ?",
                    (now, now + float(lease_seconds), iid),
                )
                return OwnershipResult(
                    ok=True, reason="acquired_idempotent_same_instance", instance_id=iid,
                    generation=holder["generation"], acquired_at=holder["acquired_at"],
                    lease_expires_at=now + float(lease_seconds), recovery_required=False,
                )

            if now < holder["lease_expires_at"]:
                # A DIFFERENT instance holds a still-valid lease. FAIL
                # CLOSED, unconditionally -- never delete/steal a live
                # lease, regardless of allow_stale_takeover.
                return OwnershipResult(
                    ok=False, reason="owned_by_other_instance", instance_id=iid,
                    generation=holder["generation"], acquired_at=holder["acquired_at"],
                    lease_expires_at=holder["lease_expires_at"], recovery_required=False,
                    holder=holder,
                )

            # Lease has expired. Expiry alone is never sufficient -- an
            # explicit takeover decision is required. This is the "lease
            # expiry != execution readiness" contract at its source: the
            # caller must already have decided it is willing to run the
            # full recovery chain before it may even ask for the lease.
            if not allow_stale_takeover:
                return OwnershipResult(
                    ok=False, reason="stale_lease_requires_explicit_recovery", instance_id=iid,
                    generation=holder["generation"], acquired_at=holder["acquired_at"],
                    lease_expires_at=holder["lease_expires_at"], recovery_required=True,
                    holder=holder,
                )

            next_generation = holder["generation"] + 1
            updated = conn.execute(
                "UPDATE runtime_ownership SET owner_id = ?, instance_id = ?, boot_id = ?, "
                "acquired_at = ?, heartbeat_at = ?, lease_expires_at = ?, generation = ? "
                "WHERE id = 1 AND lease_expires_at = ?",
                (oid, iid, boot_id, now, now, now + float(lease_seconds), next_generation, holder["lease_expires_at"]),
            )
            if int(updated.rowcount or 0) != 1:
                # Race: another instance's takeover (or the original
                # owner's own refresh) committed between our SELECT and
                # this UPDATE. Fail closed rather than silently overwrite.
                return OwnershipResult(
                    ok=False, reason="stale_takeover_race_lost", instance_id=iid,
                    generation=holder["generation"], acquired_at=holder["acquired_at"],
                    lease_expires_at=holder["lease_expires_at"], recovery_required=True,
                    holder=holder,
                )
            return OwnershipResult(
                ok=True, reason="acquired_stale_takeover", instance_id=iid,
                generation=next_generation, acquired_at=now, lease_expires_at=now + float(lease_seconds),
                recovery_required=True, holder=holder,
            )

    def refresh(self, *, instance_id: str, lease_seconds: float = _DEFAULT_LEASE_SECONDS) -> OwnershipResult:
        iid = str(instance_id or "").strip()
        if not iid:
            raise ValueError("instance_id is required")
        now = time.time()
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._row(conn)
            if row is None:
                return OwnershipResult(
                    ok=False, reason="no_owner_record", instance_id=iid,
                    generation=0, acquired_at=0.0, lease_expires_at=0.0, recovery_required=False,
                )
            holder = self._as_holder(row)
            updated = conn.execute(
                "UPDATE runtime_ownership SET heartbeat_at = ?, lease_expires_at = ? "
                "WHERE id = 1 AND instance_id = ?",
                (now, now + float(lease_seconds), iid),
            )
            if int(updated.rowcount or 0) != 1:
                # Someone else now owns it (our lease expired and was
                # taken over while we kept running). We have LOST
                # ownership -- the caller must stop dispatching now.
                return OwnershipResult(
                    ok=False, reason="lost_ownership", instance_id=iid,
                    generation=holder["generation"], acquired_at=holder["acquired_at"],
                    lease_expires_at=holder["lease_expires_at"], recovery_required=False,
                    holder=holder,
                )
            return OwnershipResult(
                ok=True, reason="refreshed", instance_id=iid,
                generation=holder["generation"], acquired_at=holder["acquired_at"],
                lease_expires_at=now + float(lease_seconds), recovery_required=False,
            )

    def release(self, *, instance_id: str) -> bool:
        """Release ONLY a lease this exact instance_id currently holds.
        No-op (returns False) if absent or held by someone else -- this
        method must never be usable to discard another runtime's claim,
        e.g. an orphaned lease left by a hard crash. Orphan takeover is
        exclusively acquire()'s allow_stale_takeover path, never this."""
        iid = str(instance_id or "").strip()
        if not iid:
            return False
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            deleted = conn.execute(
                "DELETE FROM runtime_ownership WHERE id = 1 AND instance_id = ?", (iid,)
            )
        return int(deleted.rowcount or 0) == 1

    def status(self) -> Optional[Dict[str, Any]]:
        """Read-only current holder, if any -- for health/diagnostic
        reporting (e.g. scripts/docker_healthcheck.py). Never mutates."""
        with self._connect() as conn:
            row = self._row(conn)
        return self._as_holder(row) if row is not None else None
