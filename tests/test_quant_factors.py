from __future__ import annotations

from libs.runtime.quant.factors import (
    build_factor_snapshot_from_candidate,
    build_factor_snapshot_from_monitor_entry,
)
from libs.runtime.scanner.output_payloads import build_candidate_selection_reason_payload
from libs.runtime.scanner.output_snapshots import compact_selected_snapshot, ranking_table_rows


def test_candidate_factor_snapshot_extracts_scanner_features() -> None:
    snapshot = build_factor_snapshot_from_candidate(
        {
            "symbol": "005930",
            "score_total": 0.73,
            "confidence": 0.61,
            "risk_score": 0.18,
            "features": {
                "engine_vwap_distance": -0.004,
                "compat_volume_ratio": 1.32,
                "engine_volume_spike20": 1.8,
                "engine_trend_strength": 0.44,
            },
            "scanner_chart_fit_score": 0.7,
        },
        tactic_id="leader_vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert snapshot["source"] == "quant_candidate_factor_snapshot.v1"
    assert snapshot["tactic_id"] == "vwap_reclaim_pullback"
    assert snapshot["behavior_effect"] == "observation_only"
    assert snapshot["factors"]["symbol"] == "005930"
    assert snapshot["factors"]["vwap_distance_pct"] == -0.004
    assert snapshot["factors"]["volume_ratio"] == 1.32
    assert "vwap_distance_pct" not in snapshot["missing"]


def test_monitor_entry_factor_snapshot_extracts_cost_and_chart_fields() -> None:
    snapshot = build_factor_snapshot_from_monitor_entry(
        {
            "triggered": True,
            "reason": "pullback_reclaim_above_vwap_with_rebound_confirmation",
            "metrics": {
                "vwap_distance": -0.002,
                "volume_ratio": 1.1,
                "pullback_depth_pct": 0.018,
                "human_chart_entry_score": 0.72,
                "lower_vwap_rebound_probe_path_ok": True,
            },
            "condition_scores": {
                "confidence_score": 0.64,
                "entry_quality_score": 0.7,
            },
            "entry_cost_filter": {
                "passed": False,
                "cost_adjusted_edge_pct": -0.001,
                "round_trip_cost_floor_pct": 0.009,
            },
        },
        selected={"symbol": "005930"},
        tactic_id="vwap_reclaim_pullback",
        playbook="pullback",
    )

    assert snapshot["source"] == "quant_monitor_entry_factor_snapshot.v1"
    assert snapshot["factors"]["cost_floor_state"] == "not_met"
    assert snapshot["factors"]["human_chart_entry_score"] == 0.72
    assert snapshot["factors"]["lower_vwap_rebound_probe_path_ok"] is True


def test_scanner_payloads_include_observation_only_quant_snapshot() -> None:
    selected = {
        "symbol": "005930",
        "score_total": 0.8,
        "confidence": 0.6,
        "risk_score": 0.2,
        "features": {"engine_vwap_distance": 0.01, "compat_volume_ratio": 1.2},
        "candidate": {"sources": ["top_value"]},
    }

    payload = build_candidate_selection_reason_payload(
        selected=selected,
        selected_symbol="005930",
        selected_rank=1,
        selected_score_total=0.8,
        margin_vs_second=0.1,
        critical_positive_factors=[],
        critical_negative_factors=[],
        selection_summary="selected",
        scanner_policy_trace={"playbook": "pullback"},
        playbook="pullback",
        compatibility_bias_context={},
        market_representative_guard_meta={},
        blocker_family_overlay_meta={},
        selection_veto_enforced=False,
        scanner_bias_applied=False,
        scanner_memory_bias_applied=False,
        scanner_memory_bias={},
        commander_memory_application_trace={},
        candidate_bias_adjustments=[],
        candidate_memory_bias_adjustments=[],
        candidate_symbol_prior_adjustments=[],
        selection_reason_with_bias="selected",
        runner_up_reasons=[],
    )
    compact = compact_selected_snapshot(selected)
    rows = ranking_table_rows([selected])

    assert payload["quant_factor_snapshot"]["source"] == "quant_candidate_factor_snapshot.v1"
    assert payload["quant_factor_snapshot"]["behavior_effect"] == "observation_only"
    assert compact["quant_factor_snapshot"]["source"] == "quant_candidate_factor_snapshot.v1"
    assert rows[0]["quant_factor_snapshot"]["source"] == "quant_candidate_factor_snapshot.v1"

