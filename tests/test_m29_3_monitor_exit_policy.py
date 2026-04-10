from __future__ import annotations

import pytest

from graphs.nodes.monitor_node import monitor_node


def _baseline_applied_policy(*, use_exit_policy: bool, block_buy_when_open_position: bool = True):
    return {
        "monitor": {
            "hold": {"min_hold_seconds": 0},
            "entry": {"block_buy_when_open_position": block_buy_when_open_position},
            "exit": {
                "enabled": use_exit_policy,
                "confirm_ticks": 1,
                "eod_flat": {"enabled": True, "cutoff_min": 10},
            },
        },
        "execution": {"cooldowns": {"sell_sec": 0, "post_exit_sec": 0}},
    }


def test_m29_3_monitor_exit_policy_disabled_keeps_buy_intent(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "false")
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 5, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 96.0},
        "policy": {},
        "applied_policy": _baseline_applied_policy(
            use_exit_policy=False,
            block_buy_when_open_position=False,
        ),
    }

    out = monitor_node(state)
    assert out["intents"] == []
    assert out["monitor"]["exit_policy_enabled"] is False
    assert out["monitor"]["exit_triggered"] is False
    assert out["monitor"]["buy_blocked_open_position"] is False


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
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
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
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["qty"] == 2
    assert out["intents"][0]["meta"]["exit_reason"] == "take_profit"
    assert out["monitor"]["exit_triggered"] is True
    assert out["monitor"]["exit_reason"] == "take_profit"


def test_m29_3_monitor_exit_policy_env_fallback_enables_exit(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 106.0},
        "policy": {
            "stop_loss_pct": 0.10,
            "take_profit_pct": 0.05,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }
    out = monitor_node(state)
    assert out["monitor"]["exit_policy_enabled"] is True
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
