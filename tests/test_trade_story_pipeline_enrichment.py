from libs.reporting.trade_story_pipeline import (
    build_trade_story_input,
    build_lifecycle_bundle,
    build_market_context_human,
    build_monitor_reason_human,
    build_scanner_reason_human,
    enrich_filters_from_evidence,
    enrich_scanner_reason_from_evidence,
)


def test_market_context_human_prefers_strategist_input_summary_when_runtime_fields_missing() -> None:
    out = build_market_context_human(
        {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "breakout",
            "themes": ["broad_market_leaders", "defensive_large_cap"],
            "macro_stress_overlay": {"stress_flags": ["elevated_vix", "yield_rise"], "active": True},
            "input_summary": {
                "global_sentiment_score": -0.2235,
                "vix_level": 25.09,
                "vix_change_pct": 12.16,
                "vix_level_pressure": 0.255,
                "headline_count": 75,
                "candidate_signal_total": 5,
                "market_signal_total": 10,
                "news_query_targets": ["코스피", "미국 증시", "국제유가", "환율"],
                "key_events_hint": [
                    "global_sentiment score=-0.224 status=ok source=yfinance",
                    "fear_index vix=25.09 change=12.16% pressure=0.255",
                ],
            },
        }
    )

    assert out["global_sentiment_score"] == -0.2235
    assert out["vix_level"] == 25.09
    assert out["headline_count"] == 75
    assert out["news_query_count"] == 4
    assert out["market_signal_total"] == 10
    assert out["candidate_signal_total"] == 5
    assert out["news_query_targets"] == ["코스피", "미국 증시", "국제유가", "환율"]
    assert "75 headlines were considered across 4 targets" in out["news_input_summary"]
    assert any("News query targets: 코스피, 미국 증시, 국제유가, 환율" in row for row in out["bullets"])


def test_scanner_reason_human_surfaces_top_candidates_and_runner_up_deltas() -> None:
    out = build_scanner_reason_human(
        {
            "universe_size": 5,
            "selected_symbol": "000660",
            "ranking_table": [
                {"rank": 1, "symbol": "000660", "score_total": 1.1776, "risk_score": 0.6281, "confidence": 0.8099},
                {"rank": 2, "symbol": "005930", "score_total": 1.1519, "risk_score": 0.7310, "confidence": 0.7851},
                {"rank": 3, "symbol": "047040", "score_total": 1.1408, "risk_score": 0.9130, "confidence": 0.7638},
            ],
            "selected_candidate": {
                "symbol": "000660",
                "sources": ["top_value", "sector_theme"],
                "score_total": 1.1776,
                "risk_score": 0.6281,
                "confidence": 0.8099,
                "score_breakdown": {"trading_value": 0.22, "theme_boost": 0.0624},
                "feature_snapshot": {"engine_ma20_gap": 0.05, "engine_adx14": 13.17, "engine_trend_strength": 0.13},
            },
            "candidate_preview": [
                {"symbol": "005930", "why": "weaker sector fit"},
                {"symbol": "047040", "why": "higher volatility and lower confidence"},
            ],
        },
        {"playbook": "breakout"},
    )

    assert out["selected_symbol"] == "000660"
    assert out["selected_rank"] == 1
    assert out["selected_score"] == 1.1776
    assert len(out["top_candidates"]) == 3
    assert out["runner_ups"][0]["symbol"] == "005930"
    assert "score gap" in out["runner_ups"][0]["why"]
    assert any("Top candidates:" in row for row in out["bullets"])
    assert any("Why not others:" in row for row in out["bullets"])


