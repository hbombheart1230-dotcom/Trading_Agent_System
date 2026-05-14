from __future__ import annotations

from libs.contracts.agent_outputs import (
    build_commander_shadow_artifact,
    build_commander_output_artifact,
    build_monitor_output_artifact,
    build_scanner_output_artifact,
    build_strategist_output_artifact,
)


def test_strategist_artifact_contains_phase1_sections() -> None:
    state = {
        "run_id": "run-s1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "candidate_symbols": ["005930", "000660", "003280"],
        "strategist_decision_frame": {
            "market_regime": "risk_on",
            "market_sentiment": "bullish",
            "playbook": "breakout",
            "pre_llm_playbook": "defensive",
            "llm_requested_playbook": "breakout",
            "requested_playbook": "breakout",
            "requested_playbook_source": "llm",
            "final_playbook": "breakout",
            "tactical_strategy": "opening_range_breakout",
            "strategy_scores": {
                "opening_range_breakout": 0.82,
                "vwap_reclaim_pullback": 0.61,
                "defensive_observe": 0.14,
            },
            "rejected_strategy_reasons": {
                "defensive_observe": "risk_on tape supports active watch",
            },
            "candidate_watch_policy": {
                "max_priority_rank": 7,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "behavior_effect": "visibility_only",
            },
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "reason_chain": ["fear eased", "breadth improved"],
        },
        "strategist_news_evidence_ranked": {
            "news_query_targets": ["semiconductor", "memory"],
            "candidate_news_ranked": [{"symbol": "005930", "title": "chip demand recovers"}],
            "market_news_ranked": [{"title": "KOSPI breadth improves"}],
            "news_context": {"headline_count": 2},
        },
        "strategist_global_sentiment_breakdown": {
            "score": 0.24,
            "status": "ok",
            "fear_index": {"level": 19.5, "level_pressure": 0.12},
            "stress_flags": ["breadth_recovery"],
        },
        "commander_decision": {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN",
            "market_regime": "risk_on",
            "session_bias": "active_selection",
            "risk_mode": "offensive",
            "allowed_playbooks": ["breakout", "pullback"],
            "banned_playbooks": ["defensive"],
            "scanner_mission": "Prioritize liquid momentum leaders.",
            "monitor_mission": "Confirm continuation quickly.",
            "llm_policy": "allow",
            "no_trade_reason_code": "NONE",
            "strategist_refresh_requested": True,
            "strategist_refresh_reason": "transition_readiness_threshold",
            "strategist_refresh_context": {
                "selected_symbol": "005930",
                "cache_age_sec": 300,
                "transition_readiness_score": 0.87,
            },
            "observations": {"market_changed": True, "last_llm_status": "ok"},
            "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            "shadow_used": True,
            "strategist_fallback_used": False,
            "decision_summary": "Commander allows offensive momentum scanning.",
        },
        "global_signal": {
            "score": 0.24,
            "fear_index": {"level": 19.5, "level_pressure": 0.12},
        },
        "strategist_output": {
            "market_regime": "risk_on",
            "market_sentiment": "bullish",
            "playbook": "breakout",
            "pre_llm_playbook": "defensive",
            "llm_requested_playbook": "breakout",
            "requested_playbook": "breakout",
            "requested_playbook_source": "llm",
            "final_playbook": "breakout",
            "tactical_strategy": "opening_range_breakout",
            "strategy_scores": {
                "opening_range_breakout": 0.82,
                "vwap_reclaim_pullback": 0.61,
                "defensive_observe": 0.14,
            },
            "rejected_strategy_reasons": {
                "defensive_observe": "risk_on tape supports active watch",
            },
            "candidate_watch_policy": {
                "max_priority_rank": 7,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "behavior_effect": "visibility_only",
            },
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "strategy_policy": {
                "market_policy": {"playbook": "breakout"},
                "commander_context": {
                    "source": "commander_decision",
                    "market_regime": "risk_on",
                    "session_bias": "active_selection",
                    "risk_mode": "offensive",
                    "decision_summary": "Commander allows offensive momentum scanning.",
                    "strategist_refresh_requested": True,
                    "strategist_refresh_reason": "transition_readiness_threshold",
                    "strategist_refresh_context": {
                        "selected_symbol": "005930",
                        "cache_age_sec": 300,
                        "transition_readiness_score": 0.87,
                    },
                },
                "strategist_plan": {
                    "selected_playbook": "breakout",
                    "candidate_hypotheses": [{"symbol": "005930", "hypothesis": "breakout setup candidate"}],
                    "symbol_constraints": {"candidate_symbols_hint": ["005930", "000660", "003280"]},
                    "entry_plan": {"setup_family": "breakout"},
                    "exit_plan": {"adaptive_exit": {"take_profit_pct": 0.03}},
                    "strategy_summary": "Strategist refined commander context into breakout plan.",
                },
                "provenance": {
                    "market_policy_owner": "commander",
                    "scanner_policy_owner": "strategist",
                    "monitor_policy_owner": "strategist",
                    "decision_policy_owner": "strategist",
                    "merged_from": ["commander_decision", "strategist_node"],
                },
            },
            "monitor_guidance": "hold_through_noise",
            "risk_tone": "normal",
            "trade_aggressiveness": "medium",
            "market_context_inputs": {"index_trend": 0.3},
            "news_query_reasoning": "macro and sector alignment",
            "news_query_targets": ["semiconductor"],
            "selected_playbook": "breakout",
            "candidate_hypotheses": [{"symbol": "005930", "hypothesis": "breakout setup candidate"}],
            "symbol_constraints": {"candidate_symbols_hint": ["005930", "000660", "003280"]},
            "entry_plan": {"setup_family": "breakout"},
            "exit_plan": {"adaptive_exit": {"take_profit_pct": 0.03}},
            "strategy_summary": "Strategist refined commander context into breakout plan.",
            "policy_provenance": {
                "market_policy_owner": "commander",
                "scanner_policy_owner": "strategist",
            },
            "market_regime_summary": "risk_on regime / bullish sentiment / trend structure with playbook breakout.",
            "monitor_entry_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "min_extended_from_vwap_pct": -0.02,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
                "reclaim_tolerance_pct": 0.0015,
                "breakout_buffer_pct": 0.0,
                "intent_cooldown_sec": 60,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            },
            "policy_rationale": "Breakout remains valid, but keep the live baseline because conviction is only moderate.",
            "policy_source": "strategist",
            "policy_validation_status": "ok",
            "policy_fallback_used": False,
            "policy_fallback_reason": "",
            "policy_validation_issues": [],
            "confidence": 0.62,
            "scanner_bias_context": {
                "prefer_shallow_pullback_candidates": True,
                "penalize_overextended": True,
                "prefer_reclaim_candidates": True,
                "prefer_volume_confirmation": False,
                "bias_strength": "low",
                "bias_source": "strategist",
            },
            "scanner_bias_summary": {
                "enabled": True,
                "active_biases": [
                    "prefer_shallow_pullback_candidates",
                    "penalize_overextended",
                    "prefer_reclaim_candidates",
                ],
                "bias_strength": "low",
                "bias_source": "strategist",
                "summary": "prefer_shallow_pullback_candidates, penalize_overextended, prefer_reclaim_candidates (low)",
            },
            "scanner_bias_validation_status": "ok",
            "scanner_bias_validation_issues": [],
            "commander_context_ref": {
                "source": "commander_decision",
                "market_regime": "risk_on",
                "session_bias": "active_selection",
                "risk_mode": "offensive",
                "command_intent": "OBSERVE_ONLY",
                "strategist_invocation": "RUN",
                "llm_policy": "allow",
                "no_trade_reason_code": "NONE",
                "strategist_refresh_requested": True,
                "strategist_refresh_reason": "transition_readiness_threshold",
                "strategist_refresh_context": {
                    "selected_symbol": "005930",
                    "cache_age_sec": 300,
                    "transition_readiness_score": 0.87,
                },
                "decision_summary": "Commander allows offensive momentum scanning.",
            },
            "commander_invocation_hint": "RUN",
            "commander_llm_policy": "allow",
            "commander_no_trade_reason_code": "NONE",
            "commander_refresh_requested": True,
            "commander_refresh_reason": "transition_readiness_threshold",
            "commander_refresh_context": {
                "selected_symbol": "005930",
                "cache_age_sec": 300,
                "transition_readiness_score": 0.87,
            },
            "shadow_used": True,
            "strategist_fallback_used": False,
        },
        "strategist_llm": {
            "status": "ok",
            "model": "minimax/minimax-m2.5",
            "prompt_hash": "prompt-hash",
            "response_hash": "response-hash",
            "prompt_ref": "reports/llm/2026-03-18/run-s1/strategist/prompt.json",
            "response_ref": "reports/llm/2026-03-18/run-s1/strategist/response.json",
        },
    }
    artifact = build_strategist_output_artifact(state)
    assert artifact["day"] == "2026-03-18"
    assert isinstance(artifact.get("market_context"), dict)
    assert isinstance(artifact.get("news_context"), dict)
    assert isinstance(artifact.get("strategy_frame"), dict)
    assert isinstance(artifact.get("policy_selected"), dict)
    assert isinstance(artifact.get("llm_trace"), dict)
    assert isinstance(artifact.get("decision_summary"), dict)
    assert isinstance(artifact.get("trace_summary"), dict)
    assert "summary" in artifact["trace_summary"]
    assert isinstance(artifact["trace_summary"].get("highlights"), list)
    assert isinstance(artifact.get("decision_frame"), dict)
    assert isinstance(artifact.get("news_evidence_ranked"), dict)
    assert isinstance(artifact.get("global_sentiment_signal"), dict)
    assert artifact.get("candidate_symbols_hint") == ["005930", "000660", "003280"]
    assert artifact["decision_frame"]["playbook"] == "breakout"
    assert artifact["tactical_strategy"] == "opening_range_breakout"
    assert artifact["strategy_scores"]["opening_range_breakout"] == 0.82
    assert artifact["candidate_watch_policy"]["max_priority_rank"] == 7
    assert artifact["strategy_detail"]["pre_llm_playbook"] == "defensive"
    assert artifact["strategy_detail"]["candidate_watch_policy"]["max_runner_ups"] == 4
    assert artifact["news_evidence_ranked"]["candidate_news_ranked"][0]["symbol"] == "005930"
    assert artifact["global_sentiment_signal"]["fear_index"]["level"] == 19.5
    assert artifact["news_evidence_missing"] is False
    assert artifact["candidate_symbols_hint_missing"] is False
    assert artifact["llm_trace"]["prompt_hash"] == "prompt-hash"
    assert artifact["llm_trace"]["response_hash"] == "response-hash"
    assert artifact["commander_context_ref"]["market_regime"] == "risk_on"
    assert artifact["selected_playbook"] == "breakout"
    assert artifact["candidate_hypotheses"][0]["symbol"] == "005930"
    assert artifact["symbol_plan"]["candidate_symbols_hint"] == ["005930", "000660", "003280"]
    assert artifact["entry_plan"]["setup_family"] == "breakout"
    assert artifact["exit_plan"]["adaptive_exit"]["take_profit_pct"] == 0.03
    assert artifact["policy_provenance"]["market_policy_owner"] == "commander"
    assert artifact["commander_invocation_hint"] == "RUN"
    assert artifact["commander_llm_policy"] == "allow"
    assert artifact["commander_no_trade_reason_code"] == "NONE"
    assert artifact["commander_refresh_requested"] is True
    assert artifact["commander_refresh_reason"] == "transition_readiness_threshold"
    assert artifact["commander_refresh_context"]["selected_symbol"] == "005930"
    assert artifact["commander_context_ref"]["strategist_refresh_requested"] is True
    assert artifact["commander_context_ref"]["strategist_refresh_reason"] == "transition_readiness_threshold"
    assert artifact["shadow_used"] is True
    assert artifact["strategist_fallback_used"] is False
    assert artifact["monitor_entry_policy"]["volume_ratio_min"] == 0.68
    assert artifact["policy_rationale"].startswith("Breakout remains valid")
    assert artifact["policy_source"] == "strategist"
    assert artifact["policy_validation_status"] == "ok"
    assert artifact["policy_fallback_used"] is False
    assert artifact["confidence"] == 0.62
    assert artifact["scanner_bias_context"]["penalize_overextended"] is True
    assert artifact["scanner_bias_summary"]["enabled"] is True
    assert artifact["scanner_bias_validation_status"] == "ok"
    assert "Strategist refined commander context" in artifact["strategy_summary"]


