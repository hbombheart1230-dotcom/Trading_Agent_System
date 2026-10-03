"""Mock Trading Runtime Docker healthcheck (P0-D containerization step).

No HTTP server exists in the trading-loop process (confirmed by the prior
audit), so this is a plain `CMD` check reusing existing on-disk evidence --
no new health-reporting machinery is invented.

Exit code drives Docker's binary healthy/unhealthy (LIVENESS + READINESS
only, per Docker's own single-check model). EXECUTION_READY is a genuinely
distinct third concept (per the audit's 3-tier design) and is reported on
stdout for operator visibility, but deliberately does NOT affect the exit
code -- an orphaned Step5C claim awaiting manual reconciliation means
"do not trust this container to dispatch new orders yet", not "this
container is unhealthy and should be restarted" (that would let Docker's
restart policy attempt to paper over an execution-safety condition, which
is exactly backwards).

P1.3-R5 (2026-10-02): LIVENESS now follows the canonical SQLite runtime-
ownership heartbeat/lease (the same row libs/runtime/live_loop_runner.py's
OwnershipHeartbeat refreshes on a background thread, independent of tick
duration) instead of the lock file's heartbeat, which is only rewritten at
tick boundaries -- legitimate ticks (p90 ~137s, max ~434s, closeout ~55 min)
routinely exceeded the old 120s lock-heartbeat threshold and made a healthy
runtime look unhealthy. The lock file is now DIAGNOSTIC process-identity
information only. This script is strictly READ-ONLY: it opens the ownership
database with SQLite's read-only URI mode (it never creates, migrates,
acquires, refreshes, releases, or otherwise writes anything), and it does not
touch the lock file, readiness snapshot, or generation.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
import time
from pathlib import Path

LOCK_PATH = Path("/app/data/state/m13_live_loop.lock")
STATE_PATH = Path("/app/data/state.json")
INTENT_DB_PATH = Path("/app/data/state/intent_state.db")
OWNERSHIP_DB_PATH = Path("/app/data/state/runtime_ownership.db")
EXECUTION_READINESS_SNAPSHOT_PATH = Path("/app/data/state/execution_readiness.json")
OWNERSHIP_STALE_WARN_AGE_SEC = 120
EXECUTION_READINESS_SNAPSHOT_MAX_AGE_SEC = 120


def _own_hostname() -> str:
    return socket.gethostname()


def _read_ownership_row() -> dict | None:
    """READ-ONLY view of the canonical ownership row (mode=ro: never creates
    the file, never writes). Returns None when no owner row exists; raises if
    the database itself is missing/unreadable."""
    uri = f"file:{OWNERSHIP_DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT owner_id, instance_id, acquired_at, heartbeat_at, lease_expires_at, generation "
            "FROM runtime_ownership WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _read_lock_diagnostic() -> tuple[dict | None, str]:
    """Lock file = diagnostic process identity only. Never an authority:
    missing/unreadable/torn is reported, not failed."""
    if not LOCK_PATH.exists():
        return None, "lock_diagnostic=missing"
    try:
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"lock_diagnostic=unreadable:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "lock_diagnostic=unreadable:not_an_object"
    hb = int(payload.get("heartbeat_epoch") or 0)
    hb_age = f" lock_tick_heartbeat_age_sec={int(time.time()) - hb}" if hb > 0 else ""
    return payload, f"lock_diagnostic=pid:{payload.get('pid')}{hb_age}"


def _check_liveness() -> tuple[bool, str]:
    """Healthy iff a canonical owner row exists, its lease is currently valid,
    and it names THIS container's runtime. Authority = SQLite ownership only;
    the lock heartbeat's age is deliberately ignored."""
    try:
        row = _read_ownership_row()
    except Exception as exc:
        return False, f"ownership_db_unreadable:{type(exc).__name__}"
    lock_payload, lock_note = _read_lock_diagnostic()
    if row is None:
        return False, f"no_valid_owner:no_owner_row {lock_note}"

    now = time.time()
    remaining = row["lease_expires_at"] - now
    ident = (
        f"instance_id={str(row['instance_id'])[:12]} generation={row['generation']} "
        f"owner_id={row['owner_id']} heartbeat_age_sec={int(now - row['heartbeat_at'])} "
        f"lease_remaining_sec={int(remaining)}"
    )
    if remaining <= 0:
        return False, f"no_valid_owner:lease_expired {ident} {lock_note}"

    owner_host, _, owner_pid = str(row["owner_id"]).rpartition(":")
    if owner_host != _own_hostname():
        return False, f"owner_is_other_runtime {ident} own_host={_own_hostname()} {lock_note}"
    if lock_payload is not None and str(lock_payload.get("pid")) != owner_pid:
        return False, (
            f"ownership_identity_mismatch sqlite_owner_pid={owner_pid} "
            f"lock_pid={lock_payload.get('pid')} {ident}"
        )
    return True, f"source=sqlite_ownership {ident} {lock_note}"


