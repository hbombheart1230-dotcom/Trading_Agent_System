"""2026-09-05 PRE-STEP5C cleanup follow-up: Q10 Index observation
collector wired into the actual trading-day runtime path.

The previous turn's "Q10 09:30/10:00/CLOSE CAPTURE: PASS" was unit/
integration level only -- libs/market/q10_index_observation_collector.py's
`run_due_slots()` was tested directly, but nothing proved the standalone
collector *process* (scripts/run_q10_index_observation_collector.py,
launched by scripts/start_trading_day.py's SHADOW_LOOPS, exactly like
every other shadow loop) actually calls into it on a realistic poll
schedule. This file closes that gap two ways:

1. Orchestration-level: `main()` is proven to call `run_due_slots` once
   per --loop iteration with the right day, and to stop exactly when
   `should_stop_shadow_loop` says to (the same shared contract every
   other shadow loop in this repo uses) -- without actually sleeping or
   spawning a real subprocess.
2. End-to-end poll simulation: the exact dispatch function the script
   calls (`run_due_slots`) is driven through a simulated trading-day poll
   sequence (09:00 -> 09:31 -> 09:31 again -> 09:35 -> 10:01 -> 15:30
   [fails] -> 15:36 [closeout succeeds] -> 15:40) and the underlying
   live-fetch call count is asserted at each step, proving 09:30/10:00/
   CLOSE dispatch, duplicate-poll idempotency, late-poll tolerance,
   honest CLOSE failure, and the bounded one-shot closeout re-query all
   hold under the actual polling pattern the collector process uses.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.run_q10_index_observation_collector as runner_mod
from libs.market.q10_index_observation_collector import observation_for_slot, run_due_slots


KST = ZoneInfo("Asia/Seoul")
DAY = "2026-09-05"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 5, hour, minute, tzinfo=KST)


# --- Orchestration: main() actually dispatches to run_due_slots --------


def test_main_without_loop_calls_run_due_slots_exactly_once(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(runner_mod, "run_due_slots", lambda **kwargs: calls.append(kwargs) or [])
    monkeypatch.setattr(runner_mod.sys, "argv", ["run_q10_index_observation_collector.py", "--day", DAY])

    exit_code = runner_mod.main()

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["day"] == DAY


def test_main_with_loop_polls_until_should_stop_shadow_loop_says_stop(monkeypatch) -> None:
    """T2/T3/T4 (orchestration half): with --loop, main() must keep calling
    run_due_slots on every tick -- this is what actually causes the
    09:30/10:00/CLOSE slots to be reached over the course of a trading
    day -- and must stop exactly when the shared shadow-loop contract
    (should_stop_shadow_loop) says to, never sleeping for real."""
    calls: list[dict] = []
    stop_after = 3

    def _fake_run_due_slots(**kwargs):
        calls.append(kwargs)
        return []

    def _fake_should_stop(*, day: str, **_kwargs) -> bool:
        assert day == DAY
        return len(calls) >= stop_after

    sleeps: list[float] = []

    monkeypatch.setattr(runner_mod, "run_due_slots", _fake_run_due_slots)
    monkeypatch.setattr(runner_mod, "should_stop_shadow_loop", _fake_should_stop)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        runner_mod.sys, "argv", ["run_q10_index_observation_collector.py", "--day", DAY, "--loop", "--poll-sec", "30"]
    )

    exit_code = runner_mod.main()

    assert exit_code == 0
    assert len(calls) == stop_after
    assert all(call["day"] == DAY for call in calls)
    # Slept between iterations but never longer than requested, and never
    # blocked the test with a real sleep.
    assert len(sleeps) == stop_after - 1
    assert all(seconds == 30.0 for seconds in sleeps)


def test_main_exception_from_run_due_slots_does_not_hang_or_swallow(monkeypatch) -> None:
    """T10: this collector is launched as its own OS subprocess by
    start_trading_day.py's SHADOW_LOOPS -- identical isolation to every
    other shadow loop (run_baseline_samsung_hynix.py,
    run_opportunity_engine_shadow.py, run_baseline_btc_woori_tech.py),
    none of which wrap their inner call in try/except either. A crash here
    ends only this subprocess; the watchdog cycle in start_trading_day.py
    detects it is no longer running for the day and relaunches it on its
    next pass. It must never propagate into or block the caller in a way
    that could affect the main live trading loop (a separate process
    entirely)."""
    def _boom(**kwargs):
        raise RuntimeError("simulated unexpected failure")

    monkeypatch.setattr(runner_mod, "run_due_slots", _boom)
    monkeypatch.setattr(runner_mod.sys, "argv", ["run_q10_index_observation_collector.py", "--day", DAY])

    try:
        runner_mod.main()
        raised = False
    except RuntimeError:
        raised = True

    # The exception propagates out of this one subprocess's main() (same
    # as every other shadow loop) rather than being silently swallowed --
    # but it stays confined to this process, never touching commander
    # runtime state, locks, or the live loop.
    assert raised is True


# --- End-to-end poll simulation through the real dispatch function ------


def test_realistic_poll_sequence_covers_0930_1000_close_idempotency_and_closeout(tmp_path: Path) -> None:
    """T2-T9 combined: drives libs.market.q10_index_observation_collector's
    real run_due_slots() -- the exact function the collector process calls
    every tick -- through a realistic, slightly-imperfect poll sequence."""
    root = tmp_path / "q10_index_observations"
    live_calls: list[str] = []

    def _ok_capture(**kwargs):
        live_calls.append("ok")
        return {
            "status": "ok",
            "source": "kiwoom.ka20009",
            "indices": {"KOSPI": {"current": 3050.0}, "KOSDAQ": {"current": 810.0}},
        }

    def _failing_capture(**kwargs):
        live_calls.append("fail")
        return {"status": "unavailable", "source": "kiwoom.ka20009", "indices": {}, "error": "network_error"}

    # Poll tick 1: 09:00 -- before the 09:30 slot, nothing due yet.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 0), capture=_ok_capture)
    assert len(live_calls) == 0
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] == "MISSING"

    # Poll tick 2: 09:31 -- T2, 09:30 slot dispatch actually fires.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 31), capture=_ok_capture)
    assert len(live_calls) == 1
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] == "OBSERVED_UNVERIFIED_TIME"

    # Poll tick 3: 09:31 again (duplicate poll, e.g. process restarted) --
    # T5, must NOT re-fetch a slot that already has a real observation.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 31), capture=_ok_capture)
    assert len(live_calls) == 1

    # Poll tick 4: 09:35 -- T6, a late poll for the SAME still-due slot
    # would also be tolerated (simulated separately by starting the whole
    # sequence late; here we confirm no re-fetch since 09:30 is settled).
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(9, 35), capture=_ok_capture)
    assert len(live_calls) == 1

    # Poll tick 5: 10:01 -- T3, 10:00 slot dispatch fires on the next poll
    # after its scheduled time, not requiring an exact-timestamp hit.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(10, 1), capture=_ok_capture)
    assert len(live_calls) == 2
    assert observation_for_slot(DAY, "10:00", root=root)["availability"] == "OBSERVED_UNVERIFIED_TIME"

    # T9: 10:00 having real data must never leak into CLOSE.
    assert observation_for_slot(DAY, "15:30", root=root)["availability"] == "MISSING"

    # Poll tick 6: 15:30 -- T4, CLOSE slot dispatch fires, but the live
    # fetch fails -- T7, must stay honestly MISSING/PENDING, never a
    # fabricated or stale (e.g. 10:00's) substitute value.
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 30), capture=_failing_capture)
    assert live_calls[-1] == "fail"
    assert observation_for_slot(DAY, "15:30", root=root)["availability"] == "MISSING"
    assert observation_for_slot(DAY, "15:30", root=root)["indices"] == {}

    # Poll tick 7: 15:36 -- past the grace period, still missing -- T8,
    # the bounded one-shot closeout re-query fires and this time succeeds.
    calls_before = len(live_calls)
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 36), capture=_ok_capture, closeout_grace_sec=300)
    assert len(live_calls) == calls_before + 1
    close_row = observation_for_slot(DAY, "15:30", root=root)
    assert close_row["availability"] == "CLOSE_UNVERIFIED"
    assert close_row["closeout_requeried"] is True

    # Poll tick 8: 15:40 -- further polling after CLOSE is settled must
    # never issue another live fetch (T8, bounded to exactly one requery).
    calls_before = len(live_calls)
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(15, 40), capture=_ok_capture, closeout_grace_sec=300)
    assert len(live_calls) == calls_before


def test_late_process_start_attempts_each_due_slot_once_but_honors_capture_window(tmp_path: Path) -> None:
    """2026-09-05 FIX 2 (Codex REJECT, item 1): the ORIGINAL version of
    this test asserted that a process starting at 10:05 could backfill
    09:30 as AVAILABLE using the 10:05 current price -- that is exactly
    the defect Codex's independent re-audit caught (requested_slot vs
    actual observation time conflated). Corrected expectation: every due
    slot still gets exactly one primary attempt (still only 2 live calls,
    never re-attempted), but 09:30 (35 minutes late, outside the 5-minute
    capture window) must be LATE_MISSED, never AVAILABLE -- while 10:00
    (5 minutes late, exactly at the window boundary) is still accepted."""
    root = tmp_path / "q10_index_observations"
    calls: list[str] = []

    def _ok_capture(**kwargs):
        calls.append("ok")
        return {
            "status": "ok", "source": "kiwoom.ka20009",
            "indices": {
                "KOSPI": {"current": 3050.0, "current_date": DAY.replace("-", "")},
                "KOSDAQ": {"current": 810.0, "current_date": DAY.replace("-", "")},
            },
        }

    # First poll ever, already at 10:05 -- both 09:30 and 10:00 are due.
    captured = run_due_slots(day=DAY, root=root, now_fn=lambda: _at(10, 5), capture=_ok_capture)

    assert len(calls) == 2
    assert {row["requested_slot"] for row in captured} == {"09:30", "10:00"}
    assert observation_for_slot(DAY, "09:30", root=root)["availability"] == "LATE_MISSED"
    assert observation_for_slot(DAY, "10:00", root=root)["availability"] == "OBSERVED_UNVERIFIED_TIME"

    # A subsequent poll at the same/later time must not re-fetch either
    # (LATE_MISSED counts as "already attempted", not retried by the
    # primary per-slot loop -- see run_due_slots's already_attempted check).
    run_due_slots(day=DAY, root=root, now_fn=lambda: _at(10, 6), capture=_ok_capture)
    assert len(calls) == 2
