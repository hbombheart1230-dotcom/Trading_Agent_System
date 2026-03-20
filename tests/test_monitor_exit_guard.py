from __future__ import annotations

from graphs.nodes.monitor_node import _extract_monitor_strategy_frame, monitor_node


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


def test_monitor_exit_cooldown_suppresses_duplicate_sell_intents(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    base = _base_state()
    base["tick_ts"] = 1772850000
    out1 = monitor_node(base)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "SELL"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    reason = str((out2.get("monitor_exit") or {}).get("sell_guard_reason") or "")
    assert "sell_guard_pending_exit_lock" in reason


def test_monitor_exit_cooldown_applies_after_position_closed(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    s1 = _base_state()
    s1["tick_ts"] = 1772850000
    out1 = monitor_node(s1)
    assert (out1.get("intents") or [{}])[0].get("side") == "SELL"

    s2 = dict(out1)
    s2["portfolio_snapshot"] = {"cash": 0.0, "positions": []}
    s2["use_position_sizing"] = True
    s2["tick_ts"] = 1772850001
    out2 = monitor_node(s2)
    assert out2.get("intents") == []

    s3 = dict(out2)
    s3["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 800}],
    }
    s3["tick_ts"] = 1772850002
    out3 = monitor_node(s3)
    assert out3.get("intents") == []
    reason = str((out3.get("monitor_exit") or {}).get("sell_guard_reason") or "")
    assert "sell_guard_cooldown" in reason
    assert (out3.get("monitor_exit") or {}).get("sell_cooldown_blocked") is True


def test_monitor_does_not_select_symbol_when_selected_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": None,
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    assert (out.get("monitor_output") or {}).get("selected_symbol") is None


def test_monitor_blocks_new_buy_when_open_position_guard_enabled(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}],
        },
        "policy": {},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    mon = out.get("monitor") or {}
    assert mon.get("open_position_count") == 1
    assert mon.get("buy_blocked_open_position") is True
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "buy_blocked_open_position"


def test_monitor_waits_when_open_position_guard_disabled_but_minute_candles_missing(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}],
        },
        "policy": {},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("buy_blocked_open_position") is False
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "minute_candle_missing"
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "minute_candle_missing"


def test_monitor_requires_intraday_entry_confirmation_when_ohlcv_available(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")
    monkeypatch.setenv("MONITOR_ENTRY_INTENT_COOLDOWN_SEC", "0")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {},
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is True
    assert monitor.get("entry_triggered") is True
    assert monitor.get("entry_pattern") == "breakout_vwap_hold"


def test_monitor_skips_buy_when_intraday_entry_signal_not_confirmed(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")
    monkeypatch.setenv("MONITOR_ENTRY_INTENT_COOLDOWN_SEC", "0")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 103.2,
            "features": {"engine_vwap_distance": 0.020, "engine_volume_spike20": 1.6},
        },
        "ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 103.4, "low": 101.0, "close": 103.2, "volume": 2500, "vwap": 101.1},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {},
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is True
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "too_extended_from_vwap"
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "too_extended_from_vwap"


def test_monitor_waits_when_minute_candles_missing(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")
    monkeypatch.setenv("MONITOR_ENTRY_INTENT_COOLDOWN_SEC", "0")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.2,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.3},
        },
        "ohlcv_by_symbol": {},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {},
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    monitor = out.get("monitor") or {}
    assert monitor.get("entry_evaluated") is False
    assert monitor.get("entry_triggered") is False
    assert monitor.get("entry_reason") == "minute_candle_missing"
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "minute_candle_missing"


def test_monitor_blocks_reentry_during_post_exit_cooldown(monkeypatch):
    monkeypatch.setenv("POST_EXIT_COOLDOWN_SEC", "600")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "tick_ts": 2000,
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "persisted_state": {"last_trade_side": "SELL", "last_trade_epoch": 1500},
        "policy": {},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    mon = out.get("monitor") or {}
    assert mon.get("buy_blocked_post_exit_cooldown") is True
    assert mon.get("post_exit_cooldown_remaining_sec") == 100
    assert (out.get("monitor_output") or {}).get("entry_exit_reason") == "post_exit_cooldown"