def _check_readiness() -> tuple[bool, str]:
    if not STATE_PATH.exists():
        return False, "state_json_missing"
    try:
        json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"state_json_unreadable:{type(exc).__name__}"
    if not INTENT_DB_PATH.exists():
        # Genuinely fine on a brand-new deployment -- SQLiteIntentStateStore
        # creates it lazily on first use, not at container start.
        return True, "intent_db_not_yet_created"
    try:
        with sqlite3.connect(str(INTENT_DB_PATH)) as conn:
            conn.execute("SELECT 1 FROM intent_state LIMIT 1")
    except sqlite3.OperationalError:
        return True, "intent_db_present_no_rows_yet"
    except Exception as exc:
        return False, f"intent_db_unreachable:{type(exc).__name__}"
    return True, "intent_db_reachable"


def _report_execution_ready() -> str:
    """P1 (execution readiness authority, 2026-09-17): reads the SAME
    canonical `ExecutionReadiness` result the live tick already computed
    and persisted (graphs/nodes/build_execution_readiness.py) -- this
    process never recomputes the decision rule itself, which is exactly
    the "single source of truth, healthcheck does not reimplement its own
    rules" requirement. A missing or stale snapshot (older than
    EXECUTION_READINESS_SNAPSHOT_MAX_AGE_SEC -- e.g. before the first tick
    has ever run, or if the loop has stalled) is reported as UNKNOWN, never
    silently treated as ready."""
    try:
        if not EXECUTION_READINESS_SNAPSHOT_PATH.exists():
            return "EXECUTION_READY_UNKNOWN:snapshot_not_yet_written"
        payload = json.loads(EXECUTION_READINESS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        computed_at = int(payload.get("computed_at_epoch") or 0)
        age = int(time.time()) - computed_at if computed_at > 0 else -1
        if age < 0 or age > EXECUTION_READINESS_SNAPSHOT_MAX_AGE_SEC:
            return f"EXECUTION_READY_UNKNOWN:snapshot_stale_age_sec={age}"
        readiness = payload.get("execution_readiness") or {}
        if bool(readiness.get("ready")):
            return "EXECUTION_READY"
        reasons = ",".join(str(r) for r in (readiness.get("reasons") or []))
        return f"NOT_READY reasons={reasons or 'unspecified'}"
    except Exception as exc:
        return f"EXECUTION_READY_UNKNOWN:{type(exc).__name__}"


def _report_ownership_status() -> str:
    """P0-D (2026-09-17): reports which runtime_instance_id currently holds
    execution authority, if any -- observability only, like
    _report_execution_ready(), and for the identical reason: ownership
    contention/loss is a run_live_loop-level FAIL-CLOSED exit (codes 6/7,
    libs/runtime/live_loop_runner.py), not a Docker-restart-worthy health
    condition on its own. A container that lost the ownership race already
    exited non-zero and stopped its own loop; this line is purely for an
    operator/dashboard to see the lease's current holder/age/generation."""
    try:
        status = _read_ownership_row()
        if status is None:
            return "NO_OWNER"
        now = time.time()
        heartbeat_age = int(now - status["heartbeat_at"])
        lease_state = "LIVE" if now < status["lease_expires_at"] else "EXPIRED"
        detail = (
            f"lease={lease_state} generation={status['generation']} "
            f"heartbeat_age_sec={heartbeat_age} instance_id={status['instance_id'][:12]}"
        )
        if lease_state == "EXPIRED" or heartbeat_age > OWNERSHIP_STALE_WARN_AGE_SEC:
            return f"OWNERSHIP_STALE {detail}"
        return f"OWNERSHIP_ACTIVE {detail}"
    except Exception as exc:
        return f"OWNERSHIP_STATUS_UNKNOWN:{type(exc).__name__}"


def main() -> int:
    live_ok, live_detail = _check_liveness()
    ready_ok, ready_detail = _check_readiness()
    execution_ready = _report_execution_ready()
    ownership_status = _report_ownership_status()

    print(f"LIVENESS={'PASS' if live_ok else 'FAIL'} ({live_detail})")
    print(f"READINESS={'PASS' if ready_ok else 'FAIL'} ({ready_detail})")
    print(f"EXECUTION_READY_STATUS={execution_ready}")
    print(f"OWNERSHIP_STATUS={ownership_status}")

    return 0 if (live_ok and ready_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
