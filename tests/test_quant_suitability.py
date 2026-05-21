from __future__ import annotations

from libs.runtime.quant.factors import build_factor_snapshot_from_candidate
from libs.runtime.quant.suitability import score_candidate_tactic_suitability, score_tactic_suitability


def test_vwap_pullback_suitability_scores_fit_and_penalties() -> None:
    snapshot = build_factor_snapshot_from_candidate(
        {
            "symbol": "005930",
            "score_total": 0.8,
            "confidence": 0.7,
            "features": {
                "engine_vwap_distance": -0.004,
                "compat_volume_ratio": 1.3,
                "engine_trend_strength": 0.5,
            },
            "scanner_chart_fit_score": 0.7,
        },
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    suitability = score_tactic_suitability(snapshot, tactic_id="vwap_reclaim_pullback", playbook="pullback")

    assert suitability["schema_version"] == "tactic_suitability.v1"
    assert suitability["tactic_id"] == "vwap_reclaim_pullback"
    assert suitability["tier"] == "strong"
    assert "vwap_pullback_band_fit" in suitability["positive_reasons"]
    assert suitability["behavior_effect"] == "observation_only"


def test_breakout_suitability_penalizes_below_vwap_and_missing_volume() -> None:
    suitability = score_candidate_tactic_suitability(
        {
            "symbol": "000660",
            "score_total": 0.8,
            "confidence": 0.7,
            "expected_monitor_block_reason": "volume_confirmation_missing",
            "features": {
                "compat_is_below_vwap": True,
                "compat_volume_ratio": 0.4,
                "compat_breakout_gap_pct": 0.001,
                "engine_trend_strength": 0.2,
            },
        },
        tactic_id="opening_range_breakout",
        playbook="breakout",
    )

    assert suitability["tactic_id"] == "opening_range_breakout"
    assert suitability["tier"] in {"weak", "watch"}
    assert "volume_confirmation_missing" in suitability["penalty_reasons"]
    assert suitability["factor_snapshot_ref"]["source"] == "quant_candidate_factor_snapshot.v1"

