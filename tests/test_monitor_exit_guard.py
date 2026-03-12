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


def test_monitor_allows_buy_when_open_position_guard_disabled(monkeypatch):
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
    intents = out.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["side"] == "BUY"
    assert (out.get("monitor") or {}).get("buy_blocked_open_position") is False


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


def test_monitor_hard_exit_bypasses_confirmation_ticks(monkeypatch):
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN_SEC", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "6")
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
    assert bool((out.get("monitor_exit") or {}).get("hard_exit")) is True


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
