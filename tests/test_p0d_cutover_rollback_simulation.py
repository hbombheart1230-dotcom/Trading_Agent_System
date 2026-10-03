"""Real-Docker-Readiness-Audit Section 20 -- host-runtime-to-Docker-runtime
cutover simulation, and its rollback, entirely through
libs.runtime.runtime_ownership + libs.runtime.live_loop_runner.run_live_loop
against one shared, isolated SQLite ownership DB file (simulating the same
persistent-volume-backed data/state/runtime_ownership.db two real processes
-- one host, one container -- would share).

No real Docker container is involved here (this repo's Docker Desktop
crashed with an unrelated host-level stale-socket error during this audit
and could not be recovered after two standard remediation attempts -- see
the audit report). This simulation exercises the EXACT SAME
SQLiteRuntimeOwnershipStore CAS logic a real host-vs-container scenario
would use (already proven container-vs-container-identical in
tests/test_p0d_runtime_ownership.py's OWN-1..OWN-7 and in this session's
earlier live Docker validation): the mechanism has no code path that
branches on "am I in a container," so a second host-side process instance
is behaviorally equivalent to a second containerized instance sharing the
same volume-mounted DB file. No real order, real broker call, or real
production process is touched -- `run_once_fn` is a fake, and every store
is constructed against a pytest tmp_path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from libs.runtime.live_loop_runner import run_live_loop
from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore

KST = timezone(timedelta(hours=9))


def test_section20_cutover_then_rollback_simulation(tmp_path):
    db_path = str(tmp_path / "runtime_ownership.db")
    lock_path_host = tmp_path / "host_m13.lock"
    lock_path_docker = tmp_path / "docker_m13.lock"

    # --- Phase 1: "host runtime running" -----------------------------
    host_calls = {"count": 0}

    def host_run_once(state, dt=None):
        host_calls["count"] += 1
        return state

    rc_host_start = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=lock_path_host,
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=host_run_once,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
    )
    assert rc_host_start == 0
    assert host_calls["count"] == 1
    # run_live_loop(once=True) already released ownership in its own
    # `finally` block on normal completion -- this IS the "graceful stop"
    # + "ownership release" steps of the cutover sequence, verified via the
    # real code path (not asserted separately as a no-op simulation step).
    assert SQLiteRuntimeOwnershipStore(db_path).status() is None

    # --- Phase 2: "Docker runtime start" -> acquire -> reconciliation --
    # -> EXECUTION_READY validation (simulated as: the fake tick itself
    # runs, proving admission was reachable) ---------------------------
    docker_calls = {"count": 0}
    docker_state_seen = {}

    def docker_run_once(state, dt=None):
        docker_calls["count"] += 1
        docker_state_seen.update(state.get("runtime_ownership") or {})
        return state

    rc_docker_start = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=lock_path_docker,
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 6, tzinfo=KST),
        run_once_fn=docker_run_once,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
    )
    assert rc_docker_start == 0
    assert docker_calls["count"] == 1
    # Fresh acquire (host had cleanly released) -- NOT a stale takeover,
    # so no recovery flag needed for this leg of the sequence.
    assert docker_state_seen.get("recovery_required") is False
    assert docker_state_seen.get("generation") == 1

    # --- Rollback: "Docker execution disabled" -> graceful stop ->
    # release -> host runtime restart -> reconciliation ----------------
    # (already-released-by-Docker's-own-finally-block is verified the
    # same way as Phase 1: a status() check after the run.)
    assert SQLiteRuntimeOwnershipStore(db_path).status() is None

    host_restart_calls = {"count": 0}

    def host_restart_run_once(state, dt=None):
        host_restart_calls["count"] += 1
        return state

    rc_host_restart = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=lock_path_host,
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 7, tzinfo=KST),
        run_once_fn=host_restart_run_once,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
    )
    assert rc_host_restart == 0
    assert host_restart_calls["count"] == 1
    assert SQLiteRuntimeOwnershipStore(db_path).status() is None


def test_section20_docker_cannot_start_while_host_still_owns(tmp_path):
    """The other half of the cutover safety property: if the host runtime
    is NOT stopped first (operator error), the Docker side must be
    refused, not silently run concurrently."""
    db_path = str(tmp_path / "runtime_ownership.db")
    host_store = SQLiteRuntimeOwnershipStore(db_path)
    # P1.3-R2: startup now waits a bounded time on a still-valid foreign lease
    # before failing closed (instead of refusing instantly). The host here is
    # genuinely still running -- it keeps refreshing -- so the Docker side
    # must still never displace it. A tiny lease keeps the bounded window
    # short; the safety property under test is unchanged.
    host_store.acquire(instance_id="host-still-running", owner_id="host", lease_seconds=0.3)

    def _sleep_while_host_stays_alive(seconds):
        import time as _time

        _time.sleep(seconds)
        host_store.refresh(instance_id="host-still-running", lease_seconds=0.3)

    calls = {"count": 0}

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "docker_m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=lambda state, dt=None: (calls.__setitem__("count", calls["count"] + 1), state)[1],
        sleep_fn=_sleep_while_host_stays_alive,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
        ownership_lease_sec=0.3,
        ownership_wait_poll_sec=0.05,
        ownership_wait_margin_sec=0.1,
    )

    assert rc == 6
    assert calls["count"] == 0
    # The host's own lease is untouched.
    status = host_store.status()
    assert status is not None
    assert status["instance_id"] == "host-still-running"
