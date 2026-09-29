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
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

LOCK_PATH = Path("/app/data/state/m13_live_loop.lock")
STATE_PATH = Path("/app/data/state.json")
INTENT_DB_PATH = Path("/app/data/state/intent_state.db")
OWNERSHIP_DB_PATH = Path("/app/data/state/runtime_ownership.db")
EXECUTION_READINESS_SNAPSHOT_PATH = Path("/app/data/state/execution_readiness.json")
LIVENESS_MAX_HEARTBEAT_AGE_SEC = 120
OWNERSHIP_STALE_WARN_AGE_SEC = 120
EXECUTION_READINESS_SNAPSHOT_MAX_AGE_SEC = 120


def _check_liveness() -> tuple[bool, str]:
    if not LOCK_PATH.exists():
        return False, "lock_file_missing"
    try:
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"lock_file_unreadable:{type(exc).__name__}"
    heartbeat_epoch = int(payload.get("heartbeat_epoch") or payload.get("started_epoch") or 0)
    if heartbeat_epoch <= 0:
        return False, "no_heartbeat_recorded_yet"
    age = int(time.time()) - heartbeat_epoch
    if age > LIVENESS_MAX_HEARTBEAT_AGE_SEC:
        return False, f"heartbeat_stale_age_sec={age}"
    return True, f"heartbeat_age_sec={age}"


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
        sys.path.insert(0, "/app")
        from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore

        store = SQLiteRuntimeOwnershipStore(str(OWNERSHIP_DB_PATH))
        status = store.status()
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
