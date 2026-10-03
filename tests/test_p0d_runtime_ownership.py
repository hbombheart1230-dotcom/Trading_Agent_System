"""P0-D -- single runtime execution ownership (SQLite/CAS lease), replacing
PID-existence as the authority signal (empirically proven unsafe across
Docker PID namespaces in this repo's own Mock Docker validation).

Test IDs OWN-1..OWN-7 per the P0 Docker Runtime Ownership + Real-Readiness
Hardening task:
  OWN-1: two host processes sharing the same DB file -> exactly one owner.
  OWN-2: two Docker containers -> single owner (covered by real Docker
         re-validation in deploy/trading/ -- this module's CAS logic is
         host/container-agnostic by construction: it never reads a PID from
         anywhere, so the container-vs-host distinction has no code path to
         diverge on. Unit-level equivalent here: two independent store
         instances pointed at the same DB file behave exactly like two
         processes/containers sharing one mounted volume.)
  OWN-3: second runtime cannot delete the first's lease.
  OWN-4: PID namespace / PID reuse is irrelevant -- ownership is keyed
         purely to instance_id, never anything PID-derived.
  OWN-5: clean shutdown (release) safely hands off ownership.
  OWN-6: a hard crash (no release) does not immediately permit a second
         runtime to acquire and execute -- the live lease still blocks it.
  OWN-7: taking over an expired/stale lease requires an explicit takeover
         decision and is flagged as requiring a full readiness recovery
         chain before execution -- expiry alone is never readiness.

Also covers this store's wiring into libs/runtime/live_loop_runner.py::
run_live_loop -- the actual place P0-D's ownership gate must block a
runtime, not just the store in isolation.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from libs.runtime.live_loop_runner import run_live_loop
from libs.runtime.runtime_ownership import (
    SQLiteRuntimeOwnershipStore,
    new_runtime_instance_id,
)

KST = timezone(timedelta(hours=9))


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "runtime_ownership.db")


def test_own1_two_host_processes_single_owner(db_path):
    store_a = SQLiteRuntimeOwnershipStore(db_path)
    store_b = SQLiteRuntimeOwnershipStore(db_path)
    id_a = new_runtime_instance_id()
    id_b = new_runtime_instance_id()

    res_a = store_a.acquire(instance_id=id_a, owner_id="host-proc-a")
    assert res_a.ok is True
    assert res_a.reason == "acquired_no_prior_owner"

    res_b = store_b.acquire(instance_id=id_b, owner_id="host-proc-b")
    assert res_b.ok is False
    assert res_b.reason == "owned_by_other_instance"
    assert res_b.holder["instance_id"] == id_a

    # A remains the sole owner and can keep refreshing.
    refreshed = store_a.refresh(instance_id=id_a)
    assert refreshed.ok is True


def test_own2_two_containers_sharing_volume_single_owner(db_path):
    # Simulated as two independent store instances against the same DB
    # file/mounted-volume path -- the CAS logic has no PID/host-identity
    # branch, so this is behaviorally identical to the real two-container
    # scenario re-validated separately in Docker.
    container_a = SQLiteRuntimeOwnershipStore(db_path)
    container_b = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()

    assert container_a.acquire(instance_id=id_a, boot_id="container-a").ok is True
    result_b = container_b.acquire(instance_id=id_b, boot_id="container-b")
    assert result_b.ok is False
    assert result_b.reason == "owned_by_other_instance"

    status = container_b.status()
    assert status["instance_id"] == id_a
    assert status["boot_id"] == "container-a"


def test_own3_second_runtime_cannot_delete_first_lease(db_path):
    store = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()

    store.acquire(instance_id=id_a)
    # B never held the lease -- release() must be a strict no-op, never a
    # generic "clear whoever is there."
    released = store.release(instance_id=id_b)
    assert released is False

    status = store.status()
    assert status is not None
    assert status["instance_id"] == id_a


def test_own4_pid_namespace_and_pid_reuse_are_irrelevant(db_path):
    # Two different runtime instances can legitimately report the SAME
    # owner_id label (e.g. identical hostname:pid due to PID reuse across
    # independent PID namespaces, exactly the scenario that broke the old
    # pid_exists()-based lock) -- ownership authority must still be scoped
    # strictly to the unforgeable instance_id token, not owner_id.
    store = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()
    same_looking_label = "host:1234"

    res_a = store.acquire(instance_id=id_a, owner_id=same_looking_label)
    assert res_a.ok is True

    res_b = store.acquire(instance_id=id_b, owner_id=same_looking_label)
    assert res_b.ok is False
    assert res_b.reason == "owned_by_other_instance"

    # Also assert the acquire()/refresh()/release() API never accepts or
    # requires a pid-shaped argument at all -- ownership_ownership.py's
    # OwnershipResult carries no pid field.
    assert not hasattr(res_a, "pid")


def test_own5_clean_shutdown_releases_ownership_safely(db_path):
    store = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()

    store.acquire(instance_id=id_a)
    assert store.release(instance_id=id_a) is True
    assert store.status() is None

    res_b = store.acquire(instance_id=id_b)
    assert res_b.ok is True
    assert res_b.reason == "acquired_no_prior_owner"


def test_own6_hard_crash_does_not_immediately_permit_takeover(db_path):
    store = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()

    # A "hard crashes" -- acquires, then never releases, never refreshes
    # again. Its lease is still LIVE (not yet expired).
    store.acquire(instance_id=id_a, lease_seconds=30.0)

    res_b = store.acquire(instance_id=id_b, lease_seconds=30.0)
    assert res_b.ok is False
    assert res_b.reason == "owned_by_other_instance"

    # Even with explicit takeover intent, a still-live lease is never
    # stolen -- allow_stale_takeover only matters once the lease has
    # actually expired.
    res_b_forced = store.acquire(instance_id=id_b, lease_seconds=30.0, allow_stale_takeover=True)
    assert res_b_forced.ok is False
    assert res_b_forced.reason == "owned_by_other_instance"


def test_own7_stale_takeover_requires_explicit_recovery_flag(db_path):
    store = SQLiteRuntimeOwnershipStore(db_path)
    id_a, id_b = new_runtime_instance_id(), new_runtime_instance_id()

    store.acquire(instance_id=id_a, lease_seconds=0.05)
    time.sleep(0.15)

    # Expired, but no explicit takeover -> still fails, not a silent pass.
    res_default = store.acquire(instance_id=id_b)
    assert res_default.ok is False
    assert res_default.reason == "stale_lease_requires_explicit_recovery"
    assert res_default.recovery_required is True

    # A itself must also lose refresh() authority once expired-and-not-yet-
    # taken-over is moot -- but before anyone takes over, A's own refresh
    # (still matching instance_id) is allowed to keep extending its lease
    # (the row is untouched until an explicit takeover happens).
    res_a_refresh = store.refresh(instance_id=id_a)
    assert res_a_refresh.ok is True

    # Now actually let it expire again and have B take over explicitly.
    store.acquire(instance_id=id_a, lease_seconds=0.05)
    time.sleep(0.15)
    res_takeover = store.acquire(instance_id=id_b, allow_stale_takeover=True)
    assert res_takeover.ok is True
    assert res_takeover.reason == "acquired_stale_takeover"
    assert res_takeover.recovery_required is True
    assert res_takeover.generation == 2

    # A has now lost ownership -- its own refresh must fail closed.
    res_a_lost = store.refresh(instance_id=id_a)
    assert res_a_lost.ok is False
    assert res_a_lost.reason == "lost_ownership"

    # B is the sole confirmed owner now.
    status = store.status()
    assert status["instance_id"] == id_b
    assert status["generation"] == 2


# ---------------------------------------------------------------------------
# Wiring into the real live_loop_runner.run_live_loop entry point
# ---------------------------------------------------------------------------


def test_run_live_loop_startup_blocked_by_live_ownership_lease(tmp_path, capsys):
    db_path = str(tmp_path / "runtime_ownership.db")
    other_store = SQLiteRuntimeOwnershipStore(db_path)
    # P1.3-R2: a still-valid foreign lease is no longer refused instantly --
    # startup waits a bounded time (the observed lease's own remaining TTL +
    # margin) and only then fails closed. The foreign owner here is genuinely
    # alive for the whole window (it keeps refreshing, via the injected
    # sleep), so it must never be displaced, nothing may dispatch, and the
    # coarse PID lock must still be released. A tiny lease keeps the bounded
    # window short; the original instant-refusal intent (valid owner is never
    # displaced) is unchanged.
    other_id = new_runtime_instance_id()
    other_store.acquire(instance_id=other_id, owner_id="other-runtime", lease_seconds=0.3)

    def _sleep_while_other_owner_stays_alive(seconds):
        time.sleep(seconds)
        other_store.refresh(instance_id=other_id, lease_seconds=0.3)

    calls = {"count": 0}

    def run_once_fn(state, dt=None):
        calls["count"] += 1
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=run_once_fn,
        sleep_fn=_sleep_while_other_owner_stays_alive,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
        ownership_lease_sec=0.3,
        ownership_wait_poll_sec=0.05,
        ownership_wait_margin_sec=0.1,
    )

    assert rc == 6
    assert calls["count"] == 0
    assert "ownership not acquired" in capsys.readouterr().out
    assert SQLiteRuntimeOwnershipStore(db_path).status()["instance_id"] == other_id
    # The coarse PID lock must not be left held after an ownership-gated
    # refusal -- a later, legitimate retry must still be able to acquire it.
    assert not (tmp_path / "m13.lock").exists()


def test_run_live_loop_stops_when_ownership_lost_mid_loop(tmp_path, capsys, monkeypatch):
    # P1.3-R3: a live process now keeps its lease fresh from a background
    # heartbeat, so a takeover can no longer happen merely because a tick ran
    # long. This test's scenario is a FULLY STALLED process (e.g. SIGSTOP /
    # host freeze: tick AND heartbeat both starved), so the heartbeat thread
    # is deliberately not started here; the heartbeat's own loss handling is
    # covered in tests/test_m13_lease_heartbeat_fix.py.
    import libs.runtime.live_loop_runner as runner_mod

    monkeypatch.setattr(runner_mod.OwnershipHeartbeat, "start", lambda self: self)
    db_path = str(tmp_path / "runtime_ownership.db")
    calls = {"count": 0}

    def run_once_fn(state, dt=None):
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate a second runtime taking over after this instance's
            # very short lease expires mid-tick (e.g. this process stalled
            # or was perceived as crashed) -- a hard-crash-like takeover,
            # not a graceful release.
            time.sleep(0.1)
            attacker = SQLiteRuntimeOwnershipStore(db_path)
            result = attacker.acquire(
                instance_id=new_runtime_instance_id(),
                owner_id="attacker-runtime",
                lease_seconds=60.0,
                allow_stale_takeover=True,
            )
            assert result.ok is True
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=False,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=run_once_fn,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
        ownership_lease_sec=0.05,
    )

    assert rc == 7
    # The tick that was already running under valid authority completed
    # (INV: a signal/ownership-loss never interrupts an in-flight tick),
    # but no SECOND tick was ever allowed to start under lost authority.
    assert calls["count"] == 1
    assert "ownership lost" in capsys.readouterr().out


def test_run_live_loop_releases_ownership_on_clean_completion(tmp_path):
    db_path = str(tmp_path / "runtime_ownership.db")
    store = SQLiteRuntimeOwnershipStore(db_path)

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=lambda state, dt=None: state,
        sleep_fn=lambda _: None,
        ownership_store=store,
    )

    assert rc == 0
    assert store.status() is None


def test_run_live_loop_carries_ownership_result_into_state(tmp_path):
    db_path = str(tmp_path / "runtime_ownership.db")
    captured: dict = {}

    def run_once_fn(state, dt=None):
        captured.update(state.get("runtime_ownership") or {})
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=run_once_fn,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(db_path),
    )

    assert rc == 0
    assert captured.get("recovery_required") is False
    assert captured.get("generation") == 1
    assert captured.get("instance_id")
