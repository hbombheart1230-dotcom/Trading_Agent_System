from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node


def _base_state() -> dict:
    return {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 71000.0,
            "features": {"engine_volatility20": 0.02},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 120}],
        },
        "policy": {
            "use_exit_policy": True,
            "exit_policy": {"take_profit_pct": 0.01},
        },
    }


def test_monitor_exit_policy_respects_min_hold_guard(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    out = monitor_node(_base_state())
    assert out["intents"] == []
    assert out["monitor_exit"]["sell_guard_blocked"] is True
    assert "sell_guard_min_hold" in str(out["monitor_exit"]["sell_guard_reason"])
    assert out["monitor_exit"]["triggered"] is False


def test_monitor_exit_requires_confirmation_ticks(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "2")

    s1 = _base_state()
    out1 = monitor_node(s1)
    assert out1["intents"] == []
    assert out1["monitor_exit"]["triggered"] is False
    assert "exit_confirmation_pending:1/2" in str(out1["monitor_exit"]["sell_guard_reason"])

    out2 = monitor_node(out1)
    intents = out2.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert out2["monitor_exit"]["triggered"] is True
