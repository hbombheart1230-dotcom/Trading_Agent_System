from __future__ import annotations

from libs.runtime.decision_observability import (
    build_entry_blocker_surface,
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


def test_build_entry_blocker_surface_normalizes_entry_evidence_and_blocks() -> None:
    surface = build_entry_blocker_surface(
        {
            "reason": "pullback_not_mature",
            "primary_failure_axis": "pullback_structure",
            "metrics": {
                "rebound_ok": False,
                "pullback_ok": False,
                "pullback_mature": False,
                "pullback_depth_pct": 0.0015,
                "volume_ok": False,
                "volume_ratio": 0.72,
                "confidence_score": 0.51,
                "confidence_threshold": 0.55,
                "rebound_progress": 0.33,
            },
            "policy_interpretation": {"entry_style": "pullback"},
            "chart_structure_features": {"structure": {"structure_hh_hl": "weakening"}},
            "passed_checks": [],
            "failed_checks": ["rebound_ok", "pullback_ok", "volume_ok", "structure_hh_hl=intact"],
        },
        final_decision="WAIT",
        no_trade_surface={
            "no_trade_reason_code": "pullback_not_mature",
            "dominant_blocker": "pullback_not_mature",
        },
        entry_blockers=["pullback_not_mature", "rebound_ok"],
        buy_blocked_open_position=False,
        buy_blocked_post_exit_cooldown=True,
        post_exit_cooldown_remaining_sec=120,
        open_position_count=0,
    )

    assert surface["final_decision"] == "WAIT"
    assert surface["entry_style"] == "pullback"
    assert surface["rebound_ok"] is False
    assert surface["pullback_ok"] is False
    assert surface["pullback_not_mature"] is True
    assert surface["volume_confirmation_missing"] is False
    assert surface["cooldown_blocked"] is True
    assert surface["post_exit_cooldown_remaining_sec"] == 120
    assert surface["structure_hh_hl"] == "weakening"
    assert surface["primary_blockers"][:2] == ["pullback_not_mature", "rebound_ok"]


def test_build_entry_blocker_surface_surfaces_reclaim_tuning_provenance() -> None:
    surface = build_entry_blocker_surface(
        {
            "reason": "breakout_above_recent_high_with_policy_reclaim_near_ready",
            "primary_failure_axis": "",
            "metrics": {
                "rebound_ok": True,
                "pullback_ok": False,
                "volume_ok": True,
                "volume_ratio": 1.21,
                "confidence_score": 0.61,
                "confidence_threshold": 0.55,
                "reclaim_distance_to_ready": -0.0017,
                "reclaim_gate_ok": False,
                "vwap_hold_ok": False,
                "vwap_reclaim_ok": False,
            },
            "policy_interpretation": {"entry_style": "breakout"},
            "passed_checks": ["breakout_ok"],
            "failed_checks": ["reclaim_gate_ok"],
            "policy_aware_gating": {
                "entry_tuning_flags": ["reclaim_small_relaxation_v1"],
                "reclaim_readiness_tuned": True,
                "reclaim_tuning_version": "small_relaxation_v1",
                "reclaim_tuning_scope": "below_vwap_reclaim_not_ready_only",
                "reclaim_tuning_band_used": "tuned",
                "reclaim_near_ready_distance_min": -0.0018,
            },
        },
        final_decision="BUY",
        no_trade_surface={},
        entry_blockers=[],
        buy_blocked_open_position=False,
        buy_blocked_post_exit_cooldown=False,
        post_exit_cooldown_remaining_sec=0,
        open_position_count=0,
    )

    assert surface["final_decision"] == "BUY"
    assert surface["reclaim_readiness_tuned"] is True
    assert surface["reclaim_tuning_version"] == "small_relaxation_v1"
    assert surface["reclaim_tuning_scope"] == "below_vwap_reclaim_not_ready_only"
    assert surface["reclaim_tuning_band_used"] == "tuned"
    assert surface["reclaim_near_ready_distance_min"] == -0.0018
    assert "reclaim_small_relaxation_v1" in list(surface.get("entry_tuning_flags") or [])
    assert "small_relaxation_v1" in str(surface.get("reclaim_evidence_explanation") or "")


def test_build_entry_blocker_surface_surfaces_closeout_window_block() -> None:
    surface = build_entry_blocker_surface(
        {
            "reason": "buy_blocked_closeout_window",
            "metrics": {"confidence_score": 0.62, "confidence_threshold": 0.55},
            "policy_interpretation": {"entry_style": "breakout"},
        },
        final_decision="WAIT",
        no_trade_surface={
            "no_trade_reason_code": "buy_blocked_closeout_window",
            "dominant_blocker": "buy_blocked_closeout_window",
        },
        entry_blockers=["buy_blocked_closeout_window"],
        buy_blocked_open_position=False,
        buy_blocked_closeout_window=True,
        buy_blocked_post_exit_cooldown=False,
        post_exit_cooldown_remaining_sec=0,
        open_position_count=0,
        minutes_to_close=5,
        eod_flat_cutoff_min=10,
    )

    assert surface["closeout_window_blocked"] is True
    assert surface["minutes_to_close"] == 5
    assert surface["eod_flat_cutoff_min"] == 10
    assert surface["primary_blockers"][0] == "buy_blocked_closeout_window"


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
