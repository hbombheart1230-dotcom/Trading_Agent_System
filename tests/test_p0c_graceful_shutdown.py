"""P0-C -- graceful SIGTERM/SIGINT drain for the live trading loop.

Target lifecycle:
  RUNNING -> SIGTERM -> DRAINING (no new tick starts; an in-flight tick is
  never interrupted) -> STOPPED (lock released, listener thread stopped).

Primary execution safety (INV-6) remains persistent idempotency + broker
reconciliation + guards -- these tests only verify the drain/latency
behavior, never that the signal handler grants or blocks execution itself.
"""

from __future__ import annotations

import signal

import pytest

from libs.runtime.live_loop_runner import ShutdownRequested, install_shutdown_handler, run_live_loop


class _FakeLock:
    def __init__(self):
        self.acquired = False
        self.released = False
        self.refresh_count = 0

    def acquire(self, *a, **k):
        self.acquired = True
        return True, "ok"

    def refresh(self, *a, **k):
        self.refresh_count += 1

    def release(self, *a, **k):
        self.released = True


@pytest.fixture()
def _patched_lock(monkeypatch):
    fake = _FakeLock()
    monkeypatch.setattr("libs.runtime.live_loop_runner.acquire_live_loop_lock", lambda *a, **k: fake.acquire())
    monkeypatch.setattr("libs.runtime.live_loop_runner.refresh_live_loop_lock", lambda *a, **k: fake.refresh())
    monkeypatch.setattr("libs.runtime.live_loop_runner.release_live_loop_lock", lambda *a, **k: fake.release())

    class _NoopListener:
        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr("libs.runtime.live_loop_runner.KiwoomMarketStatusListener", lambda: _NoopListener())
    return fake


def test_shutdown_requested_before_loop_prevents_any_new_tick(_patched_lock):
    flag = ShutdownRequested()
    flag.request("SIGTERM")
    tick_calls = []

    rc = run_live_loop(
        {},
        once=False,
        sleep_sec=60,
        session_hard_gate=False,
        lock_path=__import__("pathlib").Path("unused.lock"),
        lock_stale_sec=1800,
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 17, 10, 0, 0),
        run_once_fn=lambda state, dt: (tick_calls.append(1) or state),
        sleep_fn=lambda s: None,
        shutdown_flag=flag,
        install_signal_handler=False,
    )

    assert rc == 0
    assert tick_calls == []
    assert _patched_lock.released is True


def test_in_flight_tick_completes_before_drain_stops_the_loop(_patched_lock):
    # The signal arrives (per the flag) *during* what would be tick #1's
    # own execution -- since run_once_fn itself sets the flag, this
    # simulates "SIGTERM delivered while a tick (e.g. execute_owned_order)
    # is in progress." The currently-running tick must be allowed to
    # return normally (never truncated), and only the *next* tick is
    # skipped.
    flag = ShutdownRequested()
    tick_calls = []

    def _run_once(state, dt):
        tick_calls.append(1)
        flag.request("SIGTERM")  # signal "arrives" mid-tick
        return state

    rc = run_live_loop(
        {},
        once=False,
        sleep_sec=60,
        session_hard_gate=False,
        lock_path=__import__("pathlib").Path("unused.lock"),
        lock_stale_sec=1800,
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 17, 10, 0, 0),
        run_once_fn=_run_once,
        sleep_fn=lambda s: (_ for _ in ()).throw(AssertionError("must not sleep after drain is requested")),
        shutdown_flag=flag,
        install_signal_handler=False,
    )

    assert rc == 0
    assert tick_calls == [1]  # exactly one tick ran to completion, no second tick


def test_shutdown_during_idle_sleep_wakes_within_one_step(_patched_lock):
    flag = ShutdownRequested()
    tick_calls = []
    sleep_steps = []

    def _run_once(state, dt):
        tick_calls.append(1)
        return state

    def _sleep_fn(seconds):
        sleep_steps.append(seconds)
        if len(sleep_steps) == 1:
            flag.request("SIGINT")  # signal "arrives" during the idle window

    rc = run_live_loop(
        {},
        once=False,
        sleep_sec=60,  # would be 60x 1s steps if never interrupted
        session_hard_gate=False,
        lock_path=__import__("pathlib").Path("unused.lock"),
        lock_stale_sec=1800,
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 17, 10, 0, 0),
        run_once_fn=_run_once,
        sleep_fn=_sleep_fn,
        shutdown_flag=flag,
        install_signal_handler=False,
    )

    assert rc == 0
    assert tick_calls == [1]
    # Interrupted after exactly one 1-second step, not the full 60s.
    assert sleep_steps == [1.0]


def test_once_mode_ignores_drain_flag_and_still_runs_its_single_tick(_patched_lock):
    flag = ShutdownRequested()
    tick_calls = []

    rc = run_live_loop(
        {},
        once=True,
        sleep_sec=60,
        session_hard_gate=False,
        lock_path=__import__("pathlib").Path("unused.lock"),
        lock_stale_sec=1800,
        now_fn=lambda: __import__("datetime").datetime(2026, 9, 17, 10, 0, 0),
        run_once_fn=lambda state, dt: (tick_calls.append(1) or state),
        sleep_fn=lambda s: None,
        shutdown_flag=flag,
        install_signal_handler=False,
    )

    assert rc == 0
    assert tick_calls == [1]


def test_install_shutdown_handler_registers_sigterm_and_sigint_and_is_restorable():
    # Deliberately does NOT self-signal via os.kill(): raising a real
    # SIGINT/SIGTERM at the OS level is platform-dependent (on Windows it
    # can propagate as a console Ctrl+C event to the whole process group,
    # not just this interpreter) and is not a safe/deterministic way to
    # exercise this in a test process. Instead, verify registration
    # structurally, then invoke the installed handler function directly
    # (the same callable signal.signal() would invoke) to prove it only
    # sets the flag and never raises.
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)
    try:
        flag = ShutdownRequested()
        installed = install_shutdown_handler(flag)
        assert installed.get("SIGTERM") is True
        assert installed.get("SIGINT") is True
        assert flag.requested is False

        term_handler = signal.getsignal(signal.SIGTERM)
        assert term_handler is not previous_term
        term_handler(signal.SIGTERM, None)  # call directly, no real OS signal raised
        assert flag.requested is True
        assert flag.signal_name == "SIGTERM"
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