def test_scanner_artifact_contains_filter_funnel_and_selection_reason_detail() -> None:
    state = {
        "run_id": "run-scan-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "scanner_output": {
            "candidate_pool_size": 2,
            "candidate_count": 2,
            "candidate_source": "kiwoom_market_data",
            "playbook": "breakout",
            "policy_source": "strategist",
            "applied_policy_present": True,
            "monitor_entry_policy_summary": {
                "timeframe_minutes": 1,
                "volume_ratio_min": 0.68,
                "pullback_min_pct": 0.008,
            },
            "scanner_bias_context": {
                "prefer_shallow_pullback_candidates": True,
                "penalize_overextended": True,
                "bias_strength": "low",
            },
            "scanner_bias_applied": True,
            "scanner_bias_summary": {
                "enabled": True,
                "active_biases": ["prefer_shallow_pullback_candidates", "penalize_overextended"],
                "bias_strength": "low",
                "summary": "prefer_shallow_pullback_candidates, penalize_overextended (low)",
            },
            "candidate_bias_adjustments": [
                {
                    "symbol": "005930",
                    "bias_adjustment": 0.003,
                    "bias_adjustments": [{"rule": "prefer_shallow_pullback_candidates", "reason": "shallow pullback preference applied"}],
                }
            ],
            "selection_reason_with_bias": "value and theme alignment | bias: prefer_shallow_pullback_candidates, penalize_overextended (low)",
            "entry_compatibility_score": 0.86,
            "compatibility_bias": 0.018,
            "compatibility_components": {
                "vwap_proximity_score": 0.9,
                "volume_readiness_score": 0.84,
                "breakout_readiness_score": 0.72,
                "reclaim_proximity": 0.9,
            },
            "expected_monitor_block_reason": "",
            "dominant_block_reason": "volume_confirmation_missing",
            "dominant_block_reason_ratio": 0.55,
            "bias_scale": 0.15,
            "soft_penalty": 0.05,
            "compatibility_score_pre_penalty": 0.91,
            "compatibility_score_post_penalty": 0.86,
            "compatibility_trace": {
                "compatibility_source": "minute_eval",
                "triggered_path": "pullback_volume_path",
            },
            "pre_adjust_score_total": 1.302,
            "post_adjust_score_total": 1.32,
            "quote_data_diagnostic": {
                "live_equity_candidates": 2,
                "quote_rows_with_activity": 0,
                "feature_refresh_forced": True,
                "feature_refresh_reason": "quote_metrics_missing_rebuild_feature_engine",
            },
        },
        "scanner_candidate_pool": {
            "candidate_source": "kiwoom_market_data",
            "candidate_pool_before_filter": 5,
            "candidate_pool_after_filter": 2,
            "theme_filter_applied": True,
            "avoid_filter_applied": True,
        },
        "ranked_candidates": [
            {
                "symbol": "005930",
                "score_total": 1.32,
                "risk_score": 0.21,
                "confidence": 0.82,
                "why": "top ranked",
                "score_breakdown": {"top_value": 0.8, "risk_penalty": -0.1},
            },
            {
                "symbol": "000660",
                "score_total": 1.01,
                "risk_score": 0.34,
                "confidence": 0.74,
                "why": "runner up",
                "score_breakdown": {"top_value": 0.5, "risk_penalty": -0.2},
            },
        ],
        "selected": {
            "symbol": "005930",
            "score_total": 1.32,
            "risk_score": 0.21,
            "confidence": 0.82,
            "why": "value and theme alignment",
            "score_breakdown": {"top_value": 0.8, "risk_penalty": -0.1},
            "candidate": {"source_scores": {"top_value": 2.1, "sector_theme": 1.7}},
        },
        "scanner_runner_up_reasons": [{"symbol": "000660", "why_lost": ["lower total score"]}],
        "scanner_candidate_ranking_table": {
            "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
            "rows": [
                {"rank": 1, "symbol": "005930", "score_total": 1.32, "score_breakdown": {"top_value": 0.8}, "risk_score": 0.21, "confidence": 0.82},
                {"rank": 2, "symbol": "000660", "score_total": 1.01, "score_breakdown": {"top_value": 0.5}, "risk_score": 0.34, "confidence": 0.74},
            ],
        },
        "scanner_candidate_selection_reason": {
            "selected_symbol": "005930",
            "selected_rank": 1,
            "selected_score_total": 1.32,
            "margin_vs_second": 0.31,
            "critical_positive_factors": ["top_value:0.800"],
            "critical_negative_factors": ["risk_penalty:-0.100"],
            "selection_summary": "value and theme alignment",
            "why_selected": ["highest total score (1.320)"],
            "runner_ups_lost": [{"symbol": "000660", "why_lost": ["lower total score"]}],
            "playbook": "breakout",
            "policy_source": "strategist",
            "applied_policy_present": True,
            "monitor_entry_policy_summary": {
                "timeframe_minutes": 1,
                "volume_ratio_min": 0.68,
                "pullback_min_pct": 0.008,
            },
            "scanner_bias_applied": True,
            "scanner_bias_summary": {
                "enabled": True,
                "active_biases": ["prefer_shallow_pullback_candidates", "penalize_overextended"],
                "bias_strength": "low",
                "summary": "prefer_shallow_pullback_candidates, penalize_overextended (low)",
            },
            "candidate_bias_adjustments": [
                {
                    "symbol": "005930",
                    "bias_adjustment": 0.003,
                    "bias_adjustments": [{"rule": "prefer_shallow_pullback_candidates", "reason": "shallow pullback preference applied"}],
                }
            ],
            "selection_reason_with_bias": "value and theme alignment | bias: prefer_shallow_pullback_candidates, penalize_overextended (low)",
            "entry_compatibility_score": 0.86,
            "compatibility_bias": 0.018,
            "compatibility_components": {
                "vwap_proximity_score": 0.9,
                "volume_readiness_score": 0.84,
                "breakout_readiness_score": 0.72,
                "reclaim_proximity": 0.9,
            },
            "expected_monitor_block_reason": "",
            "compatibility_trace": {
                "compatibility_source": "minute_eval",
                "triggered_path": "pullback_volume_path",
            },
            "pre_adjust_score_total": 1.302,
            "post_adjust_score_total": 1.32,
        },
    }
    artifact = build_scanner_output_artifact(state)
    assert isinstance(artifact.get("candidate_pool_snapshot"), dict)
    assert isinstance(artifact.get("filter_funnel"), dict)
    assert isinstance(artifact.get("selection_reason_detail"), dict)
    detail = artifact["selection_reason_detail"]
    assert detail["selected_symbol"] == "005930"
    assert "selected_score_total" in detail
    assert "margin_vs_second" in detail
    assert isinstance(detail.get("critical_positive_factors"), list)
    assert isinstance(detail.get("critical_negative_factors"), list)
    assert isinstance(artifact.get("trace_summary"), dict)
    assert artifact["trace_summary"]["selected_symbol"] == "005930"
    assert artifact["trace_summary"]["runner_up_symbol"] == "000660"
    assert artifact["trace_summary"]["candidate_count"] == 2
    assert isinstance(artifact["trace_summary"].get("highlights"), list)
    assert artifact["candidate_selection_reason"]["selected_symbol"] == "005930"
    assert artifact["candidate_ranking_table"]["rows"][1]["symbol"] == "000660"
    assert artifact["runner_up_symbol"] == "000660"
    assert artifact["score_breakdown_by_symbol"]["005930"]["top_value"] == 0.8
    assert artifact["confidence_by_symbol"]["000660"] == 0.74
    assert artifact["risk_score_by_symbol"]["005930"] == 0.21
    assert artifact["ranking_table_missing"] is False
    assert isinstance(artifact.get("rejection_summary"), list)
    assert artifact["playbook"] == "breakout"
    assert artifact["policy_source"] == "strategist"
    assert artifact["applied_policy_present"] is True
    assert artifact["monitor_entry_policy_summary"]["volume_ratio_min"] == 0.68
    assert artifact["entry_compatibility_score"] == 0.86
    assert artifact["compatibility_bias"] == 0.018
    assert artifact["compatibility_components"]["vwap_proximity_score"] == 0.9
    assert artifact["dominant_block_reason"] == "volume_confirmation_missing"
    assert artifact["dominant_block_reason_ratio"] == 0.55
    assert artifact["bias_scale"] == 0.15
    assert artifact["soft_penalty"] == 0.05
    assert artifact["compatibility_score_pre_penalty"] == 0.91
    assert artifact["compatibility_score_post_penalty"] == 0.86
    assert artifact["compatibility_trace"]["compatibility_source"] == "minute_eval"
    assert artifact["pre_adjust_score_total"] == 1.302
    assert artifact["post_adjust_score_total"] == 1.32
    assert artifact["quote_data_diagnostic"]["feature_refresh_forced"] is True
    assert artifact["scanner_bias_applied"] is True
    assert artifact["scanner_bias_summary"]["enabled"] is True
    assert artifact["candidate_bias_adjustments"][0]["symbol"] == "005930"
    assert "bias:" in artifact["selection_reason_with_bias"]


