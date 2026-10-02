"""P1.3-R3 (2026-10-02): the SQLite ownership lease is refreshed by a
background heartbeat, independent of tick duration.

Confirmed problem: ownership was only refreshed at tick boundaries, but real
ticks ran median ~36s / p90 ~137s / max ~434s (plus a ~55 minute closeout
tick) against a 30s lease, so a healthy live owner routinely looked stale and a
contender's stale takeover would have succeeded mid-tick.

These tests use tiny leases with real (short) sleeps -- no mocked clocks -- and
cover: a long operation keeps the lease fresh and blocks a contender; owner
loss fails closed and stops the heartbeat; lifecycle (no orphan thread,
stopped before release); crash semantics (heartbeat dies with the process, the
lease expires, R2's bounded wait / stale takeover still work); and that the
interval is derived from the existing lease rather than a second contract.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from libs.runtime.live_loop_runner import (
    OwnershipHeartbeat,
    _acquire_ownership_with_bounded_wait,
    _resolve_heartbeat_interval_sec,
    run_live_loop,
)
from libs.runtime.runtime_ownership import OwnershipResult, SQLiteRuntimeOwnershipStore

KST = timezone(timedelta(hours=9))


def _store(tmp_path):
    return SQLiteRuntimeOwnershipStore(path=str(tmp_path / "runtime_ownership.db"))


def _heartbeat_threads():
    return [t for t in threading.enumerate() if t.name == "ownership-heartbeat" and t.is_alive()]


# ---------------------------------------------------------------- interval --


def test_interval_is_derived_from_the_existing_lease_not_a_second_contract():
    assert _resolve_heartbeat_interval_sec(30.0, None) == pytest.approx(10.0)
    assert _resolve_heartbeat_interval_sec(0.3, None) == pytest.approx(0.1)
    assert _resolve_heartbeat_interval_sec(30.0, 5.0) == 5.0
    with pytest.raises(ValueError):
        _resolve_heartbeat_interval_sec(30.0, 30.0)
    with pytest.raises(ValueError):
        _resolve_heartbeat_interval_sec(30.0, 45.0)


# ------------------------------------------- long operation / live owner ----


def test_without_heartbeat_a_long_operation_loses_the_lease_documenting_the_original_bug(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="owner", lease_seconds=0.3, allow_stale_takeover=True)
    assert first.ok
    time.sleep(0.5)  # a "long tick" with no refresh
    contender = store.acquire(instance_id="contender", lease_seconds=0.3, allow_stale_takeover=True)
    assert contender.ok and contender.generation == 2  # the live owner was displaced


def test_long_operation_keeps_lease_fresh_and_blocks_stale_takeover(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="owner", lease_seconds=0.3, allow_stale_takeover=True)
    hb = OwnershipHeartbeat(
        store, instance_id="owner", generation=first.generation, lease_seconds=0.3
    ).start()
    try:
        contender_results = []
        deadline = time.time() + 1.5  # five times the lease length
        while time.time() < deadline:
            contender_results.append(
                store.acquire(instance_id="contender", lease_seconds=0.3, allow_stale_takeover=True)
            )
            time.sleep(0.03)
        assert contender_results
        assert all((not r.ok) and r.reason == "owned_by_other_instance" for r in contender_results)
        status = store.status()
        assert status["instance_id"] == "owner"
        assert status["generation"] == 1
        assert hb.refresh_count >= 5
        assert not hb.lost
    finally:
        hb.stop()
    assert not hb.running


# ------------------------------------------------ owner loss / fail closed --


class _ScriptedStore:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def refresh(self, *, instance_id, lease_seconds):
        self.calls += 1
        item = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        if isinstance(item, Exception):
            raise item
        return item


def _result(ok, reason="refreshed", generation=1):
    return OwnershipResult(
        ok=ok, reason=reason, instance_id="x", generation=generation,
        acquired_at=0.0, lease_expires_at=0.0, recovery_required=False,
    )


def test_ownership_loss_marks_unsafe_and_stops_without_resurrecting(tmp_path):
    scripted = _ScriptedStore([_result(True), _result(False, "lost_ownership")])
    hb = OwnershipHeartbeat(scripted, instance_id="x", generation=1, lease_seconds=0.3, interval_sec=0.02).start()
    deadline = time.time() + 2.0
    while not hb.lost and time.time() < deadline:
        time.sleep(0.01)
    assert hb.lost and hb.lost_reason == "lost_ownership"
    time.sleep(0.1)
    calls_at_loss = scripted.calls
    time.sleep(0.15)
    assert scripted.calls == calls_at_loss, "a superseded owner must never refresh again"
    assert not hb.running


def test_generation_change_is_treated_as_loss(tmp_path):
    scripted = _ScriptedStore([_result(True, generation=2)])
    hb = OwnershipHeartbeat(scripted, instance_id="x", generation=1, lease_seconds=0.3, interval_sec=0.02).start()
    deadline = time.time() + 2.0
    while not hb.lost and time.time() < deadline:
        time.sleep(0.01)
    assert hb.lost and hb.lost_reason == "generation_changed"
    hb.stop()


def test_persistent_store_errors_beyond_a_full_lease_fail_closed(tmp_path):
    scripted = _ScriptedStore([OSError("db locked")])
    hb = OwnershipHeartbeat(scripted, instance_id="x", generation=1, lease_seconds=0.2, interval_sec=0.02).start()
    deadline = time.time() + 2.0
    while not hb.lost and time.time() < deadline:
        time.sleep(0.01)
    assert hb.lost and hb.lost_reason.startswith("refresh_errors_exceeded_lease")
    hb.stop()


def test_a_transient_store_error_does_not_fail_closed(tmp_path):
    scripted = _ScriptedStore([OSError("blip"), _result(True)])
    hb = OwnershipHeartbeat(scripted, instance_id="x", generation=1, lease_seconds=5.0, interval_sec=0.02).start()
    time.sleep(0.3)
    assert not hb.lost
    assert hb.refresh_count >= 1
    hb.stop()


# --------------------------------------------------------------- lifecycle --


def test_run_live_loop_keeps_lease_through_a_tick_longer_than_the_lease_and_cleans_up(tmp_path):
    store = _store(tmp_path)
    contender_store = _store(tmp_path)
    attempts = []
    stop_poll = threading.Event()

    def _poll():
        while not stop_poll.is_set():
            attempts.append(contender_store.acquire(instance_id="contender", lease_seconds=0.4, allow_stale_takeover=True))
            time.sleep(0.03)

    def long_tick(state, dt=None):
        poller = threading.Thread(target=_poll, daemon=True)
        poller.start()
        time.sleep(1.4)  # > 3x lease_seconds
        stop_poll.set()
        poller.join(timeout=2)
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True, sleep_sec=1, session_hard_gate=False,
        lock_path=tmp_path / "m13.lock", lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=long_tick, sleep_fn=lambda _s: None,
        ownership_store=store, ownership_lease_sec=0.4, install_signal_handler=False,
    )
    assert rc == 0
    assert attempts, "the contender must actually have been polling during the long tick"
    assert all((not r.ok) and r.reason == "owned_by_other_instance" for r in attempts)
    assert not _heartbeat_threads(), "no orphan heartbeat thread after run_live_loop returns"
    assert store.status() is None, "lease released on graceful exit"


def test_run_live_loop_exits_7_when_the_heartbeat_reports_ownership_loss(tmp_path):
    class _HeartbeatOnlyLossStore(SQLiteRuntimeOwnershipStore):
        def refresh(self, *, instance_id, lease_seconds=30.0):
            if threading.current_thread().name == "ownership-heartbeat":
                return _result(False, "lost_ownership")
            return super().refresh(instance_id=instance_id, lease_seconds=lease_seconds)

    store = _HeartbeatOnlyLossStore(path=str(tmp_path / "runtime_ownership.db"))

    class _Flag:
        requested = False
        signal_name = ""

        def request(self, name):
            self.requested = True
            self.signal_name = name

    flag = _Flag()
    ticks = {"n": 0}

    def tick(state, dt=None):
        ticks["n"] += 1
        time.sleep(0.15)  # long enough for the heartbeat to fire and detect the loss
        if ticks["n"] >= 20:
            flag.request("TEST_SAFETY_STOP")
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=False, sleep_sec=1, session_hard_gate=False,
        lock_path=tmp_path / "m13.lock", lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=tick, sleep_fn=lambda _s: None,
        ownership_store=store, ownership_lease_sec=0.3, install_signal_handler=False,
        shutdown_flag=flag,
    )
    assert rc == 7, "heartbeat-detected ownership loss must fail closed like the existing loss path"
    assert ticks["n"] < 20, "no further tick may start once ownership is known lost"
    assert not _heartbeat_threads()


# ------------------------------------------------------------ crash path ---


def test_crash_stops_heartbeat_lease_expires_and_r2_takeover_still_works(tmp_path):
    store = _store(tmp_path)
    first = store.acquire(instance_id="dies", lease_seconds=0.3, allow_stale_takeover=True)
    hb = OwnershipHeartbeat(store, instance_id="dies", generation=first.generation, lease_seconds=0.3).start()
    time.sleep(0.4)
    assert store.status()["instance_id"] == "dies"  # kept alive by the heartbeat
    hb.stop()  # the process dies: the heartbeat dies with it, nothing refreshes any more

    result = _acquire_ownership_with_bounded_wait(
        store, instance_id="restarted", lease_seconds=0.3, allow_stale_takeover=True,
        sleep_fn=time.sleep, wait_poll_sec=0.05, wait_margin_sec=0.2,
    )
    assert result.ok is True
    assert result.generation == 2
    assert result.recovery_required is True
