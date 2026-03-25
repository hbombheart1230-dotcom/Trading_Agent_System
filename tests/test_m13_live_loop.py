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
        assert "runtime_fast_path" not in state
        assert "commander_decision" not in state
        assert "strategist_output" not in state
        assert "strategy_policy" not in state
        assert "selected" not in state
        assert "scanner_output" not in state
        assert "monitor_output" not in state
        assert "reasoning_trace" not in state
        assert "reasoning_trace_provenance" not in state
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
        "runtime_fast_path": {"reason": "commander_skip_cached_strategist"},
        "commander_decision": {"strategist_invocation": "SKIP"},
        "strategist_output": {"playbook": "defensive"},
        "strategy_policy": {"schema_version": "strategy_policy.v1"},
        "selected": {"symbol": "000660"},
        "scanner_output": {"selected_symbol": "000660"},
        "monitor_output": {"decision": "NOOP"},
        "reasoning_trace": {"commander_summary": {"summary": "old"}},
        "reasoning_trace_provenance": {"shadow_used": True},
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


def test_run_m13_once_keeps_durable_state_while_clearing_cycle_scoped_artifacts():
    def load_fn(state):
        return state

    def tick_fn(state, dt=None):
        assert state["persisted_state"]["strategist_output_cache"]["output"]["playbook"] == "defensive"
        assert state["symbol"] == "000660"
        assert state["m13_tick_pipeline"] == "integrated_chain"
        assert state["use_exit_policy"] is True
        assert "top_stock" not in state
        assert "monitor_entry_decision_detail" not in state
        assert "monitor_action_decision" not in state
        assert "commander_shadow_runtime" not in state
        assert "intraday_trade_report" not in state
        state["tick_ran"] = True
        return state

    seed = {
        "persisted_state": {
            "strategist_output_cache": {
                "generated_epoch": 1772000000,
                "output": {"playbook": "defensive"},
            }
        },
        "symbol": "000660",
        "m13_tick_pipeline": "integrated_chain",
        "use_exit_policy": True,
        "top_stock": "005930",
        "monitor_entry_decision_detail": {"reason": "old"},
        "monitor_action_decision": {"decision": "NOOP"},
        "commander_shadow_runtime": {"strategist_executed": False},
        "intraday_trade_report": {"ok": True},
    }

    out = run_m13_once(
        seed,
        dt=datetime(2026, 2, 11, 9, 1, tzinfo=KST),
        load_state_fn=load_fn,
        save_state_fn=lambda s: s,
        tick_fn=lambda s, dt=None: tick_fn(s, dt=dt),
        eod_fn=lambda s, dt=None: s,
    )

    assert out["tick_ran"] is True
