from __future__ import annotations

from libs.runtime.monitor_directional_edge import (
    apply_horizon_directional_edge,
    estimate_horizon_directional_edge,
)
from libs.runtime.monitor_entry_cost_filter import (
    evaluate_entry_cost_filter,
    resolve_entry_cost_filter_config,
)


def _memory_packets(*, expectancy_pct: float = 2.2, observed_count: int = 40) -> dict:
    return {
        "monthly_strategy_memory": {
            "operator_summary": {
                "quant_shadow_candidate_evaluation": {
                    "entry_lane_forward_outcomes": {
                        "by_primary_lane": [
                            {
                                "name": "vwap_reclaim",
                                "observed_count": observed_count,
                                "observed_day_count": 8,
                                "coverage": 0.9,
                                "sample_concentration": 0.4,
                                "avg_return_5m_pct": 0.4,
                                "avg_return_30m_pct": expectancy_pct,
                                "avg_return_60m_pct": 1.1,
                            }
                        ],
                        "by_subtype": [],
                    }
                }
            }
        }
    }


def _state(*, expectancy_pct: float = 2.2, observed_count: int = 40) -> dict:
    return {
        "strategist_output": {
            "memory_packets": _memory_packets(
                expectancy_pct=expectancy_pct,
                observed_count=observed_count,
            )
        }
    }


def _persisted_state(*, expectancy_pct: float = 2.2) -> dict:
    return {
        "persisted_state": {
            "strategist_output_cache": {
                "output": {
                    "memory_packets": _memory_packets(expectancy_pct=expectancy_pct)
                }
            }
        }
    }


def test_directional_edge_uses_horizon_matched_historical_expectancy() -> None:
    result = estimate_horizon_directional_edge(
        state=_state(),
        selected={"symbol": "005930"},
        entry_info={"reason": "pullback_structure_above_vwap_with_volume_confirmation"},
        strategy_frame={"strategy_horizon": "intraday"},
    )

    assert result["available"] is True
    assert result["forward_horizon"] == "30m"
    assert result["expected_move_pct"] == 0.022
    assert result["source"].endswith("vwap_reclaim.avg_return_30m_pct")


def test_directional_edge_reads_persisted_runtime_cache_shape() -> None:
    result = estimate_horizon_directional_edge(
        state=_persisted_state(expectancy_pct=1.7),
        selected={"symbol": "005930"},
        entry_info={"reason": "pullback_structure_above_vwap_with_volume_confirmation"},
        strategy_frame={"strategy_horizon": "intraday"},
    )

    assert result["available"] is True
    assert result["historical_expectancy_pct"] == 1.7


def test_long_horizons_do_not_fall_back_to_short_forward_returns() -> None:
    overnight = estimate_horizon_directional_edge(
        state=_state(),
        selected={"symbol": "005930"},
        entry_info={"reason": "vwap_reclaim"},
        strategy_frame={"strategy_horizon": "overnight_probe"},
    )
    swing = estimate_horizon_directional_edge(
        state=_state(),
        selected={"symbol": "005930"},
        entry_info={"reason": "vwap_reclaim"},
        strategy_frame={"strategy_horizon": "1_2day_swing"},
    )

    assert overnight["available"] is False
    assert overnight["forward_horizon"] == "next_open"
    assert overnight["return_field"] == "avg_return_next_open_pct"
    assert overnight["reason"] == "horizon_matched_expectancy_missing"
    assert swing["available"] is False
    assert swing["forward_horizon"] == "1d"
    assert swing["return_field"] == "avg_return_1d_pct"
    assert swing["reason"] == "horizon_matched_expectancy_missing"


def test_unknown_horizon_fails_closed_instead_of_using_intraday() -> None:
    result = estimate_horizon_directional_edge(
        state=_state(),
        selected={},
        entry_info={"reason": "vwap_reclaim"},
        strategy_frame={"strategy_horizon": "unexpected_horizon"},
    )

    assert result["available"] is False
    assert result["forward_horizon"] is None
    assert result["reason"] == "unsupported_strategy_horizon"


def test_directional_edge_rejects_small_or_non_positive_evidence() -> None:
    small = estimate_horizon_directional_edge(
        state=_state(observed_count=4),
        selected={},
        entry_info={"reason": "vwap_reclaim"},
        strategy_frame={"strategy_horizon": "intraday"},
    )
    negative = estimate_horizon_directional_edge(
        state=_state(expectancy_pct=-0.2),
        selected={},
        entry_info={"reason": "vwap_reclaim"},
        strategy_frame={"strategy_horizon": "intraday"},
    )

    assert small["available"] is False
    assert "observed_count_below_minimum" in small["failed_requirements"]
    assert negative["available"] is False
    assert "historical_expectancy_not_positive" in negative["failed_requirements"]


def test_directional_edge_classifies_breakout_before_vwap_reference() -> None:
    result = estimate_horizon_directional_edge(
        state=_state(),
        selected={},
        entry_info={"reason": "breakout_above_recent_high_with_vwap_structure_confirmation"},
        strategy_frame={"strategy_horizon": "intraday"},
    )

    assert result["setup_lane"] == "breakout_readiness"
    assert result["available"] is False
    assert result["reason"] == "matching_performance_profile_missing"


def test_apply_directional_edge_adds_cost_filter_input_and_metadata() -> None:
    entry_info = {
        "reason": "pullback_structure_above_vwap_with_volume_confirmation",
        "metrics": {"current_price": 100.0},
    }

    result = apply_horizon_directional_edge(
        state=_state(),
        selected={"symbol": "005930"},
        entry_info=entry_info,
        strategy_frame={"strategy_horizon": "intraday"},
    )

    assert result["available"] is True
    assert entry_info["metrics"]["expected_move_pct"] == 0.022
    assert entry_info["directional_edge_estimate"]["behavior_effect"] == "entry_cost_evidence"


def test_directional_edge_is_consumed_as_directional_cost_evidence() -> None:
    entry_info = {
        "triggered": True,
        "reason": "pullback_structure_above_vwap_with_volume_confirmation",
        "metrics": {"current_price": 100.0, "entry_quality_score": 0.9},
        "condition_scores": {"entry_quality_score": 0.9},
    }
    apply_horizon_directional_edge(
        state=_state(),
        selected={"symbol": "005930", "price": 100.0},
        entry_info=entry_info,
        strategy_frame={"strategy_horizon": "intraday"},
    )
    config = resolve_entry_cost_filter_config(
        state={},
        policy={},
        monitor_policy={},
        strategy_monitor_policy={},
        entry_policy_input={},
        commander_entry_control={},
    )

    result = evaluate_entry_cost_filter(
        entry_info=entry_info,
        selected={"symbol": "005930", "price": 100.0},
        qty=100,
        config=config,
    )

    assert result["directional_edge_available"] is True
    assert result["edge_evidence_type"] == "directional"
    assert result["estimated_gross_edge_source"] == "metrics.expected_move_pct*quality_modifier"
    assert result["passed"] is True