def test_strategist_artifact_records_policy_fallback_metadata() -> None:
    state = {
        "run_id": "run-s1-fallback",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "pullback",
            "themes": ["semiconductor"],
            "avoid_themes": [],
            "strategy_policy": {
                "market_policy": {"playbook": "pullback"},
                "monitor_policy": {"entry_policy": {"volume_ratio_min": 0.68}},
            },
            "monitor_entry_policy": {
                "timeframe_minutes": 1,
                "volume_ratio_min": 0.68,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
            },
            "policy_rationale": "Invalid draft was replaced by the conservative live baseline.",
            "policy_validation_status": "fallback_invalid",
            "policy_fallback_used": True,
            "policy_fallback_reason": "invalid_fields=timeframe_minutes,volume_ratio_min",
            "policy_validation_issues": ["timeframe_minutes:out_of_bounds:30.0"],
        },
        "strategist_llm": {"status": "ok"},
    }

    artifact = build_strategist_output_artifact(state)
    assert artifact["policy_validation_status"] == "fallback_invalid"
    assert artifact["policy_fallback_used"] is True
    assert "invalid_fields=" in artifact["policy_fallback_reason"]
    assert artifact["policy_validation_issues"] == ["timeframe_minutes:out_of_bounds:30.0"]


def test_strategist_artifact_surfaces_memory_packet_visibility() -> None:
    state = {
        "run_id": "run-s1-memory",
        "started_at": "2026-04-20T09:05:00+00:00",
        "runtime_phase": "session",
        "read_model_facts_summary": {
            "present": True,
            "recent_trade_count": 5,
            "symbol_pattern_count": 2,
            "symbols": ["005930", "000660"],
            "daily_summary_present": False,
        },
        "recent_strategy_feedback": {
            "status": "ok",
            "feedback_window_size": 12,
            "top_recent_strengths": ["s1"],
            "top_recent_weaknesses": ["w1", "w2"],
            "suggested_report_focus": ["exit_quality", "scanner_fit"],
            "advisory_only": True,
        },
        "reporter_feedback_packet": {
            "available": False,
            "status": "auto_ignored",
            "consumed": False,
            "confidence": "none",
            "recommendation": ["tighten_breakout_confirmation"],
        },
        "strategy_memory": {
            "status": "empty",
            "best_playbooks": [],
            "worst_playbooks": ["breakout"],
            "recent_failures": ["volume_confirmation_failed"],
            "recent_success_patterns": [],
        },
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "pullback",
            "themes": ["semiconductor"],
            "commander_refresh_requested": True,
            "commander_refresh_reason": "selected_symbol_refresh",
            "commander_refresh_context": {
                "requested": True,
                "reason": "selected_symbol_refresh",
                "refresh_scope": "selected_symbol_review",
                "selected_symbol": "356680",
                "hold_repeat_count_max": 3,
                "selected_hold_repeat_count": 1,
                "requires_policy_delta": True,
                "selected_symbol_memory": {},
            },
            "read_model_facts_summary": {
                "present": True,
                "recent_trade_count": 5,
                "symbol_pattern_count": 2,
                "symbols": ["005930", "000660"],
                "daily_summary_present": False,
            },
            "recent_strategy_feedback": {
                "status": "ok",
                "feedback_window_size": 12,
                "top_recent_strengths": ["s1"],
                "top_recent_weaknesses": ["w1", "w2"],
                "suggested_report_focus": ["exit_quality", "scanner_fit"],
                "advisory_only": True,
            },
            "reporter_feedback_packet": {
                "available": False,
                "status": "auto_ignored",
                "source_available": True,
                "consumed": False,
                "feedback_gate_reason": "low_confidence",
                "confidence": "none",
                "recommendation": ["tighten_breakout_confirmation"],
            },
            "strategy_memory": {
                "status": "empty",
                "requested_day": "2026-04-20",
                "day": "2026-04-17",
                "best_playbooks": [],
                "worst_playbooks": ["breakout"],
                "recent_failures": ["volume_confirmation_failed"],
                "recent_success_patterns": [],
            },
            "selected_symbol_memory": {},
        },
    }

    artifact = build_strategist_output_artifact(state)
    visibility = artifact["memory_packet_visibility"]
    assert visibility["read_model_facts"]["present"] is True
    assert visibility["read_model_facts"]["recent_trade_count"] == 5
    assert visibility["read_model_facts"]["symbol_pattern_count"] == 2
    assert visibility["recent_strategy_feedback"]["feedback_window_size"] == 12
    assert visibility["recent_strategy_feedback"]["weakness_count"] == 2
    assert visibility["reporter_feedback_packet"]["status"] == "auto_ignored"
    assert visibility["reporter_feedback_packet"]["source_available"] is True
    assert visibility["reporter_feedback_packet"]["feedback_gate_reason"] == "low_confidence"
    assert visibility["strategy_memory"]["status"] == "empty"
    assert visibility["strategy_memory"]["requested_day"] == "2026-04-20"
    assert visibility["strategy_memory"]["resolved_day"] == "2026-04-17"
    assert visibility["selected_symbol_memory"]["present"] is False
    assert visibility["selected_symbol_memory"]["empty_state"] is True
    assert visibility["selected_symbol_memory"]["symbol"] == "356680"
    assert visibility["commander_refresh_context"]["requested"] is True
    assert visibility["commander_refresh_context"]["reason"] == "selected_symbol_refresh"
    assert visibility["commander_memory_policy"]["present"] is False
    assert visibility["memory_packets"]["daily"]["status"] == ""


