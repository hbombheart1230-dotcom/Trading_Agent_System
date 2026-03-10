from __future__ import annotations

import pytest

from graphs.nodes.monitor_node import monitor_node


@pytest.fixture(autouse=True)
def _relax_monitor_exit_guards(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")


def test_m29_3_monitor_exit_policy_disabled_keeps_buy_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 5, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 96.0},
        "policy": {},
    }

    out = monitor_node(state)
    assert out["intents"][0]["side"] == "BUY"
    assert out["monitor"]["exit_policy_enabled"] is False
    assert out["monitor"]["exit_triggered"] is False


def test_m29_3_monitor_exit_policy_stop_loss_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 5, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 96.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.10,
        },
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["qty"] == 5
    assert out["intents"][0]["meta"]["exit_reason"] == "stop_loss"
    assert out["monitor"]["exit_policy_enabled"] is True
    assert out["monitor"]["exit_triggered"] is True
    assert out["monitor"]["exit_reason"] == "stop_loss"


def test_m29_3_monitor_exit_policy_take_profit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 106.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.10,
            "take_profit_pct": 0.05,
        },
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["qty"] == 2
    assert out["intents"][0]["meta"]["exit_reason"] == "take_profit"
    assert out["monitor"]["exit_triggered"] is True
    assert out["monitor"]["exit_reason"] == "take_profit"