def test_monitor_reason_human_keeps_normalized_exit_context_details() -> None:
    out = build_monitor_reason_human(
        {
            "trigger_type": "hard_stop",
            "monitor_reason": "confirmed_exit_signal",
            "thresholds_guards_used": {
                "thresholds": {
                    "stop_loss_pct": 0.08,
                    "effective_stop_loss_pct": 0.01,
                    "effective_stop_reason": "hard_stop",
                    "take_profit_pct": 0.0084,
                    "peak_drawdown_exit_pct": 0.0052,
                },
                "exit_confirm_ticks": 3,
                "exit_confirm_count": 2,
            },
            "exit_triggered": True,
            "current_price": 29300.0,
            "average_price": 29650.0,
            "peak_price": 29650.0,
            "current_drawdown": -0.0118,
            "active_exit_axis": "Hard Stop",
            "watch_axes": ["Hard stop", "Take profit", "Trailing stop"],
            "price_source": "position.current_price",
            "feature_source": "selected.features",
            "decision_reason_chain": ["hold", "hard_stop", "confirmed_exit_signal"],
        },
        {"action": "SELL"},
    )

    assert out["posture"] == "SELL"
    assert out["trigger_type"] == "hard_stop"
    assert out["active_exit_axis"] == "Hard Stop"
    assert out["effective_stop_loss_pct"] == 0.01
    assert out["confirm_required"] == 3
    assert out["confirm_count"] == 2
    assert out["watch_axes"][:3] == ["Hard stop", "Take profit", "Trailing stop"]


def test_monitor_reason_human_surfaces_intraday_entry_metrics() -> None:
    out = build_monitor_reason_human(
        {
            "entry_evaluated": True,
            "entry_triggered": True,
            "entry_reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
            "entry_pattern": "breakout_vwap_hold",
            "entry_signal_chain": ["recent_high_breakout", "vwap_hold", "volume_confirmation", "not_extended"],
            "entry_metrics": {
                "timeframe_minutes": 1,
                "recent_high": 101.4,
                "breakout_level": 101.4,
                "vwap": 101.2,
                "volume_ratio": 2.31,
                "extended_from_vwap_pct": 0.0059,
                "pullback_depth_pct": 0.0041,
            },
            "entry_thresholds": {
                "volume_ratio_min": 1.15,
                "max_extended_from_vwap_pct": 0.006,
                "pullback_max_pct": 0.008,
            },
            "monitor_reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
        },
        {"action": "BUY"},
    )

    assert out["posture"] == "BUY"
    assert out["entry_triggered"] is True
    assert out["entry_pattern"] == "breakout_vwap_hold"
    assert any("Entry timeframe: 1m" in row for row in out["bullets"])
    assert any("Volume ratio: 2.31" in row for row in out["bullets"])
    assert any("Extended from VWAP:" in row for row in out["bullets"])
    assert "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation" in out["summary"]


def test_monitor_reason_human_prefers_decision_trace_and_surfaces_threshold_gaps() -> None:
    out = build_monitor_reason_human(
        {
            "entry_evaluated": True,
            "entry_triggered": False,
            "entry_reason": "stale_top_level_reason",
            "monitor_reason": "reclaim_not_confirmed",
            "entry_metrics": {
                "volume_ratio": 0.10,
                "extended_from_vwap_pct": 0.19,
                "pullback_depth_pct": 0.00,
            },
            "entry_thresholds": {
                "volume_ratio_min": 0.75,
                "max_extended_from_vwap_pct": 0.05,
                "pullback_min_pct": 0.012,
                "pullback_max_pct": 0.07,
            },
            "decision_trace": {
                "entry_check_summary": "mission=wait_for_confirmation | reason=reclaim_not_confirmed",
                "entry_blockers": ["volume_ok", "vwap_reclaim_ok"],
                "policy_ref": {
                    "monitor_mission": "Wait for cleaner reclaim confirmation.",
                    "flow_instruction": "observe_only",
                },
                "timing_assessment": {
                    "entry_reason": "reclaim_not_confirmed",
                    "entry_pattern": "pullback_reclaim",
                },
                "thresholds_guards_used": {
                    "thresholds": {
                        "volume_ratio_min": 0.75,
                        "max_extended_from_vwap_pct": 0.05,
                        "pullback_min_pct": 0.012,
                    }
                },
            },
        },
        {"action": "NOOP"},
    )

    assert "mission=wait_for_confirmation" in out["summary"]
    assert "volume ratio 0.10 below min 0.75" in out["summary"]
    assert out["entry_reason"] == "reclaim_not_confirmed"
    assert out["entry_pattern"] == "pullback_reclaim"
    assert out["entry_check_summary"] == "mission=wait_for_confirmation | reason=reclaim_not_confirmed"
    assert out["entry_blockers"] == ["volume_ok", "vwap_reclaim_ok"]
    assert out["policy_ref"]["flow_instruction"] == "observe_only"
    assert any("Entry blockers:" in row for row in out["bullets"])
    assert any("Threshold gaps:" in row for row in out["bullets"])


