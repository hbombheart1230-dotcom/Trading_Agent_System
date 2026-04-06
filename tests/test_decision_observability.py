from __future__ import annotations

from libs.runtime.decision_observability import (
    build_commander_route_observability_surface,
    build_monitor_no_trade_surface,
    build_scanner_monitor_handoff_surface,
    build_strategist_policy_resolution_surface,
)


def test_build_monitor_no_trade_surface_exposes_blocker_and_distance_to_ready() -> None:
    surface = build_monitor_no_trade_surface(
        {
            "evaluated": True,
            "triggered": False,
            "reason": "below_vwap_reclaim_not_ready",
            "primary_failure_axis": "vwap_relationship",
            "reclaim_distance_to_ready": -0.012,
            "volume_distance_to_ready": -0.18,
            "breakout_distance_to_ready": 0.004,
            "transition_readiness_score": 0.82,
            "condition_scores": {"confidence_score": 0.59, "confidence_threshold": 0.60},
            "policy_alignment_summary": {
                "primary_blocker": "below_vwap_reclaim_not_ready",
                "top_failed_required_checks": ["reclaim_gate_ok"],
                "top_failed_preferred_checks": ["volume_ok"],
                "top_relaxable_gaps": ["confidence_ok"],
                "alignment_state": "partial",
            },
        },
        final_decision="WAIT",
        buy_submitted=False,
        guard_blocked=False,
        guard_reason="",
        commander_no_trade_reason_code="noop_intent_skipped",
    )

    assert surface["decision_outcome"] == "WAIT"
    assert surface["dominant_blocker"] == "below_vwap_reclaim_not_ready"
    assert surface["blocker_family"] == "vwap_relationship"
    assert surface["distance_to_ready"]["reclaim_score_gap"] == 0.012
    assert surface["near_ready_flag"] is True
    assert surface["required_checks_failed"] == ["reclaim_gate_ok"]


def test_build_strategist_policy_resolution_surface_marks_timeout_fallback() -> None:
    surface = build_strategist_policy_resolution_surface(
        strategist_output={
            "policy_source": "default_safe_policy",
            "policy_fallback_used": True,
            "monitor_entry_policy": {"schema_version": "monitor_entry_policy_schema_candidate.v1"},
        },
        strategist_llm={
            "status": "blocked",
            "latency_ms": 15234,
            "blocked": True,
            "blocked_reason": "TimeoutError: request timed out",
            "prompt_ref": "reports/llm/prompt_v3.json",
        },
        commander_context={},
    )

    assert surface["llm_attempted"] is True
    assert surface["llm_ok"] is False
    assert surface["llm_error_type"] == "TimeoutError"
    assert surface["fallback_used"] is True
    assert surface["strategy_generation_mode"] == "fallback"
    assert surface["effective_schema_version"] == "monitor_entry_policy_schema_candidate.v1"


def test_build_scanner_monitor_handoff_surface_links_top_pick_to_monitor_rejection() -> None:
    no_trade = {
        "no_trade_stage": "pre_intent_wait",
        "no_trade_reason_code": "pullback_not_mature",
        "no_trade_reason_summary": "pullback not mature",
    }
    surface = build_scanner_monitor_handoff_surface(
        selected={"symbol": "005930", "score_total": 0.91, "score_breakdown": {"momentum": 0.31, "liquidity": 0.22}},
        ranked_candidates=[
            {"symbol": "005930", "score_total": 0.91, "score_breakdown": {"momentum": 0.31}},
            {"symbol": "000660", "score_total": 0.84, "score_breakdown": {"momentum": 0.25}},
        ],
        scanner_output={"expected_monitor_block_reason": "pullback_not_mature"},
        final_decision="WAIT",
        no_trade_surface=no_trade,
        entry_info={"policy_interpretation": {"entry_style": "pullback"}},
    )

    assert surface["scanner_selected_symbol"] == "005930"
    assert surface["scanner_rank"] == 1
    assert surface["monitor_rejection_after_top_pick"] is True
    assert surface["monitor_rejection_reason_code"] == "pullback_not_mature"
    assert surface["scanner_vs_monitor_alignment"] == "expected_mismatch"


def test_build_commander_route_observability_surface_records_route_provenance() -> None:
    surface = build_commander_route_observability_surface(
        selected_route="cached_strategist",
        route_reason="cache still fresh",
        commander_decision={
            "strategist_invocation": "SKIP",
            "strategist_cache_preference_reason": "cache fresh",
            "strategist_refresh_reason": "transition_readiness_threshold",
            "policy_source": "commander_applied_policy",
            "applied_policy": {"policy_id": "policy-123"},
        },
        runtime_fast_path={"cache_age_sec": 42, "reason": "cache fresh"},
        resilience={"incident_count": 0},
        runtime_status="ok",
        runtime_transition="",
    )

    assert surface["route_selected"] == "cached_strategist"
    assert surface["strategist_call_decision"] == "skip"
    assert surface["strategist_skip_reason"] == "cache fresh"
    assert surface["cache_hit"] is True
    assert surface["cache_age_sec"] == 42
    assert surface["applied_policy_source"] == "commander_applied_policy"
    assert surface["applied_policy_id"] == "policy-123"
    assert surface["strategy_generation_mode"] == "cached"
