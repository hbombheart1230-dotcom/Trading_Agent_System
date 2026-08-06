from __future__ import annotations

from libs.research.horizon_revision_backtest.analysis import analyze_horizon_revision, build_trade_scenarios


def _observation() -> dict:
    return {
        "trade_id": "T1",
        "day": "2026-08-01",
        "symbol": "005930",
        "model": {
            "entry": {"price": 100.0},
            "exit": {"price": 101.0, "reason": "vwap_breakdown"},
            "outcome": {"net_return_pct": 0.72, "holding_seconds": 120},
            "horizon_contract": {"strategy_horizon": "intraday"},
        },
        "evaluation": {},
        "post_exit_recap": {
            "checkpoints": {
                "+5m": {"status": "observed", "price": 102.0},
                "+30m": {"status": "observed", "price": 104.0},
                "EOD": {"status": "pending"},
            }
        },
    }


def test_trade_scenarios_apply_cost_once_and_keep_missing_checkpoints_missing() -> None:
    rows = build_trade_scenarios([_observation()], live_cost_pct=0.28, mock_cost_pct=1.0)
    assert len(rows) == 1
    scenarios = rows[0]["scenario_returns"]
    assert scenarios["actual_exit"]["live_net_return_pct"] == 0.72
    assert scenarios["+30m"]["live_net_return_pct"] == 3.72
    assert "EOD" not in scenarios


def test_analysis_compares_only_observed_horizon_proxy() -> None:
    payload = analyze_horizon_revision(
        [_observation()],
        live_cost_pct=0.28,
        mock_cost_pct=1.0,
        stage_inventory={},
        q16_review={},
    )
    row = payload["live_horizon_extension_proxy"][0]
    assert row["entry_horizon"] == "intraday"
    assert row["proxy_checkpoint_after_actual_exit"] == "+30m"
    assert row["coverage"] == 1.0
    assert row["average_delta_pct"] == 3.0