def test_monitor_reason_human_uses_applied_policy_when_entry_thresholds_missing() -> None:
    out = build_monitor_reason_human(
        {
            "entry_evaluated": True,
            "entry_triggered": False,
            "monitor_reason": "pullback_not_mature",
            "entry_metrics": {
                "timeframe_minutes": 1,
                "volume_ratio": 0.61,
                "extended_from_vwap_pct": 0.03,
                "pullback_depth_pct": 0.004,
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
        },
        {"action": "NOOP"},
    )

    assert "volume ratio 0.61 below min 0.68" in out["summary"]
    assert "pullback depth 0.40% below min 0.80%" in out["summary"]
    assert any("Entry timeframe: 1m" in row for row in out["bullets"])


def test_enrich_scanner_reason_from_evidence_promotes_selection_reason_details() -> None:
    out = enrich_scanner_reason_from_evidence(
        {
            "summary": "Scanner selected 000660 as rank #1.",
            "bullets": ["Universe scanned: 5"],
        },
        {
            "candidate_selection_reasons": [
                {
                    "payload": {
                        "why_selected": [
                            "highest total score (1.178)",
                            "confidence 0.81 and risk 0.63",
                        ],
                        "runner_ups_lost": [
                            {
                                "symbol": "005930",
                                "why_lost": [
                                    "lower total score (1.152 vs 1.178)",
                                    "higher risk (0.73 vs 0.63)",
                                ],
                            }
                        ],
                        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
                        "final_decision_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting.",
                    }
                }
            ]
        },
    )

    assert out["selection_basis"] == "Scanner selected the highest-ranked candidate after strategist-guided weighting."
    assert out["tie_break_rule"] == "score_total desc -> confidence desc -> risk_score asc"
    assert out["why_selected"][0] == "highest total score (1.178)"
    assert out["runner_ups_lost"][0]["symbol"] == "005930"
    assert any("Selection decision:" in row for row in out["bullets"])


def test_enrich_scanner_reason_from_evidence_normalizes_chart_coverage_from_ranking_table() -> None:
    out = enrich_scanner_reason_from_evidence(
        {
            "selected_symbol": "005930",
            "top_reasons": ["highest combined scanner score (1.173)", "chart feature coverage 6/12"],
            "bullets": ["Chart / feature coverage: 6/12"],
        },
        {
            "candidate_ranking_tables": [
                {
                    "payload": {
                        "rows": [
                            {
                                "symbol": "005930",
                                "compact_feature_snapshot": {
                                    "engine_ma20_gap": 0.03,
                                    "engine_adx14": 14.4,
                                    "engine_trend_strength": 0.14,
                                    "engine_volume_spike20": 0.59,
                                    "engine_volatility20": 0.05,
                                    "engine_vwap_distance": 0.21,
                                    "engine_sector_relative_strength": 0.0,
                                    "engine_cross_section_rank": 0.75,
                                    "engine_regime": "high_volatility",
                                    "engine_signal_score": 0.0,
                                },
                            }
                        ]
                    }
                }
            ]
        },
    )

    assert out["feature_coverage"]["present"] == 10
    assert out["top_reasons"][1] == "chart feature coverage 10/12"
    assert any("Chart / feature coverage: 10/12" == row for row in out["bullets"])


def test_build_trade_story_input_normalizes_filter_coverage_from_scanner_evidence() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-03-20",
            "run_id": "run-1",
            "scanner_reason_human": {
                "selected_symbol": "005930",
                "bullets": ["Chart / feature coverage: 6/12"],
            },
            "filters_human": {
                "summary": "Scanner and guard checks passed 6 of 8 visible gates. Chart completeness was partial with 6/12 captured features.",
                "bullets": ["chart completeness filter: PARTIAL - 6/12 captured chart features"],
            },
            "scanner_evidence": {
                "candidate_ranking_tables": [
                    {
                        "payload": {
                            "rows": [
                                {
                                    "symbol": "005930",
                                    "compact_feature_snapshot": {
                                        "engine_ma20_gap": 0.03,
                                        "engine_adx14": 14.4,
                                        "engine_trend_strength": 0.14,
                                        "engine_volume_spike20": 0.59,
                                        "engine_volatility20": 0.05,
                                        "engine_vwap_distance": 0.21,
                                        "engine_sector_relative_strength": 0.0,
                                        "engine_cross_section_rank": 0.75,
                                        "engine_regime": "high_volatility",
                                        "engine_signal_score": 0.0,
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            "trade_lifecycle": {
                "trade_id": "TRD_20260320_005930_01",
                "symbol": "005930",
                "status": "open",
                "entry": {
                    "run_id": "run-1",
                    "action": "BUY",
                    "scanner_context": {"selected_symbol": "005930"},
                },
                "holding": {},
                "exit": {},
                "summary": {},
                "reporter": {},
            },
        }
    )

    assert "10/12 captured features" in out["filters_human"]["summary"]
    assert any("chart completeness filter: PASS - 10/12 captured chart features" == row for row in out["filters_human"]["bullets"])
    assert any(
        row.get("name") == "chart completeness filter" and row.get("status") == "PASS" and row.get("detail") == "10/12 captured chart features"
        for row in out["filters_human"]["checks"]
    )


def test_trade_story_input_and_lifecycle_bundle_include_reasoning_trace_chain() -> None:
    bundle_out = {
        "day": "2026-03-24",
        "run_id": "run-trace-1",
        "trade_id": "TRD_TEST_1",
        "story_id": "TRD_TEST_1",
        "market_context_human": {"summary": "Commander saw a defensive regime."},
        "scanner_reason_human": {"summary": "Scanner preferred 003280 over 000660."},
        "monitor_reason_human": {"summary": "Monitor waited for confirmation."},
        "operator_conclusion_human": {"summary": "No new action yet."},
        "execution_outcome_human": {"summary": "Execution was not attempted."},
        "guard_reason_human": {"summary": "No guard escalation."},
        "reporter_status_human": {"summary": "Reporter ready."},
        "warnings": [],
        "timeline": [],
        "strategist_summary": {
            "selected_playbook": "defensive",
            "strategy_summary": "Strategist kept a defensive playbook.",
            "strategist_fallback_used": False,
        },
        "scanner_summary": {
            "selected_symbol": "003280",
            "runner_up_symbol": "000660",
            "selection_summary": "003280 ranked first with better liquidity.",
        },
        "monitor_summary": {
            "decision": "WAIT",
            "entry_check_summary": "VWAP reclaim confirmation is still pending.",
        },
        "commander_summary": {
            "command_intent": "OBSERVE_ONLY",
            "decision_summary": "Commander kept the session in observe-only mode.",
            "shadow_used": True,
            "strategist_fallback_used": False,
        },
        "canonical_agent_artifacts": {
            "canonical_commander_json": "/tmp/commander.json",
            "canonical_strategist_json": "/tmp/strategist.json",
            "canonical_scanner_json": "/tmp/scanner.json",
            "canonical_monitor_json": "/tmp/monitor.json",
        },
        "evidence_provenance": {
            "commander": "canonical",
            "strategist": "canonical",
            "scanner": "canonical",
            "monitor": "canonical",
        },
    }

    story_input = build_trade_story_input(bundle_out)

    assert story_input["reasoning_trace"]["commander_summary"]["summary"] == "Commander kept the session in observe-only mode."
    assert story_input["reasoning_trace"]["strategist_summary"]["summary"] == "Strategist kept a defensive playbook."
    assert story_input["reasoning_trace"]["scanner_summary"]["summary"] == "003280 ranked first with better liquidity."
    assert story_input["reasoning_trace"]["monitor_summary"]["summary"] == "VWAP reclaim confirmation is still pending."
    assert story_input["reasoning_provenance"]["shadow_used"] is True
    assert story_input["reasoning_provenance"]["commander_source_ref"] == "/tmp/commander.json"

    lifecycle_bundle = build_lifecycle_bundle(
        day="2026-03-24",
        trade_id="TRD_TEST_1",
        run_id="run-trace-1",
        symbol="003280",
        lifecycle={"entry": {}, "holding": {}, "exit": {}, "summary": {}},
        strategist_summary=bundle_out["strategist_summary"],
        scanner_summary=bundle_out["scanner_summary"],
        monitor_summary=bundle_out["monitor_summary"],
        commander_summary=bundle_out["commander_summary"],
        story_input=story_input,
        diagnostics={},
        canonical_refs=bundle_out["canonical_agent_artifacts"],
        llm_refs={},
        artifact_links={},
    )

    assert lifecycle_bundle["reasoning_trace"]["scanner_summary"]["selected_symbol"] == "003280"
    assert lifecycle_bundle["reasoning_provenance"]["strategist_plan_source"] == "canonical"


def test_trade_story_input_prefers_latest_reasoning_trace_snapshot_when_present() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-03-24",
            "run_id": "run-trace-2",
            "trade_id": "TRD_TEST_2",
            "latest_reasoning_trace": {
                "commander_summary": {"summary": "snapshot commander"},
                "strategist_summary": {"summary": "snapshot strategist"},
                "scanner_summary": {"summary": "snapshot scanner", "selected_symbol": "005930"},
                "monitor_summary": {"summary": "snapshot monitor"},
            },
            "latest_reasoning_trace_provenance": {
                "commander_context_source": "state.commander_decision",
                "strategist_plan_source": "state.strategy_policy.strategist_plan",
                "scanner_reason_source": "state.scanner_output",
                "monitor_reason_source": "state.monitor_output",
                "shadow_used": True,
                "strategist_fallback_used": False,
            },
            "market_context_human": {"summary": "derived market"},
            "scanner_reason_human": {"summary": "derived scanner"},
            "monitor_reason_human": {"summary": "derived monitor"},
            "operator_conclusion_human": {"summary": "derived conclusion"},
            "execution_outcome_human": {"summary": "Execution was not attempted."},
            "guard_reason_human": {"summary": "No guard escalation."},
            "reporter_status_human": {"summary": "Reporter ready."},
        }
    )

    assert out["reasoning_trace"]["commander_summary"]["summary"] == "snapshot commander"
    assert out["reasoning_trace"]["scanner_summary"]["selected_symbol"] == "005930"
    assert out["reasoning_provenance"]["commander_context_source"] == "state.commander_decision"
    assert out["reasoning_provenance"]["shadow_used"] is True


def test_trade_story_input_prefers_latest_reasoning_provenance_over_stale_legacy_copy() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-03-24",
            "run_id": "run-trace-2b",
            "trade_id": "TRD_TEST_2B",
            "reasoning_provenance": {
                "commander_context_source": "canonical",
                "strategist_plan_source": "canonical",
                "scanner_reason_source": "canonical",
                "monitor_reason_source": "canonical",
                "shadow_used": False,
                "strategist_fallback_used": False,
                "source_priority": [],
            },
            "latest_reasoning_trace_provenance": {
                "commander_context_source": "state.commander_decision",
                "strategist_plan_source": "state.strategy_policy.strategist_plan",
                "scanner_reason_source": "state.scanner_output",
                "monitor_reason_source": "state.monitor_output",
                "commander_source_ref": "commander_router.shadow_assessment",
                "shadow_used": True,
                "strategist_fallback_used": False,
                "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            },
            "market_context_human": {"summary": "derived market"},
            "scanner_reason_human": {"summary": "derived scanner"},
            "monitor_reason_human": {"summary": "derived monitor"},
            "operator_conclusion_human": {"summary": "derived conclusion"},
            "execution_outcome_human": {"summary": "Execution was not attempted."},
            "guard_reason_human": {"summary": "No guard escalation."},
            "reporter_status_human": {"summary": "Reporter ready."},
        }
    )

    assert out["reasoning_provenance"]["commander_context_source"] == "state.commander_decision"
    assert out["reasoning_provenance"]["commander_source_ref"] == "commander_router.shadow_assessment"
    assert out["reasoning_provenance"]["shadow_used"] is True
    assert out["reasoning_provenance"]["source_priority"] == [
        "shadow_commander",
        "runtime_observation",
        "strategist_fallback",
    ]


def test_trade_story_input_falls_back_to_market_context_artifact_for_commander_source_ref() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-03-24",
            "run_id": "run-trace-3",
            "trade_id": "TRD_TEST_3",
            "market_context_human": {"summary": "Commander regime summary"},
            "scanner_reason_human": {"summary": "Scanner summary"},
            "monitor_reason_human": {"summary": "Monitor summary"},
            "operator_conclusion_human": {"summary": "Conclusion summary"},
            "execution_outcome_human": {"summary": "Execution was not attempted."},
            "guard_reason_human": {"summary": "No guard escalation."},
            "reporter_status_human": {"summary": "Reporter ready."},
            "canonical_agent_artifacts": {},
            "artifacts": {"agent_pipeline_trace_json": "/tmp/agent_pipeline_trace.json"},
            "evidence_provenance": {"commander": "canonical"},
        }
    )

    assert out["reasoning_provenance"]["commander_context_source"] == "canonical"
    assert out["reasoning_provenance"]["commander_source_ref"] == "/tmp/agent_pipeline_trace.json"


def test_trade_story_input_uses_commander_bundle_fallback_for_shadow_flags() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-03-24",
            "run_id": "run-trace-4",
            "trade_id": "TRD_TEST_4",
            "execution": {"symbol": "003280", "action": "BUY"},
            "reasoning_provenance": {
                "commander_context_source": "canonical",
                "strategist_plan_source": "canonical",
                "scanner_reason_source": "canonical",
                "monitor_reason_source": "canonical",
                "shadow_used": False,
                "strategist_fallback_used": False,
                "source_priority": [],
            },
            "commander": {
                "shadow_used": True,
                "strategist_fallback_used": False,
                "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            },
            "strategist_summary": {"summary": "Strategist summary."},
            "scanner_summary": {"summary": "Scanner summary."},
            "monitor_summary": {"summary": "Monitor summary."},
            "market_context_human": {"summary": "Market context"},
            "scanner_reason_human": {"summary": "Scanner reason"},
            "monitor_reason_human": {"summary": "Monitor reason"},
            "operator_conclusion_human": {"summary": "Operator conclusion"},
            "execution_outcome_human": {"summary": "Execution was not attempted."},
            "guard_reason_human": {"summary": "No guard escalation."},
            "reporter_status_human": {"summary": "Reporter ready."},
            "canonical_agent_artifacts": {},
            "evidence_provenance": {"commander": "canonical"},
            "artifacts": {"agent_pipeline_trace_json": "/tmp/agent_pipeline_trace.json"},
        }
    )

    assert out["reasoning_provenance"]["shadow_used"] is True
    assert out["reasoning_provenance"]["strategist_fallback_used"] is False
    assert out["reasoning_provenance"]["source_priority"] == [
        "shadow_commander",
        "runtime_observation",
        "strategist_fallback",
    ]