def test_strategist_artifact_memory_visibility_prefers_open_position_refresh_context() -> None:
    state = {
        "run_id": "run-s1-open-refresh",
        "started_at": "2026-04-20T09:10:00+00:00",
        "runtime_phase": "session",
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "defensive",
            "commander_refresh_requested": True,
            "commander_refresh_reason": "repeated_hold_monitor_only",
            "commander_refresh_context": {
                "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
                "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
            },
            "commander_open_position_refresh_context": {
                "refresh_scope": "open_position_monitor_refresh",
                "selected_symbol": "000660",
                "hold_repeat_count_max": 3,
                "selected_hold_repeat_count": 3,
                "carry_state": "overnight_open",
                "carry_risk_bias": "elevated",
                "carry_risk_reason": "overnight_open_needs_confirmation",
                "session_open_recovery_assessment": {"evaluated": True, "recovery_state": "mixed"},
            },
            "selected_symbol_memory": {
                "symbol": "000660",
                "trade_count": 11,
                "closed_trade_count": 9,
                "win_rate": 0.5555,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            },
        },
    }

    artifact = build_strategist_output_artifact(state)
    visibility = artifact["memory_packet_visibility"]["commander_refresh_context"]
    assert visibility["selected_symbol"] == "000660"
    assert visibility["refresh_scope"] == "open_position_monitor_refresh"
    assert visibility["hold_repeat_count_max"] == 3
    assert visibility["selected_hold_repeat_count"] == 3
    assert visibility["requires_policy_delta"] is True
    assert visibility["carry_state"] == "overnight_open"
    assert visibility["carry_risk_bias"] == "elevated"
    assert visibility["session_open_recovery_evaluated"] is True


def test_strategist_artifact_memory_visibility_includes_commander_memory_policy() -> None:
    state = {
        "run_id": "run-s1-memory-policy",
        "started_at": "2026-04-21T07:10:00+00:00",
        "runtime_phase": "session",
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "defensive",
            "commander_memory_policy": {
                "application_mode": "surface_only",
                "active_layers": ["daily", "symbol"],
                "priority_order": ["daily", "symbol", "weekly", "monthly"],
                "symbol_memory_override_enabled": True,
                "scanner_bias_enabled": True,
                "monitor_bias_enabled": True,
            },
            "scanner_memory_bias": {
                "enabled": True,
                "active_layers": ["daily", "symbol"],
                "source_weight_delta": {"top_value": 0.015, "top_change_rate": -0.02},
                "symbol_adjustments": {"000660": {"delta": 0.015, "reason": "dominant_playbook:defensive"}},
                "bias_source": "commander_memory_bias.v1",
            },
            "monitor_memory_bias": {
                "enabled": True,
                "active_layers": ["daily", "symbol"],
                "entry_policy_delta": {"volume_ratio_min": 0.03, "max_extended_from_vwap_pct": -0.01},
                "risk_posture": "defensive",
                "bias_source": "commander_memory_bias.v1",
            },
            "memory_packets": {
                "daily_strategy_memory": {
                    "status": "ok",
                    "active": True,
                    "best_playbooks": ["defensive"],
                },
                "weekly_strategy_memory": {"status": "unavailable", "active": False},
                "monthly_strategy_memory": {"status": "unavailable", "active": False},
                "symbol_memory_packet": {
                    "status": "ok",
                    "active": True,
                    "symbol": "000660",
                    "override_eligible": True,
                    "trade_count": 8,
                },
            },
        },
    }

    artifact = build_strategist_output_artifact(state)
    visibility = artifact["memory_packet_visibility"]
    assert visibility["commander_memory_policy"]["present"] is True
    assert visibility["commander_memory_policy"]["application_mode"] == "surface_only"
    assert visibility["commander_memory_policy"]["active_layers"] == ["daily", "symbol"]
    assert visibility["scanner_memory_bias"]["present"] is True
    assert visibility["scanner_memory_bias"]["enabled"] is True
    assert visibility["scanner_memory_bias"]["active_layers"] == ["daily", "symbol"]
    assert visibility["scanner_memory_bias"]["source_delta_keys"] == ["top_value", "top_change_rate"]
    assert visibility["scanner_memory_bias"]["symbol_adjustment_count"] == 1
    assert visibility["monitor_memory_bias"]["present"] is True
    assert visibility["monitor_memory_bias"]["enabled"] is True
    assert visibility["monitor_memory_bias"]["active_layers"] == ["daily", "symbol"]
    assert visibility["monitor_memory_bias"]["entry_delta_keys"] == ["volume_ratio_min", "max_extended_from_vwap_pct"]
    assert visibility["monitor_memory_bias"]["risk_posture"] == "defensive"
    assert visibility["memory_packets"]["daily"]["status"] == "ok"
    assert visibility["memory_packets"]["symbol"]["symbol"] == "000660"
    assert visibility["memory_packets"]["symbol"]["override_eligible"] is True


