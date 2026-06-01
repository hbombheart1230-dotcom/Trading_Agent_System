from __future__ import annotations

import pytest

from libs.runtime.exit_policy import apply_account_pnl_crosscheck_context, evaluate_exit_policy
from libs.runtime.position_sizing import evaluate_position_size


def test_position_sizing_strategy_context_reduces_qty_in_degrade_mode():
    base = evaluate_position_size(
        price=100.0,
        cash=1_000_000.0,
        policy={
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 0.10,
        },
        risk_context={},
    )
    degraded = evaluate_position_size(
        price=100.0,
        cash=1_000_000.0,
        policy={
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.03,
            "position_notional_ratio": 0.10,
        },
        risk_context={
            "regime": "high_volatility",
            "volatility_percentile": 0.9,
            "portfolio_exposure": 0.8,
            "correlation_bucket": "high",
            "daily_loss_state": True,
            "degrade_mode": True,
        },
    )
    assert int(base["qty"]) > 0
    assert int(degraded["qty"]) >= 0
    assert int(degraded["qty"]) < int(base["qty"])
    assert degraded["inputs"]["degrade_mode"] is True


def test_position_sizing_respects_absolute_notional_cap():
    out = evaluate_position_size(
        price=50_000.0,
        cash=10_000_000.0,
        policy={
            "risk_per_trade_ratio": 0.01,
            "stop_loss_pct": 0.01,
            "position_notional_ratio": 1.0,
            "max_position_qty": 100,
            "max_position_notional": 1_000_000,
        },
        risk_context={},
    )

    assert out["reason"] == "ok"
    assert int(out["qty"]) == 20
    assert float(out["inputs"]["notional_budget"]) == 1_000_000.0
    assert float(out["inputs"]["max_position_notional"]) == 1_000_000.0


def test_exit_policy_trailing_stop_triggers():
    out = evaluate_exit_policy(
        price=95.0,
        avg_price=90.0,
        qty=10,
        policy={
            "trailing_stop_pct": 0.04,
            "peak_price": 100.0,
            "take_profit_pct": 0.0,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "trailing_stop"


def test_exit_policy_volatility_expansion_triggers():
    out = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=3,
        policy={
            "vol_expansion_ratio": 1.5,
            "current_volatility": 0.06,
            "baseline_volatility": 0.03,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "volatility_expansion"


def test_exit_policy_emergency_and_eod_flat_triggers():
    out_emergency = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=1,
        policy={"emergency_halt": True},
    )
    assert out_emergency["triggered"] is True
    assert out_emergency["reason"] == "emergency_halt"

    out_eod = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=1,
        policy={"use_eod_flat": True, "minutes_to_close": 5, "eod_flat_cutoff_min": 10},
    )
    assert out_eod["triggered"] is True
    assert out_eod["reason"] == "eod_flat"


def test_exit_policy_time_stop_alias_triggers():
    out = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=1,
        hold_sec=3700,
        policy={"time_stop_sec": 3600},
    )
    assert out["triggered"] is True
    assert out["reason"] == "time_stop"


