from datetime import datetime, timezone, timedelta

from graphs.pipelines.m13_live_loop import run_m13_once

KST = timezone(timedelta(hours=9))


def test_run_m13_once_calls_in_order():
    calls = []

    def load_fn(state):
        calls.append("load")
        state["loaded"] = True
        return state

    def tick_fn(state, dt=None):
        calls.append("tick")
        state["tick_ran"] = True
        state["dt_ts"] = int((dt or datetime(2026, 2, 11, 9, 0, tzinfo=KST)).timestamp())
        return state

    def eod_fn(state, dt=None):
        calls.append("eod")
        state["eod_checked"] = True
        return state

    def save_fn(state):
        calls.append("save")
        state["saved"] = True
        return state

    dt = datetime(2026, 2, 11, 9, 1, tzinfo=KST)
    out = run_m13_once({}, dt=dt, load_state_fn=load_fn, save_state_fn=save_fn, tick_fn=lambda s, dt=None: tick_fn(s, dt=dt), eod_fn=lambda s, dt=None: eod_fn(s, dt=dt))

    assert calls == ["load", "tick", "eod", "save"]
    assert out["loaded"] and out["tick_ran"] and out["eod_checked"] and out["saved"]
    assert out["dt_ts"] == int(dt.timestamp())


def test_run_m13_once_clears_per_run_fields_before_tick():
    def load_fn(state):
        return state

    def tick_fn(state, dt=None):
        # per-run keys should be cleared before tick executes
        assert "run_id" not in state
        assert "decision_packet" not in state
        assert "decision_trace" not in state
        assert "execution" not in state
        state["tick_ran"] = True
        return state

    def eod_fn(state, dt=None):
        return state

    def save_fn(state):
        return state

    seed = {
        "run_id": "old",
        "decision_packet": {"intent": {"action": "NOOP"}},
        "decision_trace": {"strategy": "old"},
        "execution": {"allowed": True},
    }
    out = run_m13_once(
        seed,
        dt=datetime(2026, 2, 11, 9, 1, tzinfo=KST),
        load_state_fn=load_fn,
        save_state_fn=save_fn,
        tick_fn=lambda s, dt=None: tick_fn(s, dt=dt),
        eod_fn=lambda s, dt=None: eod_fn(s, dt=dt),
    )
    assert out["tick_ran"] is True