def test_monitor_artifact_contains_evaluation_and_action_sections() -> None:
    state = {
        "run_id": "run-mon-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 1},
        "monitor_posture": "holding",
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "hold"},
        "monitor_entry": {
            "triggered": False,
            "pattern": "",
            "reason": "no_breakout_signal",
            "failed_checks": ["breakout_ok"],
            "passed_checks": ["vwap_hold_ok"],
            "thresholds": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
            },
            "applied_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
            },
            "received_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.68,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.07,
            },
            "received_policy_source": "commander_applied_policy",
            "effective_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.82,
                "max_extended_from_vwap_pct": 0.05,
                "pullback_min_pct": 0.008,
                "pullback_max_pct": 0.05,
                "adjustments": ["playbook:defensive", "risk_tone:conservative"],
            },
            "effective_policy_source": "monitor_frame_adjusted",
            "effective_policy_source_chain": [
                "commander_applied_policy",
                "strategy_frame_adjustment",
                "monitor_effective_policy",
            ],
            "policy_adjustments": {
                "inputs": {
                    "playbook": "defensive",
                    "monitor_guidance": "defensive_exit",
                    "risk_tone": "conservative",
                    "trade_aggressiveness": "low",
                },
                "applied_rules": ["playbook:defensive", "risk_tone:conservative"],
                "changed_fields": ["volume_ratio_min", "max_extended_from_vwap_pct", "pullback_max_pct"],
            },
            "policy_adjustment_summary": "defensive + conservative adjusted volume_ratio_min, max_extended_from_vwap_pct, pullback_max_pct",
            "effective_policy_deltas": [
                {"field": "volume_ratio_min", "from": 0.68, "to": 0.82},
                {"field": "max_extended_from_vwap_pct", "from": 0.13, "to": 0.05},
                {"field": "pullback_max_pct", "from": 0.07, "to": 0.05},
            ],
            "threshold_margins": {"volume_ratio": {"actual": 0.7, "limit": 0.8}},
            "guard_blocked": False,
            "confidence": 0.65,
        },
        "monitor_exit": {
            "symbol": "005930",
            "price": 70500,
            "avg_price": 70000,
            "peak_price": 71200,
            "monitor_reason": "hold",
            "reason": "",
            "active_exit_axis": "vwap_hold",
            "watch_axes": ["vwap", "prior_low"],
            "triggered": False,
            "sell_guard_blocked": False,
            "thresholds": {"stop_loss_pct": 0.02, "take_profit_pct": 0.03},
        },
    }
    artifact = build_monitor_output_artifact(state)
    assert isinstance(artifact.get("position_snapshot"), dict)
    assert isinstance(artifact.get("monitor_evaluation"), dict)
    assert isinstance(artifact.get("monitor_action_decision"), dict)
    assert "triggered_rules" in artifact["monitor_evaluation"]
    assert "blocked_rules" in artifact["monitor_evaluation"]
    assert "action_reason_human" in artifact["monitor_action_decision"]
    assert artifact.get("decision_phase") == "hold"
    assert artifact.get("decision_action") == "hold"
    assert artifact.get("decision_status") in {"skipped", "blocked", "unavailable"}
    assert isinstance(artifact.get("secondary_reason_codes"), list)
    assert isinstance(artifact.get("threshold_snapshot"), dict)
    assert isinstance(artifact.get("signal_snapshot"), dict)
    assert isinstance(artifact.get("market_snapshot_refs"), dict)
    assert isinstance(artifact.get("applied_policy"), dict)
    assert isinstance((artifact.get("threshold_snapshot") or {}).get("applied_policy"), dict)
    assert artifact.get("applied_policy", {}).get("volume_ratio_min") == 0.68
    assert artifact.get("threshold_snapshot", {}).get("applied_policy", {}).get("pullback_min_pct") == 0.008
    assert artifact.get("received_policy", {}).get("volume_ratio_min") == 0.68
    assert artifact.get("effective_policy", {}).get("volume_ratio_min") == 0.82
    assert artifact.get("effective_policy_source") == "monitor_frame_adjusted"
    assert artifact.get("threshold_snapshot", {}).get("effective_policy", {}).get("max_extended_from_vwap_pct") == 0.05
    assert artifact.get("policy_adjustment_summary")
    assert artifact.get("effective_policy_deltas")[0]["field"] == "volume_ratio_min"
    assert artifact.get("intent_emitted") is False
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Hold:")
    assert len(decision_summary) <= 120


def test_monitor_artifact_marks_buy_intent_with_entry_phase() -> None:
    state = {
        "run_id": "run-mon-buy",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "BUY", "entry_exit_reason": "pullback_reclaim_confirmed"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": True,
            "pattern": "pullback_vwap_reclaim",
            "reason": "pullback_reclaim_confirmed",
            "signal_chain": ["reclaim", "volume_confirmation"],
            "thresholds": {"volume_ratio_min": 0.8},
            "metrics": {"volume_ratio": 1.1},
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "thresholds": {}, "watch_axes": []},
        "intents": [{"intent_id": "intent-buy-1", "side": "BUY", "symbol": "005930"}],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "entry"
    assert artifact.get("decision_action") == "buy"
    assert artifact.get("decision_status") == "ok"
    assert artifact.get("intent_emitted") is True
    assert artifact.get("intent_id") == "intent-buy-1"
    assert artifact.get("evidence_quality") in {"strong", "partial"}
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Entry:")
    assert "BUY" in decision_summary


def test_monitor_artifact_marks_sell_intent_with_exit_phase() -> None:
    state = {
        "run_id": "run-mon-sell",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 1},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "SELL", "entry_exit_reason": "confirmed_exit_signal"},
        "monitor_entry": {"evaluated": False, "triggered": False},
        "monitor_exit": {
            "symbol": "005930",
            "price": 70100,
            "reason": "vwap_breakdown",
            "monitor_reason": "confirmed_exit_signal",
            "triggered": True,
            "exit_signal_detected": True,
            "watch_axes": ["vwap"],
            "thresholds": {"vwap_breakdown_pct": 0.002},
        },
        "monitor_exit_decision_detail": {"triggered_rule": "vwap_breakdown"},
        "intents": [{"intent_id": "intent-sell-1", "side": "SELL", "symbol": "005930"}],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "exit"
    assert artifact.get("decision_action") == "sell"
    assert artifact.get("decision_status") == "ok"
    assert artifact.get("primary_reason_code") in {"vwap_breakdown", "confirmed_exit_signal"}
    assert artifact.get("intent_emitted") is True
    decision_summary = str(artifact.get("decision_summary") or "")
    assert decision_summary.startswith("Exit:")


def test_monitor_artifact_mirrors_policy_trace_from_state_outputs() -> None:
    state = {
        "run_id": "run-mon-trace",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {
            "selected_symbol": "005930",
            "intent_side": "NOOP",
            "entry_exit_reason": "pullback_not_mature",
            "policy_ref": {"monitor_mission": "Require cleaner confirmation."},
            "entry_check_summary": "mission=Require cleaner confirmation. | reason=pullback_not_mature",
            "entry_blockers": ["WAIT_FOR_CONFIRMATION", "pullback_not_mature"],
            "timing_assessment": {"entry_pattern": "", "entry_reason": "pullback_not_mature"},
            "exit_trigger_basis": {"exit_reason": "no_position"},
            "commander_context_consumed": True,
            "consumed_fields": ["monitor_mission", "flow_instruction", "no_trade_reason_code"],
            "shadow_used": True,
            "strategist_fallback_used": False,
        },
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "pullback_not_mature",
            "failed_checks": ["pullback_mature", "volume_ok"],
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "reason": "no_position", "thresholds": {}, "watch_axes": []},
        "monitor_action_decision": {
            "policy_ref": {"monitor_mission": "Require cleaner confirmation."},
            "entry_check_summary": "mission=Require cleaner confirmation. | reason=pullback_not_mature",
            "entry_blockers": ["WAIT_FOR_CONFIRMATION", "pullback_not_mature"],
            "exit_trigger_basis": {"exit_reason": "no_position"},
            "commander_context_consumed": True,
            "consumed_fields": ["monitor_mission", "flow_instruction", "no_trade_reason_code"],
            "shadow_used": True,
            "strategist_fallback_used": False,
        },
    }

    artifact = build_monitor_output_artifact(state)
    assert artifact.get("commander_context_consumed") is True
    assert artifact.get("policy_ref", {}).get("monitor_mission") == "Require cleaner confirmation."
    assert artifact.get("entry_check_summary") == "mission=Require cleaner confirmation. | reason=pullback_not_mature"
    assert artifact.get("entry_blockers") == ["WAIT_FOR_CONFIRMATION", "pullback_not_mature"]
    assert artifact.get("exit_trigger_basis", {}).get("exit_reason") == "no_position"
    assert artifact.get("shadow_used") is True
    assert artifact.get("strategist_fallback_used") is False
    assert artifact.get("decision_trace", {}).get("commander_context_consumed") is True