def test_exit_policy_time_stop_reassesses_below_cost_floor():
    out = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        hold_sec=901,
        policy={
            "time_stop_sec": 900,
            "take_profit_pct": 0.0,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["time_limit_reached"] is True
    assert out["time_limit_reassessment_blocked"] is True
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["hold_block_reason"] == "time_stop:cost_aware_profit_floor_not_met"


def test_exit_policy_time_stop_allows_exit_after_cost_floor():
    out = evaluate_exit_policy(
        price=101.3,
        avg_price=100.0,
        qty=1,
        hold_sec=901,
        policy={
            "time_stop_sec": 900,
            "take_profit_pct": 0.0,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "time_stop"
    assert out["time_limit_reached"] is True
    assert out["time_limit_reassessment_blocked"] is False


def test_exit_policy_news_shock_triggers():
    out = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=2,
        policy={
            "news_shock_threshold": 0.30,
            "symbol_sentiment_score": -0.45,
            "global_sentiment_score": 0.00,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "news_shock"


def test_exit_policy_hard_stop_overrides_wider_soft_stop():
    out = evaluate_exit_policy(
        price=98.8,
        avg_price=100.0,
        qty=1,
        policy={
            "hard_stop_pct": 0.01,
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.05,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "hard_stop"
    assert float((out.get("thresholds") or {}).get("effective_stop_loss_pct") or 0.0) == 0.01
    assert str((out.get("thresholds") or {}).get("effective_stop_reason") or "") == "hard_stop"


def test_exit_policy_prefers_tighter_soft_stop_when_hard_stop_is_looser():
    out = evaluate_exit_policy(
        price=96.5,
        avg_price=100.0,
        qty=1,
        policy={
            "hard_stop_pct": 0.05,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.05,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "stop_loss"
    assert float((out.get("thresholds") or {}).get("effective_stop_loss_pct") or 0.0) == 0.03
    assert str((out.get("thresholds") or {}).get("effective_stop_reason") or "") == "stop_loss"


def test_exit_policy_peak_drawdown_triggers():
    out = evaluate_exit_policy(
        price=104.0,
        avg_price=100.0,
        qty=1,
        policy={
            "peak_price": 110.0,
            "peak_drawdown_exit_pct": 0.05,
            "profit_protection_activation_pct": 0.08,
            "take_profit_pct": 0.0,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "peak_drawdown"
    assert out["peak_drawdown_armed"] is True
    assert float(out.get("max_runup_pct") or 0.0) >= 0.08
    assert float(out.get("peak_drawdown") or 0.0) <= -0.05


def test_exit_policy_peak_drawdown_stays_disarmed_without_runup_activation():
    out = evaluate_exit_policy(
        price=97.5,
        avg_price=100.0,
        qty=1,
        policy={
            "peak_drawdown_exit_pct": 0.02,
            "profit_protection_activation_pct": 0.008,
            "take_profit_pct": 0.0,
            "stop_loss_pct": 0.0,
            "hard_stop_pct": 0.0,
        },
    )
    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["peak_drawdown_armed"] is False
    assert float(out.get("max_runup_pct") or 0.0) < 0.008
    assert float(out.get("peak_drawdown_from_peak") or 0.0) <= -0.02


def test_exit_policy_vwap_breakdown_triggers_with_profit_protection():
    out = evaluate_exit_policy(
        price=101.0,
        avg_price=100.0,
        qty=1,
        policy={
            "peak_price": 102.0,
            "vwap_distance": -0.01,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_confirmation_required": False,
            "take_profit_pct": 0.0,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "vwap_breakdown"
    assert float(out.get("vwap_distance") or 0.0) == -0.01


def test_exit_policy_intraday_low_break_triggers():
    out = evaluate_exit_policy(
        price=98.8,
        avg_price=100.0,
        qty=1,
        policy={
            "prior_bar_low": 99.0,
            "intraday_low_break_pct": 0.001,
            "intraday_low_break_consecutive_bars": 2,
            "take_profit_pct": 0.0,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "intraday_low_break"
    assert float(out.get("prior_bar_low") or 0.0) == 99.0


def test_exit_policy_intraday_low_break_waits_for_min_hold_or_confirmation():
    out = evaluate_exit_policy(
        price=98.8,
        avg_price=100.0,
        qty=1,
        hold_sec=30,
        policy={
            "prior_bar_low": 99.0,
            "intraday_low_break_pct": 0.001,
            "take_profit_pct": 0.0,
        },
    )

    assert out["triggered"] is False
    assert out["intraday_low_break_min_hold_blocked"] is True
    assert out["hold_block_reason"] == "intraday_low_break_min_hold_pending"


def test_exit_policy_intraday_low_break_deep_still_waits_for_min_hold():
    out = evaluate_exit_policy(
        price=98.2,
        avg_price=100.0,
        qty=1,
        hold_sec=32,
        policy={
            "prior_bar_low": 99.0,
            "intraday_low_break_pct": 0.001,
            "take_profit_pct": 0.0,
        },
    )

    assert out["triggered"] is False
    assert out["intraday_low_break_min_hold_blocked"] is True
    assert str(out.get("protective_exit_hard_invalidation_reason") or "").startswith("intraday_low_break_deep:")
    assert out["hold_block_reason"] == "intraday_low_break_min_hold_pending"


def test_exit_policy_trend_breakdown_triggers():
    out = evaluate_exit_policy(
        price=100.5,
        avg_price=100.0,
        qty=1,
        policy={
            "trend_strength": -0.25,
            "trend_strength_floor": -0.10,
            "vwap_distance": -0.01,
            "take_profit_pct": 0.0,
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "trend_breakdown"
    assert float(out.get("trend_strength") or 0.0) == -0.25


def test_exit_policy_without_chart_context_keeps_existing_hold_behavior():
    out = evaluate_exit_policy(
        price=100.5,
        avg_price=100.0,
        qty=1,
        policy={"take_profit_pct": 0.10, "stop_loss_pct": 0.05},
    )
    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["chart_context_available"] is False
    assert str(out.get("structure_breakdown_signal") or "") == ""


def test_exit_policy_accepts_optional_chart_context_without_changing_threshold_decision():
    out = evaluate_exit_policy(
        price=95.0,
        avg_price=90.0,
        qty=10,
        policy={
            "trailing_stop_pct": 0.04,
            "peak_price": 100.0,
            "take_profit_pct": 0.0,
            "chart_context": {
                "source": "state.monitor_entry_decision_detail",
                "chart_structure_features": {
                    "schema_version": "chart_structure_features.v1",
                    "available": True,
                    "structure": {"structure_hh_hl": "weakening"},
                    "trend_alignment": {"ma_alignment_state": "bearish", "trend_regime": "transition"},
                    "support_resistance": {"support_holding": "lost", "failed_breakout": "confirmed"},
                    "continuity_momentum": {"momentum_follow_through": "weak"},
                    "notes": ["minute_snapshot_fresh"],
                },
            },
        },
    )
    assert out["triggered"] is True
    assert out["reason"] == "trailing_stop"
    assert out["chart_context_available"] is True
    assert str(out.get("structure_breakdown_signal") or "") == "failed_breakout"
    summary = out.get("chart_context_summary") or {}
    assert summary.get("support_holding") == "lost"
    assert summary.get("failed_breakout") == "confirmed"


def test_exit_policy_crosschecks_account_unrealized_pnl_conservatively():
    policy = apply_account_pnl_crosscheck_context(
        {"stop_loss_pct": 0.04, "take_profit_pct": 0.10},
        position={
            "symbol": "005930",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 97.0,
            "unrealized_pnl": -4.5,
        },
    )
    out = evaluate_exit_policy(
        price=97.0,
        avg_price=100.0,
        qty=1,
        policy=policy,
    )
    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert float(out.get("raw_price") or 0.0) == 97.0
    assert float(out.get("effective_price") or 0.0) == 95.5
    assert round(float(out.get("raw_pnl_ratio") or 0.0), 4) == -0.03
    assert round(float(out.get("account_pnl_ratio") or 0.0), 4) == -0.045
    assert round(float(out.get("pnl_ratio") or 0.0), 4) == -0.045
    assert round(float(out.get("stop_pnl_ratio") or 0.0), 4) == -0.03
    assert out.get("cost_drag_pressure") is True
    assert out.get("stop_loss_cost_drag_blocked") is True
    assert out.get("hold_block_reason") == "stop_loss_cost_drag_only"
    assert out.get("pnl_crosscheck_applied") is True
    assert str(out.get("pnl_crosscheck_reason") or "") == "account_unrealized_pnl_more_conservative"


def test_exit_policy_prefers_direct_account_pnl_ratio_when_available():
    policy = apply_account_pnl_crosscheck_context(
        {"stop_loss_pct": 0.032, "take_profit_pct": 0.10},
        position={
            "symbol": "005930",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 97.0,
            "unrealized_pnl": -3.0,
            "account_pnl_ratio": -0.0337,
            "account_pnl_ratio_source": "position.evlu_pfls_rt",
        },
    )
    out = evaluate_exit_policy(
        price=97.0,
        avg_price=100.0,
        qty=1,
        policy=policy,
    )
    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert round(float(out.get("account_pnl_ratio") or 0.0), 4) == -0.0337
    assert str(out.get("account_pnl_ratio_source") or "") == "position.evlu_pfls_rt"
    assert round(float(out.get("effective_price") or 0.0), 2) == 96.63
    assert round(float(out.get("pnl_ratio") or 0.0), 4) == -0.0337
    assert round(float(out.get("stop_pnl_ratio") or 0.0), 4) == -0.03
    assert out.get("cost_drag_pressure") is True
    assert out.get("stop_loss_cost_drag_blocked") is True
    assert out.get("pnl_crosscheck_applied") is True
    assert str(out.get("pnl_crosscheck_reason") or "") == "account_pnl_ratio_more_conservative"


def test_exit_policy_hard_stop_still_uses_account_pnl_crosscheck():
    policy = apply_account_pnl_crosscheck_context(
        {"hard_stop_pct": 0.008, "stop_loss_pct": 0.03, "take_profit_pct": 0.10},
        position={
            "symbol": "005930",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 100.0,
            "account_pnl_ratio": -0.009,
            "account_pnl_ratio_source": "position.evlu_pfls_rt",
        },
    )
    out = evaluate_exit_policy(
        price=100.0,
        avg_price=100.0,
        qty=1,
        policy=policy,
    )
    assert out["triggered"] is True
    assert out["reason"] == "hard_stop"
    assert round(float(out.get("stop_pnl_ratio") or 0.0), 4) == 0.0
    assert round(float(out.get("hard_stop_pnl_ratio") or 0.0), 4) == -0.009
    assert out.get("cost_drag_pressure") is True


def test_exit_policy_flags_account_ratio_mark_anomaly_and_falls_back_to_sane_price():
    policy = apply_account_pnl_crosscheck_context(
        {"stop_loss_pct": 0.02, "take_profit_pct": 0.10},
        position={
            "symbol": "005930",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 97.0,
            "unrealized_pnl": -3.0,
            "account_pnl_ratio": -0.9,
            "account_pnl_ratio_source": "position.prft_rt",
        },
    )
    out = evaluate_exit_policy(
        price=97.0,
        avg_price=100.0,
        qty=1,
        policy=policy,
    )
    assert out["triggered"] is True
    assert out["reason"] == "stop_loss"
    assert out["price_anomaly_flag"] is True
    assert "account_pnl_ratio_mark" in str(out.get("price_anomaly_reason") or "")
    assert out["pnl_fallback_applied"] is True
    assert str(out.get("fallback_price_source") or "") == "account_unrealized_mark"
    assert round(float(out.get("effective_price") or 0.0), 2) == 97.0
    assert str(out.get("effective_price_source") or "") == "account_unrealized_mark"
    assert round(float(out.get("pnl_ratio") or 0.0), 4) == -0.03


def test_exit_policy_peak_drawdown_does_not_trigger_before_profit_protection_activation():
    out = evaluate_exit_policy(
        price=97.5,
        avg_price=100.0,
        qty=1,
        policy={
            "peak_drawdown_exit_pct": 0.02,
            "profit_protection_activation_pct": 0.01,
            "take_profit_pct": 0.0,
            "stop_loss_pct": 0.0,
            "hard_stop_pct": 0.0,
        },
    )
    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["peak_drawdown_armed"] is False
    assert str(out.get("peak_drawdown_mode") or "") == "profit_protection"
    assert float(out.get("peak_drawdown") or 0.0) <= -0.02
    assert float(out.get("final_peak_drawdown_ratio") or 0.0) <= -0.02
    assert str(out.get("peak_drawdown_source") or "") == "raw_price_vs_peak_price"
    assert str(out.get("exit_trigger_metric_name") or "") == ""
    assert out.get("exit_trigger_metric_value") in (None, "")
    assert str(out.get("exit_trigger_metric_source") or "") == ""
    assert isinstance(out.get("final_exit_thresholds"), dict)
    assert str(out.get("exit_threshold_source") or "") != ""


def test_exit_policy_cost_aware_floor_blocks_small_profit_take():
    out = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.005,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["hold_block_reason"] == "cost_aware_profit_floor_not_met"
    assert out["cost_aware_profit_floor_pct"] == pytest.approx(0.012)
    assert out["cost_aware_profit_floor_met"] is False


def test_exit_policy_cost_aware_floor_allows_profit_after_cost_buffer():
    out = evaluate_exit_policy(
        price=101.3,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.005,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "take_profit"
    assert out["cost_aware_profit_floor_met"] is True
    assert out["cost_aware_profit_floor_blocked"] is False


def test_exit_policy_cost_floor_uses_gross_profit_not_account_cost_drag_twice():
    policy = apply_account_pnl_crosscheck_context(
        {
            "take_profit_pct": 0.10,
            "partial_take_profit_pct": 0.012,
            "profit_ladder_levels_pct": [],
            "risk_reward_take_profit_r": 0.0,
            "risk_reward_take_profit_rungs": [],
            "volume_exhaustion_take_profit_min_pct": 0.0,
            "opening_gap_profit_take_min_pct": 0.0,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
        position={
            "symbol": "034730",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 101.976,
            "account_pnl_ratio": 0.0106,
            "account_pnl_ratio_source": "position.evlu_pfls_rt",
        },
    )
    out = evaluate_exit_policy(price=101.976, avg_price=100.0, qty=1, policy=policy)

    assert out["triggered"] is True
    assert out["reason"] == "partial_take_profit"
    assert out["gross_pnl_ratio"] == pytest.approx(0.01976)
    assert out["effective_pnl_ratio"] == pytest.approx(0.0106)
    assert out["cost_aware_profit_floor_met"] is True
    assert out["gross_profit_floor_met"] is True
    assert out["profit_exit_metric_name"] in {"expected_exit_pnl_ratio", "gross_pnl_ratio"}
    assert out["cost_aware_profit_floor_blocked"] is False


def test_exit_policy_etf_premium_take_profit_uses_deviation_signal():
    out = evaluate_exit_policy(
        price=101.3,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.10,
            "etf_deviation_pct": 0.55,
            "etf_deviation_source": "raw.dstr_rt",
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "etf_premium_take_profit"
    assert out["exit_trigger_metric_name"] == "etf_deviation_pct"
    assert out["exit_trigger_metric_value"] == 0.55
    assert out["cost_aware_profit_floor_blocked"] is False


def test_exit_policy_etf_premium_take_profit_respects_cost_floor():
    out = evaluate_exit_policy(
        price=100.5,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.10,
            "etf_deviation_pct": 0.55,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["etf_premium_take_profit_armed"] is True
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["hold_block_reason"] == "etf_premium_take_profit:cost_aware_profit_floor_not_met"


def test_exit_policy_cost_aware_floor_does_not_block_loss_stops():
    out = evaluate_exit_policy(
        price=97.0,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.005,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "stop_loss"
    assert out["cost_aware_profit_floor_blocked"] is False


def test_exit_policy_cost_aware_floor_blocks_trailing_stop_on_small_profit():
    out = evaluate_exit_policy(
        price=100.4,
        avg_price=100.0,
        qty=1,
        policy={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.0,
            "peak_price": 101.2,
            "trailing_stop_pct": 0.003,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["trailing_drawdown"] <= -0.003
    assert out["cost_aware_profit_floor_blocked"] is True


def test_exit_policy_cost_aware_floor_blocks_vwap_breakdown_on_small_profit():
    out = evaluate_exit_policy(
        price=100.6,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_confirmation_required": False,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked_reason"] == "vwap_breakdown"
    assert out["hold_block_reason"] == "vwap_breakdown:cost_aware_profit_floor_not_met"


def test_exit_policy_vwap_breakdown_waits_for_confirmation_when_not_stop_loss():
    out = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_consecutive_bars": 1,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["vwap_breakdown_confirmation_pending"] is True
    assert out["hold_block_reason"] == "vwap_breakdown_confirmation_pending"


def test_exit_policy_vwap_breakdown_exits_after_two_bars():
    out = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_consecutive_bars": 2,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "vwap_breakdown"
    assert out["vwap_breakdown_confirmed"] is True


def test_exit_policy_vwap_breakdown_waits_for_single_confirmation_signal():
    low_break = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_consecutive_bars": 1,
            "vwap_breakdown_low_break_confirmed": True,
        },
    )
    volume = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_consecutive_bars": 1,
            "vwap_breakdown_volume_confirmed": True,
        },
    )

    assert low_break["triggered"] is False
    assert low_break["reason"] == "hold"
    assert low_break["vwap_breakdown_confirmation_pending"] is True
    assert volume["triggered"] is False
    assert volume["reason"] == "hold"
    assert volume["vwap_breakdown_confirmation_pending"] is True


def test_exit_policy_vwap_breakdown_exits_on_volume_and_low_break_confirmation():
    out = evaluate_exit_policy(
        price=100.8,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_consecutive_bars": 1,
            "vwap_breakdown_low_break_confirmed": True,
            "vwap_breakdown_volume_confirmed": True,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "vwap_breakdown"


def test_exit_policy_cost_aware_floor_blocks_metric_hard_vwap_breakdown_on_small_profit():
    out = evaluate_exit_policy(
        price=100.7,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.03,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_confirmation_required": False,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["protective_exit_hard_invalidation"] is True
    assert out["protective_exit_hard_invalidation_suppressed_by_cost_floor"] is True
    assert str(out["protective_exit_hard_invalidation_reason"]).startswith("vwap_breakdown_deep:")
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked_reason"] == "vwap_breakdown"
    assert out["hold_block_reason"] == "vwap_breakdown:cost_aware_profit_floor_not_met"


def test_exit_policy_cost_aware_floor_allows_explicit_hard_vwap_invalidation():
    out = evaluate_exit_policy(
        price=100.7,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.03,
            "vwap_breakdown_pct": 0.005,
            "hard_invalidation_confirmed": True,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "vwap_breakdown"
    assert out["protective_exit_hard_invalidation"] is True
    assert out["protective_exit_hard_invalidation_reason"] == "explicit_policy_flag"
    assert out["protective_exit_hard_invalidation_suppressed_by_cost_floor"] is False
    assert out["protective_exit_floor_blocked"] is False


def test_exit_policy_cost_aware_floor_blocks_vwap_breakdown_when_gross_profit_is_cost_loss():
    policy = apply_account_pnl_crosscheck_context(
        {
            "take_profit_pct": 0.0,
            "peak_price": 101.5,
            "vwap_distance": -0.006,
            "vwap_breakdown_pct": 0.005,
            "vwap_breakdown_confirmation_required": False,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
        position={
            "symbol": "005930",
            "qty": 1,
            "avg_price": 100.0,
            "current_price": 100.4,
            "account_pnl_ratio": -0.005,
            "account_pnl_ratio_source": "position.evlu_pfls_rt",
        },
    )
    out = evaluate_exit_policy(
        price=100.4,
        avg_price=100.0,
        qty=1,
        policy=policy,
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert round(float(out.get("gross_pnl_ratio") or 0.0), 4) == 0.004
    assert round(float(out.get("pnl_ratio") or 0.0), 4) == -0.005
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked_reason"] == "vwap_breakdown"


def test_exit_policy_peak_drawdown_protects_cost_floor_runup_giveback():
    out = evaluate_exit_policy(
        price=100.6,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "peak_price": 101.8,
            "peak_drawdown_exit_pct": 0.005,
            "cost_aware_profit_floor_enabled": True,
            "round_trip_cost_floor_pct": 0.009,
            "min_net_profit_buffer_pct": 0.003,
        },
    )

    assert out["triggered"] is True
    assert out["reason"] == "peak_drawdown"
    assert out["peak_drawdown_profit_protection_urgent"] is True
    assert out["peak_drawdown_profit_protection_reason"] == "max_runup_crossed_cost_floor_then_gave_back"


def test_exit_policy_waits_for_intraday_low_break_confirmation_before_cost_floor_block():
    out = evaluate_exit_policy(
        price=100.4,
        avg_price=100.0,
        qty=1,
        policy={
            "take_profit_pct": 0.0,
            "prior_bar_low": 100.6,
            "intraday_low_break_pct": 0.001,
            "cost_aware_profit_floor_enabled": True,
            "cost_aware_profit_floor_pct": 0.012,
        },
    )

    assert out["triggered"] is False
    assert out["reason"] == "hold"
    assert out["intraday_low_break_confirmation_pending"] is True
    assert out["cost_aware_profit_floor_blocked"] is True
    assert out["protective_exit_floor_blocked"] is False
    assert out["hold_block_reason"] == "intraday_low_break_confirmation_pending"