def test_monitor_entry_intent_cooldown_suppresses_duplicate_buy_intents(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")
    monkeypatch.setenv("MONITOR_ENTRY_INTENT_COOLDOWN_SEC", "60")

    state = {
        "tick_ts": 1772850000,
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 101.8,
            "features": {"engine_vwap_distance": 0.004, "engine_volume_spike20": 1.8},
        },
        "ohlcv_by_symbol": {
            "BBB": [
                {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
                {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
                {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
                {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
                {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
                {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
            ]
        },
        "portfolio_snapshot": {"cash": 2_000_000.0, "positions": []},
        "policy": {},
    }

    out1 = monitor_node(state)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "BUY"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    monitor2 = out2.get("monitor") or {}
    assert monitor2.get("entry_guard_blocked") is True
    assert "entry_guard_cooldown" in str(monitor2.get("entry_guard_reason") or "")


def test_monitor_falls_back_to_held_symbol_for_exit_when_selected_has_no_position(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    assert (out.get("monitor") or {}).get("exit_symbol_fallback") is True
    assert (out.get("monitor_exit") or {}).get("selected_symbol") == "BBB"
    assert (out.get("monitor_exit") or {}).get("symbol") == "AAA"


def test_monitor_uses_position_mark_price_when_quote_unavailable(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        # quote intentionally unavailable for AAA to force position mark fallback.
        "market_snapshot": {"symbol": "BBB", "price": 120.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    assert str((out.get("monitor_exit") or {}).get("reason") or "") == "stop_loss"
    assert (out.get("monitor_exit") or {}).get("exit_symbol_fallback") is True
    assert (out.get("monitor_exit") or {}).get("price_source") == "position.avg_plus_unrealized"


def test_monitor_prefers_position_current_price_over_derived_mark(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "market_snapshot": {"symbol": "BBB", "price": 120.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)

    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0
    assert "position.current_price" in str(exit_info.get("price_source_policy") or "")


def test_monitor_prefers_position_current_price_over_selected_same_symbol_price(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "AAA",
            "price": 101.0,
            "features": {"skill_quote_price": 101.0},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0


def test_monitor_prefers_position_current_price_over_market_snapshot_when_quote_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {
                    "symbol": "AAA",
                    "qty": 3,
                    "avg_price": 100.0,
                    "current_price": 96.0,
                    "unrealized_pnl": -15.0,
                    "hold_sec": 900,
                }
            ],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "position.current_price"
    assert float(exit_info.get("price") or 0.0) == 96.0


def test_monitor_uses_feature_engine_snapshot_for_held_symbol_fallback(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 95.0},
        "feature_engine": {
            "by_symbol": {
                "AAA": {
                    "atr14": 2.5,
                    "volatility20": 0.03,
                    "vwap_distance": -0.01,
                    "signal_score": -0.4,
                    "regime": "trend",
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert exit_info.get("symbol") == "AAA"
    assert exit_info.get("feature_source") == "feature_engine.by_symbol"
    assert exit_info.get("price_source") == "market_snapshot"


def test_monitor_uses_ohlcv_derived_features_for_held_symbol_fallback(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    candles = []
    px = 100.0
    for _ in range(40):
        candles.append(
            {
                "open": px,
                "high": px + 1.0,
                "low": px - 1.0,
                "close": px,
                "volume": 100000,
            }
        )
        px += 0.2

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "ohlcv_by_symbol": {"AAA": candles},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert exit_info.get("symbol") == "AAA"


def test_monitor_can_approve_overnight_carry_near_close(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 100.6,
            "features": {
                "engine_volatility20": 0.02,
                "engine_trend_strength": 0.22,
                "engine_vwap_distance": 0.002,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 3600}],
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {"minutes_to_close": 8},
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "balanced",
        "persisted_state": {},
    }

    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("eod_carry_evaluated") is True
    assert exit_info.get("eod_carry_approved") is True
    assert exit_info.get("monitor_reason") == "eod_carry_approved"
    persisted = out.get("persisted_state") or {}
    overnight = persisted.get("overnight_decision_by_symbol") or {}
    assert overnight.get("005930", {}).get("approved") is True


def test_monitor_flattens_near_close_when_overnight_carry_is_not_approved(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_USE_EOD_FLAT", "true")
    monkeypatch.setenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "10")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "005930",
            "price": 99.1,
            "features": {
                "engine_volatility20": 0.02,
                "engine_trend_strength": -0.15,
                "engine_vwap_distance": -0.009,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 3600}],
        },
        "policy": {"use_exit_policy": True, "exit_policy": {"use_eod_flat": True, "eod_flat_cutoff_min": 10}},
        "market_context": {"minutes_to_close": 8},
        "playbook": "defensive",
        "monitor_guidance": "defensive_exit",
        "risk_tone": "conservative",
        "persisted_state": {},
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("eod_carry_evaluated") is True
    assert exit_info.get("eod_carry_approved") is False
    assert str(exit_info.get("reason") or "") == "eod_flat"


def test_monitor_does_not_use_other_symbol_selected_price_for_held_position(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "BBB",
            "price": 120.0,
            "features": {"skill_quote_price": 120.0, "engine_vwap_distance": 0.02},
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("symbol") == "AAA"
    assert exit_info.get("price_source") == "market.quote.price"
    assert float(exit_info.get("price") or 0.0) == 95.0


def test_monitor_prefers_quote_price_over_stale_selected_feature_quote(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {
            "symbol": "AAA",
            "price": 101.0,
            "features": {
                "skill_quote_price": 101.0,
                "engine_vwap_distance": 0.02,
            },
        },
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "skill_results": {
            "market.quote": {
                "data": {
                    "AAA": {
                        "symbol": "AAA",
                        "price": 95.0,
                        "change_pct": -5.0,
                        "volume": 123456,
                        "value": 123456789.0,
                    }
                }
            }
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.03},
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("price_source") == "market.quote.price"
    assert float(exit_info.get("price") or 0.0) == 95.0


def test_monitor_backfills_peak_price_from_open_position_when_missing(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 3, "avg_price": 100.0, "hold_sec": 900}],
        },
        "persisted_state": {},
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.20, "take_profit_pct": 0.20},
    }

    out = monitor_node(state)
    peak_map = ((out.get("persisted_state") or {}).get("position_peak_price") or {})
    assert float(peak_map.get("AAA") or 0.0) == 100.0
    exit_info = out.get("monitor_exit") or {}
    assert float(exit_info.get("peak_price") or 0.0) == 100.0


def test_monitor_selects_held_symbol_with_triggered_exit_among_multiple_positions(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "BBB"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [
                {"symbol": "AAA", "qty": 2, "avg_price": 100.0, "unrealized_pnl": -20.0, "hold_sec": 900},
                {"symbol": "CCC", "qty": 5, "avg_price": 100.0, "unrealized_pnl": 0.0, "hold_sec": 900},
            ],
        },
        "policy": {"use_exit_policy": True, "stop_loss_pct": 0.05, "take_profit_pct": 0.05},
    }
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert intents[0]["symbol"] == "AAA"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "stop_loss"
    assert bool(exit_info.get("exit_symbol_fallback")) is True


def test_monitor_ignores_invalid_live_like_positions(monkeypatch):
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "005930"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "A0082N0", "qty": 1, "avg_price": 63200.0, "hold_sec": 900}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert intents[0]["symbol"] == "005930"
    mon = out.get("monitor") or {}
    assert mon.get("open_position_count") == 0
    exit_info = out.get("monitor_exit") or {}
    assert bool(exit_info.get("exit_symbol_fallback")) is False
    assert int(exit_info.get("qty") or 0) == 0


def test_monitor_applies_exit_policy_env_overrides(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str((out.get("monitor_exit") or {}).get("reason") or "") == "max_hold"


def test_monitor_stop_take_env_are_fallback_only(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA", "price": 103.0},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "market_snapshot": {"symbol": "AAA", "price": 103.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.05,
        },
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.05
    assert float(effective.get("take_profit_pct") or 0.0) >= 0.05
    assert str(exit_info.get("reason") or "") == "hold"


def test_monitor_max_hold_respects_min_hold_guard(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    assert out.get("intents") == []
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is False
    assert exit_info.get("sell_guard_blocked") is False
    assert exit_info.get("min_hold_blocked") is False
    assert str(exit_info.get("reason") or "") == "hold"
    assert exit_info.get("monitor_reason") == "hold"
    thresholds = exit_info.get("thresholds") or {}
    assert int(thresholds.get("max_hold_sec") or 0) == 600
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "max_hold_sec_raised_to_min_hold:60->600" in adjustments
    assert exit_info.get("hard_exit") is False


def test_monitor_max_hold_requires_confirmation_ticks(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "2")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 120}],
        },
        "policy": {"use_exit_policy": True},
    }
    out1 = monitor_node(state)
    assert out1.get("intents") == []
    exit1 = out1.get("monitor_exit") or {}
    assert exit1.get("triggered") is False
    assert "exit_confirmation_pending:1/2" in str(exit1.get("sell_guard_reason") or "")
    assert exit1.get("hard_exit") is False

    out2 = monitor_node(out1)
    intents = out2.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str((out2.get("monitor_exit") or {}).get("reason") or "") == "max_hold"
    assert bool((out2.get("monitor_exit") or {}).get("hard_exit")) is False


def test_monitor_harmonizes_max_hold_when_shorter_than_min_hold(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "60")

    state = {
        "plan": {"thesis": "test"},
        "selected": {"symbol": "AAA"},
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "AAA", "qty": 1, "avg_price": 100.0, "hold_sec": 620}],
        },
        "policy": {"use_exit_policy": True},
    }
    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("triggered") is True
    assert str(exit_info.get("reason") or "") == "max_hold"
    thresholds = exit_info.get("thresholds") or {}
    assert int(thresholds.get("max_hold_sec") or 0) == 600
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "max_hold_sec_raised_to_min_hold:60->600" in adjustments


def test_monitor_emergency_exit_bypasses_min_hold_and_confirmation(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 30}],
    }
    state["emergency_halt"] = True
    out = monitor_node(state)

    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert exit_info.get("emergency_exit") is True
    assert exit_info.get("monitor_reason") == "emergency_exit_signal"