def test_monitor_artifact_no_intent_summary_is_human_readable() -> None:
    state = {
        "run_id": "run-mon-noop",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "too_extended_from_vwap"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "too_extended_from_vwap",
            "failed_checks": ["extension_ok"],
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "reason": "", "thresholds": {}, "watch_axes": []},
        "intents": [],
    }
    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "no_intent"
    summary = str(artifact.get("decision_summary") or "")
    assert summary.startswith("No action:")
    assert len(summary) <= 120


def test_monitor_artifact_prefers_entry_reason_when_flat_and_minute_data_missing() -> None:
    state = {
        "run_id": "run-mon-minute-missing",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "minute_candle_missing"},
        "monitor_entry": {
            "evaluated": False,
            "triggered": False,
            "reason": "minute_candle_missing",
            "metrics": {"bar_count": 59, "inferred_spacing_minutes": 1440.0, "series_class": "daily_or_higher"},
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "reason": "no_position", "thresholds": {}, "watch_axes": []},
        "intents": [],
    }

    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "no_intent"
    assert artifact.get("primary_reason_code") == "minute_candle_missing"
    assert "insufficient data" in str(artifact.get("decision_summary") or "").lower()


def test_monitor_artifact_does_not_label_structural_wait_as_price_unavailable() -> None:
    state = {
        "run_id": "run-mon-structural-wait",
        "started_at": "2026-04-20T10:00:00+00:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "069540", "intent_side": "NOOP", "entry_exit_reason": "still_overextended_after_pullback"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "still_overextended_after_pullback",
            "failed_checks": ["extension_ok", "volume_ok", "rebound_ok"],
            "metrics": {
                "minute_source_present": True,
                "minute_source_used": "state.minute_ohlcv_by_symbol",
                "current_price": 6500.0,
            },
        },
        "monitor_exit": {"symbol": "069540", "price": None, "reason": "no_position", "thresholds": {}, "watch_axes": []},
        "intents": [],
    }

    artifact = build_monitor_output_artifact(state)
    assert artifact.get("decision_phase") == "no_intent"
    assert artifact.get("primary_reason_code") == "still_overextended_after_pullback"
    assert artifact.get("decision_status") == "blocked"
    summary = str(artifact.get("decision_summary") or "")
    assert summary.startswith("No action:")
    assert "insufficient data" not in summary.lower()


def test_monitor_artifact_surfaces_monitor_memory_bias_at_top_level() -> None:
    state = {
        "run_id": "run-mon-memory-bias",
        "started_at": "2026-04-23T09:10:00+09:00",
        "runtime_phase": "session",
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "breakout_not_ready"},
        "monitor_entry": {
            "evaluated": True,
            "triggered": False,
            "reason": "breakout_not_ready",
            "monitor_memory_bias_applied": True,
            "monitor_memory_bias_summary": {"enabled": True, "entry_delta_keys": ["breakout_buffer_pct"]},
            "monitor_memory_bias_deltas": [{"field": "breakout_buffer_pct", "delta": 0.0015, "from": 0.0, "to": 0.0015}],
        },
        "monitor_exit": {"symbol": "005930", "price": 70500, "reason": "no_position", "thresholds": {}, "watch_axes": []},
        "intents": [],
    }

    artifact = build_monitor_output_artifact(state)
    assert artifact.get("monitor_memory_bias_applied") is True
    assert artifact.get("monitor_memory_bias_summary", {}).get("enabled") is True
    assert artifact.get("monitor_memory_bias_deltas", [])[0]["field"] == "breakout_buffer_pct"


def test_commander_artifact_uses_kst_day_for_utc_boundary_timestamp() -> None:
    artifact = build_commander_output_artifact(
        {
            "run_id": "run-cmd-kst-day",
            "started_at": "2026-04-22T23:35:00+00:00",
            "runtime_phase": "preopen",
            "runtime_status": "preopen_ready",
            "path": "preopen_strategist",
        },
        mode="integrated_chain",
        phase="preopen",
        path="preopen_strategist",
        status="preopen_ready",
    )
    assert artifact["day"] == "2026-04-23"


def test_commander_artifact_routes_monitor_only_and_tracks_flags() -> None:
    state = {
        "run_id": "run-cmd-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "commander_decision": {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "SKIP",
            "market_regime": "neutral",
            "session_bias": "position_management",
            "risk_mode": "balanced",
            "allowed_playbooks": ["pullback", "defensive"],
            "banned_playbooks": ["reversal"],
            "scanner_mission": "Keep candidate refresh narrow while positions are open.",
            "monitor_mission": "Focus on hold versus exit confirmation first.",
            "llm_policy": "allow_if_context_changed",
            "no_trade_reason_code": "POSITION_ALREADY_OPEN",
            "strategist_refresh_requested": False,
            "strategist_refresh_reason": "",
            "strategist_refresh_context": {},
            "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            "shadow_used": True,
            "strategist_fallback_used": False,
            "decision_summary": "Commander prioritizes managing open exposure before new entries.",
            "applied_policy": {
                "timeframe_minutes": 1,
                "volume_ratio_min": 0.68,
                "pullback_min_pct": 0.008,
            },
            "policy_source": "strategist",
            "policy_validation_status": "ok",
            "policy_fallback_used": False,
            "policy_fallback_reason": "",
            "policy_partial_normalized": True,
            "policy_default_filled_fields": ["enabled"],
            "policy_validation_missing_fields": ["enabled"],
            "policy_validation_invalid_fields": [],
            "override_reason": "",
            "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
        },
        "commander_shadow_runtime": {
            "strategist_executed": False,
            "llm_called_by_strategist": False,
            "used_cached_strategist": False,
            "market_changed": False,
            "repeated_same_context": True,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
            "prior_context": {"selected_symbol": "005930", "playbook": "pullback", "market_regime": "neutral"},
        },
        "runtime_fast_path": {"reason": "holding_position_monitor_only"},
        "portfolio_snapshot": {"positions": [{"symbol": "005930"}, {"symbol": "000660"}], "cash": 1000},
        "risk_context": {
            "capital_available_for_sizing": 7500000.0,
            "cash_truth_source": "kiwoom.kt00001",
            "cash_truth_available": True,
            "broker_orderable_amount": 7500000.0,
            "broker_withdrawable_cash": 7600000.0,
            "broker_deposit": 8000000.0,
        },
        "portfolio_preflight": {"status": "ok", "blocked": False},
        "monitor": {"open_position_count": 2, "buy_blocked_open_position": True},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "buy_blocked_open_position"},
        "selected": {"symbol": "005930", "score_total": 0.78},
    }
    artifact = build_commander_output_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain_monitor_only",
        status="ok",
        reason="holding_position_monitor_only",
    )
    assert artifact.get("selected_route") == "monitor_only"
    assert artifact.get("open_position_count") == 2
    assert artifact.get("open_position_symbols") == ["005930", "000660"]
    assert artifact.get("runtime_mode") == "integrated_chain"
    assert artifact.get("runtime_phase") == "session"
    assert isinstance(artifact.get("route_reason_codes"), list)
    assert artifact.get("cooldown_applied") is False
    assert artifact.get("market_regime") == "neutral"
    assert artifact.get("session_bias") == "position_management"
    assert artifact.get("risk_mode") == "balanced"
    assert artifact.get("allowed_playbooks") == ["pullback", "defensive"]
    assert artifact.get("scanner_mission") == "Keep candidate refresh narrow while positions are open."
    assert artifact.get("llm_invocation_policy") == "allow_if_context_changed"
    assert "open exposure" in str(artifact.get("decision_summary") or "")
    assert artifact.get("shadow_used") is True
    assert artifact.get("shadow_reason_code") == "POSITION_ALREADY_OPEN"
    assert artifact.get("shadow_alignment") == "aligned"
    assert artifact.get("source_priority")[0] == "shadow_commander"
    assert artifact.get("strategist_fallback_used") is False
    assert artifact.get("strategist_refresh_requested") is False
    assert artifact.get("strategist_refresh_reason") == ""
    assert artifact.get("runtime_refresh_requested") is False
    assert artifact.get("runtime_refresh_reason") == ""
    assert artifact.get("strategist_cache_preferred") is False
    assert artifact.get("strategist_cache_preference_reason") == ""
    assert artifact.get("runtime_cache_reuse_reason") == ""
    assert isinstance(artifact.get("commander_decision"), dict)
    observations = artifact.get("observations") if isinstance(artifact.get("observations"), dict) else {}
    assert observations.get("capital_available_for_sizing") == 7500000.0
    assert observations.get("cash_truth_source") == "kiwoom.kt00001"
    assert observations.get("cash_truth_available") is True
    assert observations.get("broker_orderable_amount") == 7500000.0
    assert observations.get("broker_withdrawable_cash") == 7600000.0
    assert observations.get("broker_deposit") == 8000000.0
    assert artifact.get("policy_source") == "strategist"
    assert artifact.get("policy_validation_status") == "ok"
    assert artifact.get("policy_fallback_used") is False
    assert artifact.get("policy_partial_normalized") is True
    assert artifact.get("policy_default_filled_fields") == ["enabled"]
    assert artifact.get("policy_validation_missing_fields") == ["enabled"]
    assert artifact.get("policy_validation_invalid_fields") == []
    assert artifact.get("applied_policy", {}).get("volume_ratio_min") == 0.68
    assert artifact.get("applied_policy_source_chain") == ["strategist", "validation", "commander_confirmed"]


