"""P1.3-R5-B (2026-10-02): a shutdown request (SIGTERM / `docker stop`) that
arrives while a restarting contender is inside R2's bounded ownership wait.

Contract: the contender exits safely and promptly; it does NOT acquire
ownership afterwards (not even if the old lease expires right after the
request), the generation does not transition, no heartbeat starts, no orphan
thread remains, no tick/dispatch happens, and the coarse PID lock it already
holds is released. Legitimate stale takeover (no shutdown request) is covered
by tests/test_m13_ownership_lease_bounded_wait_fix.py and is unchanged.

Deterministic: shutdown is requested from inside the injected sleep function
(i.e. mid-wait); the real signal path is exercised with signal.raise_signal in
the main thread, with the previous handlers restored afterwards.
"""

from __future__ import annotations

import signal
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from libs.runtime.live_loop_runner import ShutdownRequested, run_live_loop
from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore

KST = timezone(timedelta(hours=9))


def _heartbeat_threads():
    return [t for t in threading.enumerate() if t.name == "ownership-heartbeat" and t.is_alive()]


def _run(tmp_path, store, *, sleep_fn, shutdown_flag=None, install_signal_handler=False, margin=1.0):
    ticks = {"n": 0}

    def tick(state, dt=None):
        ticks["n"] += 1
        return state

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=True, sleep_sec=1, session_hard_gate=False,
        lock_path=tmp_path / "m13.lock", lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=tick, sleep_fn=sleep_fn,
        ownership_store=store, ownership_lease_sec=0.3,
        ownership_wait_poll_sec=0.05, ownership_wait_margin_sec=margin,
        shutdown_flag=shutdown_flag, install_signal_handler=install_signal_handler,
    )
    return rc, ticks["n"]


def _other_owner(tmp_path):
    store = SQLiteRuntimeOwnershipStore(path=str(tmp_path / "runtime_ownership.db"))
    other = store.acquire(instance_id="other-live-owner", owner_id="other:1", lease_seconds=0.3, allow_stale_takeover=True)
    assert other.ok and other.generation == 1
    return store


def test_shutdown_during_wait_with_a_live_owner_exits_cleanly_without_acquiring(tmp_path, capsys):
    store = _other_owner(tmp_path)
    flag = ShutdownRequested()
    polls = {"n": 0}

    def sleep_fn(seconds):
        polls["n"] += 1
        time.sleep(seconds)
        store.refresh(instance_id="other-live-owner", lease_seconds=0.3)  # the other owner stays alive
        if polls["n"] == 2:
            flag.request("SIGTERM")

    started = time.time()
    rc, ticks = _run(tmp_path, store, sleep_fn=sleep_fn, shutdown_flag=flag, margin=2.0)
    elapsed = time.time() - started

    out = capsys.readouterr().out
    assert rc == 0, "a requested shutdown during the wait is a clean exit, not an ownership failure"
    assert ticks == 0
    assert "OWNERSHIP_WAIT_ABORTED_SHUTDOWN" in out
    assert "OWNERSHIP_ACQUIRED_AFTER_WAIT" not in out
    assert polls["n"] == 2, "must stop waiting at once, not keep polling after the request"
    assert elapsed < 1.0, "must not sit out the rest of the bounded window"
    status = store.status()
    assert status["instance_id"] == "other-live-owner" and status["generation"] == 1
    assert not _heartbeat_threads()
    assert not (tmp_path / "m13.lock").exists(), "the PID lock acquired before the wait must be released"


def test_shutdown_requested_just_before_the_old_lease_expires_never_acquires_afterwards(tmp_path, capsys):
    store = _other_owner(tmp_path)
    flag = ShutdownRequested()
    polls = {"n": 0}

    def sleep_fn(seconds):
        polls["n"] += 1
        if polls["n"] == 1:
            flag.request("SIGTERM")
            time.sleep(0.45)  # the old owner is NOT refreshed: its lease lapses right after the request
        else:
            time.sleep(seconds)

    rc, ticks = _run(tmp_path, store, sleep_fn=sleep_fn, shutdown_flag=flag, margin=2.0)

    assert rc == 0 and ticks == 0
    assert "OWNERSHIP_WAIT_ABORTED_SHUTDOWN" in capsys.readouterr().out
    status = store.status()
    assert status["instance_id"] == "other-live-owner", "an expired lease must still not be taken after a shutdown request"
    assert status["generation"] == 1
    assert not _heartbeat_threads()


def test_shutdown_requested_before_the_first_attempt_does_not_take_ownership(tmp_path):
    store = SQLiteRuntimeOwnershipStore(path=str(tmp_path / "runtime_ownership.db"))
    flag = ShutdownRequested()
    flag.request("SIGTERM")
    rc, ticks = _run(tmp_path, store, sleep_fn=lambda _s: None, shutdown_flag=flag)
    assert rc == 0 and ticks == 0
    assert store.status() is None, "no ownership row may be created once shutdown is already requested"
    assert not (tmp_path / "m13.lock").exists()


def test_a_real_sigterm_during_the_wait_is_handled_by_the_runtime_not_the_default_action(tmp_path, capsys):
    """The shutdown handler must already be installed while waiting (before
    this fix it was installed only AFTER ownership was acquired, so a SIGTERM
    during the wait hit Python's default action: instant termination with no
    cleanup, the PID lock left behind)."""
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("signal handlers can only be installed from the main thread")
    store = _other_owner(tmp_path)
    previous = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    polls = {"n": 0}

    def sleep_fn(seconds):
        polls["n"] += 1
        time.sleep(seconds)
        store.refresh(instance_id="other-live-owner", lease_seconds=0.3)
        if polls["n"] == 2:
            signal.raise_signal(signal.SIGTERM)

    try:
        rc, ticks = _run(tmp_path, store, sleep_fn=sleep_fn, install_signal_handler=True, margin=2.0)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    assert rc == 0 and ticks == 0
    assert "OWNERSHIP_WAIT_ABORTED_SHUTDOWN" in capsys.readouterr().out
    assert store.status()["generation"] == 1
    assert not (tmp_path / "m13.lock").exists()
    assert not _heartbeat_threads()
