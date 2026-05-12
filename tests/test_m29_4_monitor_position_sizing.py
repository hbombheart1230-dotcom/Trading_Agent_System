from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node


def _entry_breakout_rows() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]


def test_m29_4_position_sizing_disabled_keeps_default_qty_one():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "price": 101.8, "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "minute_ohlcv_by_symbol": {"AAA": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 101.8},
        "policy": {},
    }
    out = monitor_node(state)
    assert out["intents"][0]["qty"] == 1
    assert out["monitor"]["position_sizing_enabled"] is False


def test_m29_4_position_sizing_enabled_sets_risk_based_qty():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "price": 101.8, "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "minute_ohlcv_by_symbol": {"AAA": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 101.8},
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


def test_m29_4_commander_position_sizing_policy_enables_scaled_entry_qty():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "price": 101.8, "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "minute_ohlcv_by_symbol": {"AAA": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 101.8},
        "applied_policy": {
            "monitor": {
                "entry": {
                    "position_sizing": {
                        "enabled": True,
                        "risk_per_trade_ratio": 0.01,
                        "stop_loss_pct": 0.03,
                        "position_notional_ratio": 0.50,
                        "max_position_qty": 10,
                        "max_position_notional": 1_000_000,
                        "min_position_qty": 1,
                        "lot_size": 1,
                    }
                }
            }
        },
        "policy": {},
    }
    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "BUY"
    assert out["intents"][0]["qty"] == 10
    assert out["monitor"]["position_sizing_enabled"] is True
    assert out["monitor"]["position_sizing_evaluated"] is True
    assert out["monitor"]["position_sizing_reason"] == "ok"
    sizing = out["intents"][0]["meta"]["sizing"]
    assert float(sizing["inputs"]["max_position_notional"]) == 1_000_000.0


def test_m29_4_position_sizing_uses_entry_structure_stop_loss():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "price": 101.8, "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "minute_ohlcv_by_symbol": {"AAA": _entry_breakout_rows()},
        "portfolio_snapshot": {"cash": 1_000_000.0, "positions": []},
        "market_snapshot": {"symbol": "AAA", "price": 101.8},
        "policy": {
            "use_position_sizing": True,
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 1.0,
            "max_position_qty": 10_000,
        },
    }

    out = monitor_node(state)

    sizing = out["intents"][0]["meta"]["sizing"]
    inputs = sizing["inputs"]
    assert out["monitor"]["position_sizing_reason"] == "ok"
    assert int(out["intents"][0]["qty"]) > 327
    assert float(inputs["stop_loss_pct"]) < 0.03
    assert inputs["stop_loss_source"]
    assert inputs["invalidation_price"] is not None
    assert out["monitor"]["position_sizing_stop_loss_source"] == inputs["stop_loss_source"]


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
