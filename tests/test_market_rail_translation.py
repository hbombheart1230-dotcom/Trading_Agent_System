from libs.runtime.quant.market_rail_translation import evaluate_market_rail_translation


def _snapshot(**factors):
    return {
        "source": "test",
        "tactic_id": "opening_range_breakout",
        "factors": {
            "volume_ratio": 0.62,
            "vwap_distance_pct": -0.002,
            "vwap_reclaim_progress": 0.72,
            "entry_quality_score": 0.72,
            "human_chart_entry_score": 0.45,
            "human_chart_exit_risk_score": 0.30,
            "weighted_score_total": 1.25,
            "cost_floor_state": "not_met",
            "cost_drag_pct": 0.0021,
            **factors,
        },
    }


def _decision(*blockers):
    return {
        "decision": "block_recommended",
        "blockers": list(blockers),
        "cost_edge": {
            "ok": False,
            "cost_floor_state": "not_met",
            "cost_adjusted_edge_pct": None,
            "cost_drag_pct": 0.0021,
        },
    }


def test_supportive_rail_allows_near_ready_existing_lane_probe():
    result = evaluate_market_rail_translation(
        entry_info={"reason": "below_vwap_reclaim_not_ready", "primary_failure_axis": "vwap_relationship"},
        entry_quant_decision=_decision("cost_edge_fail"),
        factor_snapshot=_snapshot(),
        market_regime="risk_on",
        market_regime_rail="krx_night_futures_gap_up",
    )

    assert result["applied"] is True
    assert result["allow_probe"] is True
    assert result["probe_max_qty"] == 1
    assert "vwap_reclaim_near_ready" in result["relaxed_blockers"]
    assert "cost_near_miss" in result["relaxed_blockers"]


def test_supportive_rail_does_not_relax_human_chart_hard_block():
    result = evaluate_market_rail_translation(
        entry_info={"reason": "human_chart_sanity_guard_blocked", "primary_failure_axis": "human_chart_sanity"},
        entry_quant_decision=_decision("cost_edge_fail", "entry_chart_score<0.25"),
        factor_snapshot=_snapshot(human_chart_entry_score=0.2),
        market_regime="risk_on",
        market_regime_rail="krx_night_futures_gap_up",
    )

    assert result["applied"] is False
    assert result["allow_probe"] is False
    assert "hard_blocker_present" in result["reason"]


def test_neutral_rail_keeps_observation_only():
    result = evaluate_market_rail_translation(
        entry_info={"reason": "volume_insufficient", "primary_failure_axis": "volume_confirmation"},
        entry_quant_decision=_decision("cost_edge_fail", "volume_confirmation_missing"),
        factor_snapshot=_snapshot(vwap_distance_pct=0.001),
        market_regime="neutral",
        market_regime_rail="neutral_mixed",
    )

    assert result["applied"] is False
    assert result["behavior_effect"] == "observation_only"
    assert "market_rail_not_supportive" in result["reason"]
