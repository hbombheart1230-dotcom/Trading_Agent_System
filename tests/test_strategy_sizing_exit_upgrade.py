from __future__ import annotations

from libs.runtime.exit_policy import evaluate_exit_policy
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
