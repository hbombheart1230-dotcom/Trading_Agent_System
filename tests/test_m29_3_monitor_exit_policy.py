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
    assert out["monitor"]["buy_blocked_open_position"] is True
    assert out["monitor"]["buy_blocked_same_symbol"] is True


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


def test_m29_3_monitor_exit_ignores_filled_account_order_feature():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "AAA",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "features": {"skill_open_orders": 1},
        },
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 5, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 96.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.10,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
        "skill_results": {
            "account.orders": {
                "rows": [
                    {"symbol": "AAA", "side": "BUY", "order_qty": 1, "filled_qty": 1, "remaining_qty": 0, "status": "FILLED"},
                ]
            }
        },
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["monitor_exit"]["sell_guard_blocked"] is False
    assert out["monitor"]["exit_reason"] == "stop_loss"


def test_m29_3_monitor_exit_uses_entry_sizing_stop_before_wider_policy_stop():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 5, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 98.5},
        "persisted_state": {
            "position_entry_risk_by_symbol": {
                "AAA": {
                    "symbol": "AAA",
                    "stop_loss_pct": 0.01,
                    "stop_loss_source": "entry.metrics.vwap.reclaim_tolerance",
                    "invalidation_price": 99.0,
                    "source": "buy_execution_sizing",
                }
            }
        },
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
    assert out["intents"][0]["meta"]["exit_reason"] == "stop_loss"
    assert out["monitor"]["position_entry_risk_applied"] is True
    assert out["monitor"]["position_entry_stop_loss_pct"] == 0.01
    assert out["monitor"]["exit_effective_stop_loss_pct"] == 0.01


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
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
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


def test_m29_3_monitor_exit_policy_cost_aware_floor_blocks_small_profit():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.10,
            "take_profit_pct": 0.005,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert out["intents"] == []
    assert out["monitor"]["exit_triggered"] is False
    assert out["monitor"]["exit_reason"] == "hold"
    assert out["monitor"]["cost_aware_profit_floor_blocked"] is True
    assert out["monitor_exit"]["cost_aware_profit_floor_pct"] == pytest.approx(0.012)
    assert out["monitor_exit"]["hold_block_reason"] == "cost_aware_profit_floor_not_met"


def test_m29_3_monitor_exit_policy_expected_bid_blocks_profit_take_below_cost_floor():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}]},
        "market_quote": {"symbol": "AAA", "price": 102.0, "best_bid": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.10,
            "take_profit_pct": 0.012,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)

    assert out["intents"] == []
    assert out["monitor"]["exit_triggered"] is False
    assert out["monitor"]["exit_reason"] == "hold"
    assert out["monitor_exit"]["expected_exit_price"] == pytest.approx(100.8)
    assert out["monitor_exit"]["expected_exit_price_source"] == "expected_exit_best_bid"
    assert out["monitor_exit"]["expected_exit_profit_floor_blocked"] is True
    assert out["monitor_exit"]["cost_aware_profit_floor_blocked"] is True
    assert out["monitor_exit"]["hold_block_reason"] == "expected_exit_profit_floor_not_met"


def test_m29_3_monitor_exit_policy_slippage_fallback_blocks_profit_take_below_cost_floor():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0}]},
        "market_snapshot": {"symbol": "AAA", "price": 101.3},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.10,
            "take_profit_pct": 0.012,
            "sell_slippage_buffer_pct": 0.005,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)

    assert out["intents"] == []
    assert out["monitor"]["exit_triggered"] is False
    assert out["monitor_exit"]["expected_exit_price"] == pytest.approx(101.3 * 0.995)
    assert out["monitor_exit"]["expected_exit_price_source"] == "observed_price_minus_slippage_buffer"
    assert out["monitor_exit"]["expected_exit_price_fallback_used"] is True
    assert out["monitor_exit"]["expected_exit_profit_floor_blocked"] is True
    assert out["monitor_exit"]["hold_block_reason"] == "expected_exit_profit_floor_not_met"