def test_commander_artifact_surfaces_refresh_summary() -> None:
    state = {
        "run_id": "run-cmd-refresh",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "commander_decision": {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN_REFRESH",
            "market_regime": "risk_on",
            "session_bias": "active_selection",
            "risk_mode": "offensive",
            "allowed_playbooks": ["breakout", "pullback"],
            "banned_playbooks": ["defensive"],
            "scanner_mission": "Refresh strategist context before selecting liquid momentum leaders.",
            "monitor_mission": "Use the refreshed frame before evaluating continuation quality.",
            "llm_policy": "allow_context_refresh",
            "no_trade_reason_code": "NONE",
            "strategist_refresh_requested": True,
            "strategist_refresh_reason": "selected_symbol_outside_cached_frame",
            "strategist_refresh_context": {
                "selected_symbol": "034020",
                "selected_symbol_in_cached_frame": False,
                "cached_candidate_hints": ["005930", "000660"],
            },
            "source_priority": ["commander_refresh_heuristic", "shadow_commander"],
            "shadow_used": True,
            "strategist_fallback_used": False,
            "decision_summary": "Commander requested a fresh strategist frame before new entry planning.",
        },
        "commander_shadow_runtime": {
            "strategist_executed": True,
            "llm_called_by_strategist": True,
            "used_cached_strategist": False,
            "market_changed": True,
            "repeated_same_context": False,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
            "pre_buy_refresh_requested": True,
            "pre_buy_refresh_reason": "selected_symbol_outside_cached_frame",
            "pre_buy_refresh_context": {
                "selected_symbol": "034020",
                "selected_symbol_in_cached_frame": False,
            },
            "post_scanner_refresh_requested": True,
            "post_scanner_refresh_reason": "selected_symbol_outside_cached_frame",
            "post_scanner_refresh_context": {
                "selected_symbol": "034020",
                "selected_symbol_in_cached_frame": False,
            },
            "prior_context": {"selected_symbol": "005930", "playbook": "pullback", "market_regime": "neutral"},
        },
        "runtime_fast_path": {"reason": "commander_requested_refresh"},
        "portfolio_snapshot": {"positions": [], "cash": 1000},
        "portfolio_preflight": {"status": "ok", "blocked": False},
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "034020", "intent_side": "NOOP", "entry_exit_reason": "pullback_not_mature"},
        "selected": {"symbol": "034020", "score_total": 0.78},
    }

    artifact = build_commander_output_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain",
        status="ok",
        reason="commander_requested_refresh",
    )

    assert artifact.get("strategist_refresh_requested") is True
    assert artifact.get("strategist_refresh_reason") == "selected_symbol_outside_cached_frame"
    assert artifact.get("strategist_refresh_context", {}).get("selected_symbol") == "034020"
    assert artifact.get("runtime_refresh_requested") is True
    assert artifact.get("runtime_refresh_reason") == "selected_symbol_outside_cached_frame"
    assert artifact.get("runtime_refresh_context", {}).get("selected_symbol_in_cached_frame") is False
    assert artifact.get("post_scanner_refresh_requested") is True
    assert artifact.get("post_scanner_refresh_reason") == "selected_symbol_outside_cached_frame"
    assert artifact.get("post_scanner_refresh_context", {}).get("selected_symbol") == "034020"
    observations = artifact.get("observations") if isinstance(artifact.get("observations"), dict) else {}
    assert observations.get("post_scanner_refresh_requested") is True
    assert observations.get("post_scanner_refresh_reason") == "selected_symbol_outside_cached_frame"
    assert observations.get("post_scanner_refresh_selected_symbol") == "034020"


def test_commander_artifact_surfaces_cache_reuse_summary() -> None:
    state = {
        "run_id": "run-cmd-cache-reuse",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "commander_decision": {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "SKIP",
            "market_regime": "neutral",
            "session_bias": "active_selection",
            "risk_mode": "balanced",
            "allowed_playbooks": ["pullback", "defensive"],
            "banned_playbooks": ["reversal"],
            "scanner_mission": "Reuse the current strategist frame while the context is still valid.",
            "monitor_mission": "Evaluate continuation using the cached strategy frame.",
            "llm_policy": "prefer_cached_context",
            "no_trade_reason_code": "NONE",
            "strategist_cache_preferred": True,
            "strategist_cache_preference_reason": "commander_preferred_cached_strategist",
            "strategist_cache_preference_context": {
                "cache_age_sec": 50,
                "reuse_sec": 600,
                "cached_output_present": True,
            },
            "source_priority": ["commander_cache_reuse", "shadow_commander"],
            "shadow_used": True,
            "strategist_fallback_used": False,
            "decision_summary": "Commander preferred cached strategist context for this cycle.",
        },
        "commander_shadow_runtime": {
            "strategist_executed": False,
            "llm_called_by_strategist": False,
            "used_cached_strategist": True,
            "market_changed": False,
            "repeated_same_context": True,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
            "pre_buy_refresh_requested": False,
            "pre_buy_refresh_reason": "",
            "pre_buy_refresh_context": {},
            "prior_context": {"selected_symbol": "005930", "playbook": "pullback", "market_regime": "neutral"},
        },
        "runtime_fast_path": {
            "reason": "commander_skip_cached_strategist",
            "source": "commander_decision",
            "cache_age_sec": 50,
            "reuse_sec": 600,
        },
        "portfolio_snapshot": {"positions": [], "cash": 1000},
        "portfolio_preflight": {"status": "ok", "blocked": False},
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "entry_wait"},
        "selected": {"symbol": "005930", "score_total": 0.78},
    }

    artifact = build_commander_output_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain_cached_frame",
        status="ok",
        reason="commander_skip_cached_strategist",
    )

    assert artifact.get("selected_route") == "cached_strategist"
    assert artifact.get("strategist_cache_used") is True
    assert artifact.get("strategist_cache_preferred") is True
    assert artifact.get("strategist_cache_preference_reason") == "commander_preferred_cached_strategist"
    assert artifact.get("strategist_cache_preference_context", {}).get("cache_age_sec") == 50
    assert artifact.get("runtime_cache_reuse_reason") == "commander_skip_cached_strategist"
    assert artifact.get("runtime_cache_reuse_context", {}).get("source") == "commander_decision"


def test_commander_artifact_routes_blocked_with_cooldown() -> None:
    state = {
        "run_id": "run-cmd-2",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "cooldown_wait",
        "runtime_transition": "cooldown",
        "runtime_resilience_state": {"incident_count": 3, "cooldown_until_epoch": 1773000000},
        "portfolio_snapshot": {"positions": [], "cash": 1000},
        "portfolio_preflight": {"status": "ok", "blocked": False},
    }
    artifact = build_commander_output_artifact(
        state,
        mode="graph_spine",
        phase="session",
        path="session_strategist_blocked",
        status="blocked",
        reason="incident_threshold_cooldown",
    )
    assert artifact.get("selected_route") == "blocked"
    assert artifact.get("cooldown_applied") is True
    incident_state = artifact.get("incident_state") if isinstance(artifact.get("incident_state"), dict) else {}
    assert incident_state.get("incident_count") == 3
    assert artifact.get("strategist_blocked") is True


