from __future__ import annotations

from libs.contracts.agent_outputs import build_strategist_output_artifact
from libs.runtime.strategist_explanation import build_strategist_explanation_fields


def _strategist_output() -> dict:
    return {
        "market_regime": "neutral",
        "market_sentiment": "neutral",
        "playbook": "pullback",
        "risk_tone": "conservative",
        "monitor_guidance": "defensive_exit",
        "trade_aggressiveness": "low",
        "themes": ["semiconductor"],
        "avoid_themes": ["news_only_momentum"],
        "theme_strength_packet": {
            "schema_version": "kiwoom_theme_strength.v1",
            "source": "state_mock",
            "status": "ok",
            "reason": "test_packet",
            "top_themes": ["semiconductor"],
            "theme_scores": {"semiconductor": 0.82},
        },
        "theme_source": "state_mock",
        "theme_source_status": "ok",
        "theme_source_reason": "test_packet",
        "scanner_priority": ["trading_value", "vwap_reclaim"],
        "monitor_entry_policy": {
            "threshold_policy": {
                "volume_ratio_min": 0.72,
                "require_vwap_reclaim": True,
                "require_rebound": True,
            }
        },
        "memory_packets": {
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
                "summary": "recent failures are concentrated in extended breakout entries",
                "sample_quality": {"confidence": 0.82},
            },
            "weekly_strategy_memory": {
                "status": "ok",
                "active": False,
                "sample_quality": {"confidence": 0.31},
            },
            "monthly_strategy_memory": {
                "status": "unavailable",
                "active": False,
            },
            "symbol_memory_packet": {
                "status": "ok",
                "active": True,
                "symbol": "005930",
                "trade_count": 2,
                "closed_trade_count": 1,
                "override_eligible": False,
                "override_gate_reason": "insufficient_trade_count",
                "evidence_strength": "thin",
            },
        },
        "commander_memory_policy": {
            "application_mode": "surface_only",
            "active_layers": ["daily"],
            "priority_order": ["daily", "weekly", "monthly", "symbol"],
            "symbol_memory_override_enabled": False,
            "policy_signals": {"preferred_risk_posture": "defensive"},
        },
        "scanner_memory_bias": {
            "enabled": True,
            "source_weight_delta": {"top_change_rate": -0.08},
        },
        "monitor_memory_bias": {
            "enabled": True,
            "entry_policy_delta": {"volume_ratio_min_delta": 0.03},
        },
    }