def test_monitor_does_not_execute_orders_directly(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["execution_result"] = {"status": "unmodified"}
    out = monitor_node(state)
    assert out.get("execution_result") == {"status": "unmodified"}
    assert (out.get("monitor") or {}).get("has_intent") in (True, False)


def test_monitor_applies_strategic_frame_guidance_to_exit_guards(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "600")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "300")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "2")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 300}],
    }
    state["strategist_output"] = {
        "monitor_guidance": "quick_take_profit",
        "risk_tone": "aggressive",
        "trade_aggressiveness": "high",
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"

    exit_info = out.get("monitor_exit") or {}
    assert int(exit_info.get("min_hold_sec") or 0) == 240
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1
    assert str(exit_info.get("monitor_guidance") or "") == "quick_take_profit"
    assert str(exit_info.get("risk_tone") or "") == "aggressive"
    assert str(exit_info.get("trade_aggressiveness") or "") == "high"


def test_monitor_uses_strategist_monitor_policy_over_env(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "1200")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "600")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 200}],
    }
    state["strategist_output"] = {
        "monitor_policy": {
            "min_hold_seconds": 0,
            "sell_cooldown_seconds": 30,
            "exit_confirm_ticks": 1,
        },
        "monitor_guidance": "quick_take_profit",
        "risk_tone": "normal",
        "trade_aggressiveness": "medium",
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    # Effective values come from strategist monitor_policy first, then strategy-frame adjustments.
    assert int(exit_info.get("min_hold_sec") or 0) <= 1
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1


def test_monitor_applies_strategist_exit_policy_over_env(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
    }
    state["strategist_output"] = {
        "playbook": "breakout",
        "monitor_guidance": "hold_through_noise",
        "risk_tone": "aggressive",
        "trade_aggressiveness": "high",
        "exit_policy": {
            "stop_loss_pct": 0.025,
            "take_profit_pct": 0.060,
            "trailing_stop_pct": 0.020,
        },
    }

    out = monitor_node(state)
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.025
    assert float(effective.get("take_profit_pct") or 0.0) >= 0.060
    assert float(effective.get("trailing_stop_pct") or 0.0) >= 0.020
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "strategist_exit_policy_override" in adjustments


def test_monitor_uses_strategy_policy_monitor_contract(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.01")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.01")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "1200")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "600")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "3")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 200}],
    }
    state["selected"]["price"] = 68000.0
    state["strategist_output"] = {
        "strategy_policy": {
            "market_policy": {
                "playbook": "breakout",
                "monitor_guidance": "quick_take_profit",
                "risk_tone": "aggressive",
                "trade_aggressiveness": "high",
            },
            "monitor_policy": {
                "position_guards": {
                    "min_hold_seconds": 0,
                    "sell_cooldown_seconds": 30,
                    "exit_confirm_ticks": 1,
                },
                "adaptive_exit": {
                    "stop_loss_pct": 0.025,
                    "take_profit_pct": 0.060,
                    "trailing_stop_pct": 0.020,
                },
                "hard_risk_rails": {
                    "hard_stop_pct": 0.01,
                    "max_stop_pct_cap": 0.03,
                },
            },
        }
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    thresholds = exit_info.get("thresholds") or {}
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.02
    assert float(effective.get("stop_loss_pct") or 0.0) <= 0.03
    assert float(effective.get("hard_stop_pct") or 0.0) == 0.01
    assert int(exit_info.get("exit_confirm_ticks") or 0) == 1
    assert str(exit_info.get("monitor_guidance") or "") == "quick_take_profit"
    assert float(thresholds.get("effective_stop_loss_pct") or 0.0) == 0.01
    assert str(thresholds.get("effective_stop_reason") or "") == "hard_stop"
    adjustments = exit_info.get("exit_policy_guard_adjustments") or []
    assert "strategist_exit_policy_override" in adjustments


def test_monitor_hard_stop_triggers_before_wider_adaptive_stop(monkeypatch):
    monkeypatch.setenv("EXIT_POLICY_STOP_LOSS_PCT", "0.08")
    monkeypatch.setenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.02")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "hold_sec": 900}],
    }
    state["selected"]["price"] = 69160.0
    state["strategist_output"] = {
        "strategy_policy": {
            "market_policy": {
                "playbook": "pullback",
                "monitor_guidance": "hold_through_noise",
                "risk_tone": "normal",
                "trade_aggressiveness": "medium",
            },
            "monitor_policy": {
                "adaptive_exit": {
                    "stop_loss_pct": 0.08,
                    "take_profit_pct": 0.03,
                    "trailing_stop_pct": 0.02,
                },
                "hard_risk_rails": {
                    "hard_stop_pct": 0.01,
                    "max_stop_pct_cap": 0.08,
                },
            },
        }
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    assert str(intents[0]["meta"].get("exit_reason") or "") == "hard_stop"
    exit_info = out.get("monitor_exit") or {}
    effective = exit_info.get("effective_exit_policy") or {}
    thresholds = exit_info.get("thresholds") or {}
    assert str(exit_info.get("reason") or "") == "hard_stop"
    assert float(effective.get("stop_loss_pct") or 0.0) >= 0.08
    assert float(effective.get("hard_stop_pct") or 0.0) == 0.01
    assert float(thresholds.get("effective_stop_loss_pct") or 0.0) == 0.01


def test_monitor_peak_drawdown_exit_uses_persisted_peak(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["selected"]["price"] = 104.0
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 110.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "peak_drawdown_exit_pct": 0.05,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "peak_drawdown"
    assert float(exit_info.get("peak_drawdown") or 0.0) <= -0.05


def test_monitor_vwap_breakdown_exit_uses_feature_signal(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["selected"] = {
        "symbol": "005930",
        "price": 101.0,
        "features": {"engine_vwap_distance": -0.01},
    }
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["persisted_state"] = {
        "position_peak_price": {"005930": 102.0},
    }
    state["policy"] = {
        "use_exit_policy": True,
        "vwap_breakdown_pct": 0.005,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "vwap_breakdown"
    assert float(exit_info.get("vwap_distance") or 0.0) == -0.01


def test_monitor_intraday_low_break_exit_uses_ohlcv_structure(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    candles = [
        {"open": 100.0, "high": 100.5, "low": 99.8, "close": 100.2, "volume": 100000},
        {"open": 100.2, "high": 100.4, "low": 99.5, "close": 99.7, "volume": 120000},
        {"open": 99.7, "high": 99.9, "low": 98.7, "close": 98.8, "volume": 130000},
    ]
    state = _base_state()
    state["selected"] = {"symbol": "005930", "price": 98.8}
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["ohlcv_by_symbol"] = {"005930": candles}
    state["policy"] = {
        "use_exit_policy": True,
        "intraday_low_break_pct": 0.001,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "intraday_low_break"


def test_monitor_trend_breakdown_exit_uses_feature_signal(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = _base_state()
    state["selected"] = {
        "symbol": "005930",
        "price": 100.5,
        "features": {
            "engine_trend_strength": -0.25,
            "engine_vwap_distance": -0.01,
        },
    }
    state["portfolio_snapshot"] = {
        "cash": 2_000_000.0,
        "positions": [{"symbol": "005930", "qty": 2, "avg_price": 100.0, "hold_sec": 900}],
    }
    state["policy"] = {
        "use_exit_policy": True,
        "trend_strength_floor": -0.10,
        "take_profit_pct": 0.0,
    }

    out = monitor_node(state)
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "SELL"
    exit_info = out.get("monitor_exit") or {}
    assert str(exit_info.get("reason") or "") == "trend_breakdown"
    assert float(exit_info.get("vwap_distance") or 0.0) == -0.01


def test_monitor_extract_frame_reads_strategist_output():
    state = {
        "strategist_output": {
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        }
    }
    frame = _extract_monitor_strategy_frame(state)

    assert frame["playbook"] == "defensive"
    assert frame["monitor_guidance"] == "defensive_exit"
    assert frame["risk_tone"] == "conservative"
    assert frame["trade_aggressiveness"] == "low"