def test_commander_shadow_artifact_marks_position_already_open_without_override() -> None:
    state = {
        "run_id": "run-cmd-shadow-1",
        "started_at": "2026-03-18T10:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "runtime_fast_path": {"reason": "holding_position_monitor_only"},
        "portfolio_snapshot": {"positions": [{"symbol": "005930", "qty": 1}], "cash": 1000},
        "monitor": {"open_position_count": 1, "buy_blocked_open_position": True},
        "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "buy_blocked_open_position"},
        "selected": {"symbol": "005930", "score_total": 0.78},
        "commander_shadow_runtime": {
            "strategist_executed": False,
            "llm_called_by_strategist": False,
            "used_cached_strategist": False,
            "market_changed": False,
            "repeated_same_context": True,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
            "prior_context": {
                "selected_symbol": "005930",
                "selected_score_total": 0.79,
                "playbook": "pullback",
                "market_regime": "neutral",
                "market_sentiment": "mixed",
                "llm_status": "ok",
            },
        },
    }

    artifact = build_commander_shadow_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain_monitor_only",
        status="ok",
        reason="holding_position_monitor_only",
    )

    assert artifact.get("mode") == "shadow"
    assert artifact.get("shadow_only") is True
    assert artifact.get("decision") == "OBSERVE_ONLY"
    assert artifact.get("no_trade_reason_code") == "POSITION_ALREADY_OPEN"
    assert artifact.get("strategist_action_recommendation") == "SKIP"
    assert artifact.get("llm_call_advice") == "SKIP"
    assert artifact.get("next_action_recommendation") == "HOLD_OBSERVE"
    assert isinstance(artifact.get("monitor_gate_details"), dict)
    assert isinstance(artifact.get("context_delta_summary"), dict)
    assert isinstance(artifact.get("pre_strategist_shadow_snapshot"), dict)
    assert isinstance(artifact.get("post_strategist_assessment"), dict)
    assert isinstance(artifact.get("post_monitor_assessment"), dict)
    assert isinstance(artifact.get("end_of_cycle_summary"), dict)
    assert artifact["monitor_gate_details"]["entry_block_reason"] == "buy_blocked_open_position"
    assert artifact["context_delta_summary"]["symbol_same_as_last"] is True
    assert artifact["pre_strategist_shadow_snapshot"]["strategist_action_recommendation"] == "SKIP"
    assert artifact["post_monitor_assessment"]["monitor_decision"] == "WAIT"
    assert artifact["end_of_cycle_summary"]["next_action_recommendation"] == "HOLD_OBSERVE"
    assert artifact["integrated_into_commander_decision"] is True
    assert artifact["integration_version"] == "phase1_2"
    assert artifact["integration_role"] == "upstream_assessment"


def test_commander_shadow_artifact_includes_monitor_gate_details_for_wait_cycle() -> None:
    state = {
        "run_id": "run-cmd-shadow-2",
        "started_at": "2026-03-18T10:03:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "portfolio_snapshot": {"positions": [], "cash": 1000},
        "selected": {"symbol": "000660", "score_total": 0.91, "confidence": 0.62},
        "monitor": {"open_position_count": 0},
        "monitor_output": {"selected_symbol": "000660", "intent_side": "NOOP", "entry_exit_reason": "wait_for_confirmation"},
        "monitor_entry": {
            "reason": "wait_for_confirmation",
            "guard_reason": "breakout_not_ready",
            "failed_checks": ["breakout_ok", "volume_ok"],
            "passed_checks": ["extension_ok"],
            "primary_failure_axis": "breakout",
            "thresholds": {"volume_ratio_min": 0.8, "max_extended_from_vwap_pct": 0.05},
            "metrics": {
                "volume_ratio": 0.62,
                "extended_from_vwap_pct": 0.018,
                "pullback_depth_pct": 0.021,
                "recent_high": 125000,
                "breakout_level": 125500,
                "current_price": 124800,
                "timeframe_minutes": 3,
                "minute_source_present": True,
                "latest_candle_ts": 1773021780,
                "minute_snapshot_age_minutes": 7.5,
                "minute_snapshot_was_stale": True,
                "minute_refetch_attempted": True,
                "minute_refetch_succeeded": False,
                "minute_refetch_reason": "stale_snapshot_age_exceeded",
                "minute_refetch_produced_fresh_snapshot": False,
            },
        },
        "strategist_output": {
            "playbook": "pullback",
            "market_regime": "neutral",
            "market_sentiment": "mixed",
            "global_sentiment_score": 0.01,
            "macro_stress_overlay": {"stress_flags": ["vix_watch"]},
        },
        "strategist_llm": {"status": "repaired"},
        "commander_shadow_runtime": {
            "strategist_executed": True,
            "llm_called_by_strategist": True,
            "used_cached_strategist": False,
            "market_changed": False,
            "repeated_same_context": False,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
            "prior_context": {
                "selected_symbol": "000660",
                "selected_score_total": 0.88,
                "playbook": "pullback",
                "market_regime": "neutral",
                "market_sentiment": "mixed",
                "global_sentiment_score": 0.0,
                "vix_level": 21.0,
                "stress_flags": ["vix_watch"],
                "llm_status": "repaired",
            },
        },
    }

    artifact = build_commander_shadow_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain",
        status="ok",
        reason="cycle_complete",
    )

    assert artifact.get("shadow_only") is True
    assert artifact.get("no_trade_reason_code") == "NO_MARKET_CHANGE"
    gate = artifact["monitor_gate_details"]
    assert gate["breakout_passed"] is False
    assert gate["volume_passed"] is False
    assert gate["vwap_extension_passed"] is True
    assert gate["entry_block_reason"] == "breakout_not_ready"
    assert gate["observed_features"]["volume_ratio"] == 0.62
    assert gate["observed_features"]["minute_snapshot_age_minutes"] == 7.5
    assert gate["observed_features"]["minute_snapshot_was_stale"] is True
    assert gate["observed_features"]["minute_refetch_attempted"] is True
    assert gate["observed_features"]["minute_refetch_succeeded"] is False
    assert gate["observed_features"]["minute_refetch_reason"] == "stale_snapshot_age_exceeded"
    assert gate["observed_features"]["minute_refetch_produced_fresh_snapshot"] is False
    assert gate["used_thresholds"]["volume_ratio_min"] == 0.8
    assert artifact["context_delta_summary"]["playbook_same_as_last"] is True
    assert artifact["actual_runtime"]["strategist_executed"] is True


def test_commander_shadow_actual_runtime_marks_cached_strategist_usage() -> None:
    state = {
        "run_id": "run-cmd-shadow-cache-1",
        "started_at": "2026-03-25T03:00:00+00:00",
        "runtime_phase": "session",
        "runtime_status": "ok",
        "monitor_output": {"selected_symbol": "000660", "intent_side": "NOOP", "entry_exit_reason": "wait_for_confirmation"},
        "commander_shadow_runtime": {
            "strategist_executed": False,
            "strategist_called": False,
            "llm_called_by_strategist": False,
            "used_cached_strategist": False,
            "monitor_decision": "NOOP",
            "executor_action": "",
            "executor_status": "",
        },
    }

    artifact = build_commander_shadow_artifact(
        state,
        mode="integrated_chain",
        phase="session",
        path="integrated_chain_cached_frame",
        status="ok",
        reason="commander_skip_cached_strategist",
    )

    actual_runtime = artifact.get("actual_runtime") if isinstance(artifact.get("actual_runtime"), dict) else {}
    assert actual_runtime.get("strategist_executed") is False
    assert actual_runtime.get("strategist_called") is False
    assert actual_runtime.get("llm_called_by_strategist") is False
    assert actual_runtime.get("used_cached_strategist") is True