def test_strategist_explanation_fields_capture_memory_and_role_boundary() -> None:
    fields = build_strategist_explanation_fields(
        strategist_output=_strategist_output(),
        state={
            "commander_decision": {
                "strategist_invocation": "RUN_REFRESH",
                "route_selected": "full_cycle",
                "observations": {
                    "post_scanner_refresh_requested": True,
                    "post_scanner_refresh_reason": "selected_symbol_outside_cached_frame",
                    "post_scanner_refresh_selected_symbol": "005930",
                },
                "strategist_refresh_requested": True,
                "strategist_refresh_reason": "selected_symbol_outside_cached_frame",
                "strategist_refresh_context": {
                    "selected_symbol": "005930",
                    "selected_symbol_in_cached_frame": False,
                    "cached_candidate_hints": ["000660", "005930"],
                },
                "strategist_refresh_evaluated": True,
                "strategist_refresh_effective": False,
                "strategist_refresh_policy_delta_count": 0,
            }
        },
        news_evidence_ranked={
            "news_query_targets": ["KOSPI", "semiconductor"],
            "market_news_ranked": [
                {"target": "KOSPI", "sample_titles": ["foreign buying supports index"]},
            ],
            "candidate_news_ranked": [
                {"target": "005930", "sample_titles": ["chip demand recovery"]},
            ],
            "news_context": {"avg_score": 0.22},
        },
    )

    assert fields["strategy_thesis"]["selected_playbook"] == "pullback"
    assert fields["memory_usage_trace"]["layer_decisions"]["daily"]["used"] is True
    assert fields["memory_usage_trace"]["layer_decisions"]["daily"]["effect"] == "primary_strategy_memory+scanner_delta+monitor_delta"
    assert fields["memory_usage_trace"]["layer_decisions"]["daily"]["use_kind"] == "context_and_deterministic_delta"
    assert fields["memory_usage_trace"]["layer_decisions"]["daily"]["deterministic_delta_applied"] is True
    assert fields["memory_usage_trace"]["application_summary"] == {
        "context_used": True,
        "context_layer_count": 1,
        "scanner_delta_applied": True,
        "monitor_delta_applied": True,
        "deterministic_delta_applied": True,
        "llm_memory_usage_status": "not_reported",
        "causal_strategy_change_attributed": False,
    }
    assert (
        fields["memory_usage_trace"]["applied_to_strategy"]["playbook_effect"]
        == "memory_context_visible_no_attributed_playbook_change"
    )
    assert fields["memory_usage_trace"]["scanner_application"]["source_delta_keys"] == ["top_change_rate"]
    assert fields["memory_usage_trace"]["monitor_application"]["entry_delta_keys"] == ["volume_ratio_min_delta"]
    assert fields["memory_usage_trace"]["layer_decisions"]["symbol"]["used"] is False
    assert fields["memory_usage_trace"]["layer_decisions"]["symbol"]["use_kind"] == "blocked"
    assert fields["memory_usage_trace"]["layer_decisions"]["symbol"]["gate_reason"] == "insufficient_trade_count"
    assert fields["memory_usage_trace"]["layer_decisions"]["symbol"]["effect"] == "blocked:insufficient_trade_count"
    assert fields["news_usage_trace"]["source_event"] == "strategist.news_evidence_ranked"
    assert fields["scanner_handoff"]["not_responsible_for"] == ["final_symbol_selection", "final_candidate_rank"]
    assert "selected_symbol" in fields["responsibility_boundary"]["scanner_owns"]
    assert fields["strategy_refresh_trace"]["refresh_requested"] is True
    assert fields["strategy_refresh_trace"]["stages"][0]["label"] == "1차 전략 프레임"
    assert fields["strategy_refresh_trace"]["stages"][1]["reason"] == "selected_symbol_outside_cached_frame"
    assert fields["strategy_refresh_trace"]["stages"][2]["policy_delta_count"] == 0


def test_canonical_strategist_artifact_surfaces_explanation_contract() -> None:
    state = {
        "run_id": "run-explain-1",
        "ts": "2026-04-25T09:00:00+09:00",
        "runtime_phase": "intraday",
        "strategist_output": _strategist_output(),
        "strategist_news_evidence_ranked": {
            "news_query_targets": ["KOSPI"],
            "market_news_ranked": [
                {"target": "KOSPI", "sample_titles": ["market breadth improves"]},
            ],
            "candidate_news_ranked": [],
            "news_context": {"avg_score": 0.18},
        },
    }

    artifact = build_strategist_output_artifact(state)

    assert isinstance(artifact["strategy_thesis"], dict)
    assert artifact["strategy_thesis"]["selected_playbook"] == "pullback"
    assert artifact["strategy_thesis_text"]
    assert artifact["memory_usage_trace"]["layer_decisions"]["symbol"]["used"] is False
    assert artifact["news_usage_trace"]["market_headlines_used"] == ["KOSPI: market breadth improves"]
    assert artifact["trade_permission_frame"]["permission_level"] == "defensive"
    assert artifact["responsibility_boundary"]["not_responsible_for"] == ["final_symbol_selection", "order_execution"]
    assert artifact["strategy_refresh_trace"]["stages"][0]["label"] == "1차 전략 프레임"
    assert artifact["theme_source"] == "state_mock"
    assert artifact["theme_source_status"] == "ok"
    assert artifact["theme_strength_packet"]["top_themes"] == ["semiconductor"]
    assert artifact["strategy_frame"]["theme_strength"] == {"semiconductor": 0.82}
