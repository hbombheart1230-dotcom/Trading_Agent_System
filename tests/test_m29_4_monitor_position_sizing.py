from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node


def test_m29_4_position_sizing_disabled_keeps_default_qty_one():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 100.0},
        "policy": {},
    }
    out = monitor_node(state)
    assert out["intents"][0]["qty"] == 1
    assert out["monitor"]["position_sizing_enabled"] is False


def test_m29_4_position_sizing_enabled_sets_risk_based_qty():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 100.0},
        "policy": {
            "use_position_sizing": True,
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 0.10,
        },
    }
    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "BUY"
    assert out["intents"][0]["qty"] > 1
    assert out["monitor"]["position_sizing_enabled"] is True
    assert out["monitor"]["position_sizing_evaluated"] is True
    assert out["monitor"]["position_sizing_reason"] == "ok"


def test_m29_4_position_sizing_zero_qty_blocks_entry_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"cash": 50.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 100.0},
        "policy": {
            "use_position_sizing": True,
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 0.10,
        },
    }
    out = monitor_node(state)
    assert out["intents"] == []
    assert out["monitor"]["position_sizing_enabled"] is True
    assert out["monitor"]["position_sizing_qty"] == 0
    assert out["monitor"]["position_sizing_reason"] in ("computed_qty_zero", "cash_unavailable", "price_unavailable")