def test_m29_3_monitor_exit_policy_risk_reward_take_profit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 900}]},
        "market_snapshot": {"symbol": "AAA", "price": 102.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 1.0,
            "risk_reward_take_profit_rungs": [],
            "risk_reward_take_profit_min_pct": 0.006,
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "risk_reward_take_profit"
    assert out["monitor"]["exit_reason"] == "risk_reward_take_profit"
    thresholds = out["monitor_exit"]["thresholds"]
    assert thresholds["risk_reward_take_profit_r"] == 1.0


def test_m29_3_monitor_exit_policy_partial_take_profit_uses_partial_qty():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 4, "avg_price": 100.0, "hold_sec": 900}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.6},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.005,
            "partial_take_profit_fraction": 0.5,
            "cost_aware_profit_floor_enabled": False,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["qty"] == 2
    assert out["intents"][0]["meta"]["exit_reason"] == "partial_take_profit"
    assert out["intents"][0]["meta"]["partial_exit"] is True
    assert out["monitor"]["exit_reason"] == "partial_take_profit"


def test_m29_3_monitor_exit_policy_profit_ladder_emits_partial_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 6, "avg_price": 100.0, "hold_sec": 900}]},
        "persisted_state": {"partial_take_profit_taken_by_symbol": {"AAA": {"taken_epoch": 1}}},
        "market_snapshot": {"symbol": "AAA", "price": 101.1},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.005,
            "cost_aware_profit_floor_enabled": False,
            "profit_ladder_levels_pct": [0.005, 0.010, 0.015],
            "profit_ladder_fraction": 0.34,
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["qty"] == 2
    assert out["intents"][0]["meta"]["exit_reason"] == "profit_ladder"
    assert out["intents"][0]["meta"]["profit_ladder_level_pct"] == 0.01
    assert out["monitor"]["exit_reason"] == "profit_ladder"


def test_m29_3_monitor_exit_policy_vwap_extension_take_profit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "AAA",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "features": {"engine_vwap_distance": 0.035},
        },
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 900}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.03,
            "vwap_extension_take_profit_min_pct": 0.005,
            "cost_aware_profit_floor_enabled": False,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "vwap_extension_take_profit"
    assert out["monitor"]["exit_reason"] == "vwap_extension_take_profit"
    assert out["monitor_exit"]["vwap_distance"] == 0.035


def test_m29_3_monitor_exit_policy_resistance_take_profit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "AAA",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "features": {"prior_bar_high": 101.0},
        },
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 900}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.003,
            "resistance_take_profit_min_pct": 0.004,
            "cost_aware_profit_floor_enabled": False,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "resistance_take_profit"
    assert out["monitor"]["exit_reason"] == "resistance_take_profit"
    assert out["monitor_exit"]["resistance_price"] == 101.0


def test_m29_3_monitor_exit_policy_volume_exhaustion_take_profit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "AAA",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "features": {"volume_ratio": 0.55},
        },
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 900}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.006,
            "volume_exhaustion_volume_ratio_max": 0.8,
            "cost_aware_profit_floor_enabled": False,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "volume_exhaustion_take_profit"
    assert out["monitor"]["exit_reason"] == "volume_exhaustion_take_profit"


def test_m29_3_monitor_exit_policy_opening_gap_profit_take_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "AAA",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
            "opening_gap_chase_observed": True,
            "open_gap_pct": 0.012,
            "prev_close_distance_pct": 0.018,
        },
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 300}]},
        "market_snapshot": {"symbol": "AAA", "price": 100.5},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.004,
            "opening_gap_profit_take_window_sec": 1200,
            "cost_aware_profit_floor_enabled": False,
            "profit_time_stop_sec": 0,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "opening_gap_profit_take"
    assert out["monitor"]["exit_reason"] == "opening_gap_profit_take"


def test_m29_3_monitor_exit_policy_time_decay_profit_exit_emits_sell_intent():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 2, "avg_price": 100.0, "hold_sec": 900}]},
        "persisted_state": {"position_peak_price": {"AAA": 102.0}},
        "market_snapshot": {"symbol": "AAA", "price": 100.8},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.0,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "vwap_extension_take_profit_pct": 0.0,
            "resistance_take_profit_near_pct": 0.0,
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "profit_time_stop_sec": 600,
            "profit_time_stop_min_pct": 0.006,
            "profit_time_stop_peak_giveback_pct": 0.003,
            "cost_aware_profit_floor_enabled": False,
        },
        "applied_policy": _baseline_applied_policy(use_exit_policy=True),
    }

    out = monitor_node(state)
    assert len(out["intents"]) == 1
    assert out["intents"][0]["side"] == "SELL"
    assert out["intents"][0]["meta"]["exit_reason"] == "time_decay_profit_exit"
    assert out["monitor"]["exit_reason"] == "time_decay_profit_exit"


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
