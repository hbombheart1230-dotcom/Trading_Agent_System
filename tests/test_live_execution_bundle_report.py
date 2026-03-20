from __future__ import annotations

import json
from pathlib import Path

import libs.reporting.trade_story_pipeline as story_pipeline
import scripts.run_live_execution_bundle_report as mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fake_trace(event_log_path, evidence_log_path, report_dir, *, run_id=None, day=None, reports_root=None, max_news_titles=5):  # type: ignore[no-untyped-def]
    report_dir.mkdir(parents=True, exist_ok=True)
    rid = str(run_id or "run")
    js_path = report_dir / f"agent_pipeline_trace_{rid}.json"
    md_path = report_dir / f"agent_pipeline_trace_{rid}.md"
    out = {
        "run_id": rid,
        "day": day,
        "commander": {"route_ts": f"{day}T00:00:00+00:00"},
        "strategist": {
            "playbook": "pullback",
            "themes": ["semiconductor"],
            "global_sentiment_score": -0.12,
            "fear_index": {"level": 25.4},
            "global_macro_moves": {"dxy_pct": 0.4},
            "llm_parsed_output": {"market_regime": "neutral", "market_sentiment": "neutral"},
            "news_query_reasoning": "defensive context",
            "market_news_total_headlines": 12,
            "market_news_query_count": 4,
            "macro_stress_overlay": {"stress_flags": ["elevated_vix"], "active": False},
        },
        "scanner": {
            "top_stock": "000660" if rid in {"run-1", "run-2"} else "005930",
            "top_score": 1.23,
            "candidate_pool_after_filter": 5,
            "top_ranked_symbols": ["000660", "005930", "035420"] if rid in {"run-1", "run-2"} else ["005930", "000660", "035420"],
            "selected_candidate": {
                "symbol": "000660" if rid in {"run-1", "run-2"} else "005930",
                "why": "top_value+sector_theme",
                "sources": ["top_value", "top_volume", "sector_theme"],
                "score_total": 1.23,
                "confidence": 0.91,
                "risk_score": 0.2,
                "score_breakdown": {"trading_value": 0.3, "theme_boost": 0.1, "sentiment": 0.04},
                "component_snapshot": {"trading_value_component": 1.0, "sentiment_component": 0.2},
                "feature_snapshot": {"engine_signal_score": 0.8, "engine_ma20_gap": 0.1, "engine_regime": "trend"},
            },
            "candidate_preview": [
                {"symbol": "000660", "why": "best combined score"},
                {"symbol": "005930", "why": "weaker theme fit"},
                {"symbol": "035420", "why": "lower liquidity"},
            ],
            "condition_search_status": "disabled",
            "condition_search_reason": "condition_search_baseline_disabled",
        },
        "monitor": {
            "selected_symbol": "000660" if rid in {"run-1", "run-2"} else "005930",
            "entry_reason": "no_position",
            "exit_reason": "stop_loss" if rid == "run-2" else "no_position",
            "monitor_reason": "confirmed_exit_signal" if rid == "run-2" else "entry_ready",
            "thresholds": {
                "stop_loss_pct": 0.08,
                "effective_stop_loss_pct": 0.03,
                "effective_stop_reason": "adaptive_stop",
                "take_profit_pct": 0.02,
            },
            "position_age_seconds": 120,
            "exit_triggered": rid == "run-2",
            "price": 70500.0,
            "avg_price": 70000.0,
            "peak_price": 71600.0,
            "peak_drawdown": -0.0154,
            "current_drawdown": -0.0154,
            "vwap_distance": -0.006,
            "price_source": "market.quote.price",
            "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized",
            "feature_source": "selected.features",
        },
        "supervisor": {"verdict": "approve", "supervisor_allow": True, "supervisor_reason": "risk checks passed"},
        "executor": {"execution_ok": True, "execution_attempted": True, "broker_env": "mock", "effective_mode": "mock_broker_http"},
        "reporter": {
            "reporter_analysis_day_file_found": True,
            "reporter_analysis_found": rid == "run-1",
            "reporter_analysis_path": str((Path(str(reports_root)) / "reporter_analysis" / f"reporter_analysis_{day}.json") if reports_root else ""),
        },
    }
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(f"# trace {rid}\n", encoding="utf-8")
    return md_path, js_path, out


def _fake_trade(event_log_path, report_dir, *, day=None, max_executions=120, max_sell_pairs=120):  # type: ignore[no-untyped-def]
    report_dir.mkdir(parents=True, exist_ok=True)
    js_path = report_dir / f"trade_explain_{day}.json"
    md_path = report_dir / f"trade_explain_{day}.md"
    out = {"day": day, "execution_summary": {"executions_total": 2}}
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(f"# trade {day}\n", encoding="utf-8")
    return md_path, js_path, out


def _fake_reporter(event_log_path, report_dir, *, day=None, intents_path=None, reports_root=None, **kwargs):  # type: ignore[no-untyped-def]
    report_dir.mkdir(parents=True, exist_ok=True)
    js_path = report_dir / f"reporter_analysis_{day}.json"
    md_path = report_dir / f"reporter_analysis_{day}.md"
    out = {"day": day, "ai_summary": "same-day reporter summary", "ai_run_grade": "B"}
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(f"# reporter {day}\n", encoding="utf-8")
    root = Path(str(reports_root)) if reports_root else report_dir.parent.parent
    operator_dir = root / "operator_summary"
    operator_dir.mkdir(parents=True, exist_ok=True)
    (operator_dir / f"operator_summary_{day}.json").write_text("{}", encoding="utf-8")
    (operator_dir / f"operator_summary_{day}.md").write_text("# operator\n", encoding="utf-8")
    return md_path, js_path, out


def _fake_ai_trade_report_ok(story_input: dict, **kwargs):  # type: ignore[no-untyped-def]
    symbol = str(story_input.get("symbol") or "000000")
    action = str(story_input.get("action") or "HOLD")
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    return {
        "schema_version": "trade_report.v2",
        "trade_id": str(story_input.get("trade_id") or story_input.get("story_id") or ""),
        "story_id": str(story_input.get("story_id") or ""),
        "run_id": str(story_input.get("run_id") or ""),
        "symbol": symbol,
        "action": action,
        "status": str(story_input.get("status") or "closed"),
        "story_type": str(story_input.get("story_type") or "simulation"),
        "execution_mode_label": str(story_input.get("execution_mode_label") or "simulation"),
        "generation": {"status": "ok", "mode": "ai", "model": "openrouter/free", "reason": ""},
        "executive_summary": {"headline": f"{action} {symbol}", "summary": "AI report generated.", "action": action, "symbol": symbol, "confidence": "high"},
        "market_context_at_entry": {"summary": "Sentiment context captured.", "bullets": ["sentiment: neutral"]},
        "why_this_symbol_was_chosen": {"summary": "Top rank selected.", "bullets": ["rank #1"]},
        "entry_decision": {"summary": "Entry rationale captured.", "bullets": []},
        "holding_monitoring_story": {
            "summary": "Holding path captured.",
            "bullets": list((monitor_reason.get("bullets") or [])),
        },
        "monitor_snapshot": {
            "posture": str(monitor_reason.get("posture") or action),
            "trigger_type": str(monitor_reason.get("trigger_type") or ""),
            "current_price": monitor_reason.get("current_price"),
            "average_price": monitor_reason.get("average_price"),
            "peak_price": monitor_reason.get("peak_price"),
            "current_drawdown": monitor_reason.get("current_drawdown"),
            "peak_drawdown": monitor_reason.get("peak_drawdown"),
            "vwap_distance": monitor_reason.get("vwap_distance"),
            "active_exit_axis": str(monitor_reason.get("active_exit_axis") or ""),
            "watch_axes": list(monitor_reason.get("watch_axes") or []),
            "price_source": str(monitor_reason.get("price_source") or ""),
            "price_source_policy": str(monitor_reason.get("price_source_policy") or ""),
            "feature_source": str(monitor_reason.get("feature_source") or ""),
            "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct"),
            "effective_stop_reason": str(monitor_reason.get("effective_stop_reason") or ""),
            "take_profit_pct": monitor_reason.get("take_profit_pct"),
            "exit_triggered": bool(monitor_reason.get("exit_triggered")),
        },
        "exit_decision": {"summary": "Exit rationale captured.", "bullets": []},
        "execution_quality": {"summary": "Execution quality captured.", "bullets": []},
        "scanner_filters": {"summary": "Filters captured.", "bullets": []},
        "guard_approval_result": {"summary": "Guard approval captured.", "bullets": []},
        "reporter_evaluation": {"summary": "Reporter linkage captured.", "status": "linked", "grade": "A", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "No major issues.", "bullets": []},
        "full_timeline": [{"event": "entry", "ts": "2026-03-16T00:00:00+00:00", "description": "entry"}],
        "timeline": [{"event": "entry", "ts": "2026-03-16T00:00:00+00:00", "description": "entry"}],
        "final_operator_conclusion": {"summary": "Hold and monitor.", "current_action": action, "watch_next": ["volatility"], "thesis_invalidation": ["stop breach"]},
        "llm_response_artifact": {
            "schema_version": "llm_response_artifact.v1",
            "component": "ai_trade_report",
            "run_id": str(story_input.get("run_id") or ""),
            "trade_id": str(story_input.get("trade_id") or story_input.get("story_id") or ""),
            "story_id": str(story_input.get("story_id") or ""),
            "day": str(story_input.get("day") or ""),
            "status": "ok",
            "latency_ms": 120,
            "parsed_output": {"summary": "AI report generated."},
            "model_info": {"provider": "OpenRouter", "model": "openrouter/free"},
            "attempts": [
                {
                    "step": "primary",
                    "system_prompt": "system",
                    "user_prompt": "user",
                    "raw_response_text": "{\"executive_summary\":{\"summary\":\"AI report generated.\"}}",
                    "parsed_output": {"executive_summary": {"summary": "AI report generated."}},
                    "model_info": {"provider": "OpenRouter", "model": "openrouter/free"},
                    "latency_ms": 120,
                    "status": "ok",
                }
            ],
        },
    }


def test_flatten_news_titles_handles_count_sample_mapping_with_string_rows() -> None:
    sample = {
        "코스피": {
            "count": 5,
            "sample": [
                "NewsItem(title='코스피 약세 지속', url='https://example.com/1')",
                "NewsItem(title='외인 &amp; 기관 매도 확대', url='https://example.com/2')",
            ],
        },
        "000660": {
            "count": 3,
            "sample": [
                "NewsItem(title='SK하이닉스 변동성 확대', url='https://example.com/3')",
            ],
        },
    }

    titles = mod._flatten_news_titles(sample, max_groups=2, max_titles_per_group=2)

    assert titles == [
        "코스피: 코스피 약세 지속",
        "코스피: 외인 & 기관 매도 확대",
        "000660: SK하이닉스 변동성 확대",
    ]


def test_build_strategist_input_summary_surfaces_news_titles_from_sample_mapping() -> None:
    source_input = {
        "news_query_targets": ["코스피", "미국 증시"],
        "market_news_sample": {
            "코스피": {
                "count": 5,
                "sample": [
                    "NewsItem(title='코스피 약세 지속', url='https://example.com/1')",
                ],
            }
        },
        "candidate_news_sample": {
            "000660": {
                "count": 3,
                "sample": [
                    "NewsItem(title='SK하이닉스 변동성 확대', url='https://example.com/2')",
                ],
            }
        },
        "global_sentiment_signal": {
            "score": -0.22,
            "fear_index": {"level": 25.09, "change_pct": 12.16, "level_pressure": 0.255},
        },
        "news_context": {"headline_count": 75, "candidate_signal_total": 5, "market_signal_total": 10},
    }

    summary = mod._build_strategist_input_summary(source_input, {})

    assert summary["market_news_titles"] == ["코스피: 코스피 약세 지속"]
    assert summary["candidate_news_titles"] == ["000660: SK하이닉스 변동성 확대"]



def test_build_filters_human_prefers_normalized_scanner_feature_coverage() -> None:
    scanner = {
        "feature_coverage": {
            "present": 10,
            "total": 12,
            "coverage_ratio": 10 / 12,
            "quality": "strong",
            "present_keys": [
                "engine_ma20_gap",
                "engine_adx14",
                "engine_trend_strength",
                "engine_volume_spike20",
                "engine_volatility20",
                "engine_vwap_distance",
                "engine_sector_relative_strength",
                "engine_cross_section_rank",
                "engine_regime",
                "engine_signal_score",
            ],
            "missing_keys": ["engine_ma60", "engine_ma120"],
        },
        "selected_candidate": {
            "sources": ["top_value", "sector_theme"],
            "risk_score": 0.60,
            "score_breakdown": {"theme_boost": 0.05},
            "component_snapshot": {"trading_value_component": 1.0, "sentiment_component": 0.03},
            "feature_snapshot": {
                "engine_trend_strength": 0.14,
                "engine_volume_spike20": 0.59,
                "engine_volatility20": 0.05,
                "engine_vwap_distance": 0.21,
                "engine_sector_relative_strength": 0.0,
                "engine_cross_section_rank": 0.75,
            },
        },
    }
    strategist = {"themes": ["defensive_large_cap"], "global_sentiment_score": -0.07}
    supervisor = {"supervisor_allow": True}

    out = story_pipeline.build_filters_human(scanner, strategist, supervisor)

    assert "10/12 captured features" in out["summary"]
    assert "strong" in out["summary"]
    assert any("chart completeness filter: PASS - 10/12 captured chart features" == bullet for bullet in out["bullets"])


def test_scanner_evidence_enrichment_normalizes_chart_coverage() -> None:
    scanner_reason = {
        "selected_symbol": "005930",
        "top_reasons": ["highest combined scanner score (1.173)", "chart feature coverage 6/12"],
        "bullets": ["Chart / feature coverage: 6/12"],
    }
    filters_human = {
        "summary": "Scanner and guard checks passed 4 of 8 visible gates. Chart completeness was partial with 6/12 captured features.",
        "bullets": ["chart completeness filter: PARTIAL - 6/12 captured chart features"],
    }
    scanner_evidence = {
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
    }

    enriched_reason = mod._enrich_scanner_reason_from_evidence(scanner_reason, scanner_evidence)
    enriched_filters = mod._enrich_filters_from_evidence(filters_human, scanner_evidence, selected_symbol="005930")

    assert "chart feature coverage 10/12" in enriched_reason["top_reasons"]
    assert "Chart / feature coverage: 10/12" in enriched_reason["bullets"]
    assert "10/12 captured features" in enriched_filters["summary"]
    assert "strong" in enriched_filters["summary"]
    assert "chart completeness filter: PASS - 10/12 captured chart features" in enriched_filters["bullets"]

def test_live_execution_bundle_report_builds_trade_lifecycle_with_entry_hold_exit(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "strategist",
                "event": "market_context_snapshot",
                "event_name": "strategist.market_context_snapshot",
                "agent": "strategist",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "market_regime": "neutral",
                    "market_sentiment": "neutral",
                    "playbook": "pullback",
                    "macro_inputs": {"kospi_pct": -0.2, "dxy_pct": 0.4, "vix": 25.4},
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "strategist",
                "event": "global_sentiment_breakdown",
                "event_name": "strategist.global_sentiment_breakdown",
                "agent": "strategist",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "global_sentiment_score": -0.12,
                    "factor_contributions": [
                        {"name": "vix", "value": 25.4, "contribution": -0.05},
                        {"name": "dxy_pct", "value": 0.4, "contribution": -0.03},
                    ],
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "strategist",
                "event": "news_evidence_ranked",
                "event_name": "strategist.news_evidence_ranked",
                "agent": "strategist",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "ranked_news": [
                        {"rank": 1, "title": "Chip demand stabilizes", "used_in_decision": True},
                        {"rank": 2, "title": "Macro remains defensive", "used_in_decision": True},
                    ],
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "strategist",
                "event": "decision_frame",
                "event_name": "strategist.decision_frame",
                "agent": "strategist",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "playbook": "pullback",
                    "themes": ["semiconductor"],
                    "avoid_themes": ["speculative_small_cap"],
                    "monitor_guidance": "tighten risk if leadership weakens",
                    "reason_chain": [
                        "Global sentiment stayed slightly negative.",
                        "Liquidity remained concentrated in semiconductor leaders.",
                    ],
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "strategist",
                "event": "llm_response_saved",
                "event_name": "strategist.llm_response_saved",
                "agent": "strategist",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "status": "ok",
                    "llm_response_artifact": {"path": f"reports/trades/{day}/TRD_TEST/strategist/strategist_llm_response.json"},
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:02+00:00",
                "stage": "scanner",
                "event": "candidate_pool_snapshot",
                "event_name": "scanner.candidate_pool_snapshot",
                "agent": "scanner",
                "phase": "session",
                "payload": {"candidate_count": 5, "source_mix": {"top_value": 3, "sector_theme": 2}},
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "scanner",
                "event": "candidate_ranking_table",
                "event_name": "scanner.candidate_ranking_table",
                "agent": "scanner",
                "phase": "session",
                "payload": {
                    "rows": [
                        {
                            "rank": 1,
                            "symbol": "000660",
                            "score_total": 1.23,
                            "score_breakdown": {"trading_value": 0.3, "theme_boost": 0.1},
                            "source_scores": {"top_value": 1.0, "sector_theme": 0.8},
                            "risk_score": 0.2,
                            "confidence": 0.91,
                            "theme_match": True,
                            "feature_coverage": {"present": 10, "total": 12},
                            "status": "selected",
                            "exclusion_reason": "",
                            "compact_feature_snapshot": {"engine_signal_score": 0.8},
                        },
                        {
                            "rank": 2,
                            "symbol": "005930",
                            "score_total": 1.11,
                            "score_breakdown": {"trading_value": 0.28},
                            "source_scores": {"top_value": 0.9},
                            "risk_score": 0.18,
                            "confidence": 0.82,
                            "theme_match": False,
                            "feature_coverage": {"present": 9, "total": 12},
                            "status": "runner_up",
                            "exclusion_reason": "weaker theme fit",
                            "compact_feature_snapshot": {"engine_signal_score": 0.7},
                        },
                    ]
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "scanner",
                "event": "candidate_selection_reason",
                "event_name": "scanner.candidate_selection_reason",
                "agent": "scanner",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "why_selected": ["highest combined score", "strongest theme match"],
                    "runner_up_reasons": [{"symbol": "005930", "lost_because": ["weaker theme fit"]}],
                    "tie_break_rule": "higher confidence wins",
                    "final_decision_basis": "value plus sector-theme alignment",
                },
            },
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:03+00:00",
                "stage": "scanner",
                "event": "selection_output",
                "event_name": "scanner.selection_output",
                "agent": "scanner",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "selected_symbol": "000660",
                    "selected_rank": 1,
                    "selected_snapshot": {"score_total": 1.23, "confidence": 0.91},
                },
            },
            {"run_id": "run-3", "ts": f"{day}T00:05:00+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "000660"}},
            {"run_id": "run-3", "ts": f"{day}T00:05:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}},
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:01+00:00",
                "stage": "monitor",
                "event": "threshold_snapshot",
                "event_name": "monitor.threshold_snapshot",
                "agent": "monitor",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "current_price": 70500.0,
                    "avg_price": 70000.0,
                    "peak_price": 71600.0,
                    "pnl_pct": 0.007142857,
                    "drawdown_pct": -0.0154,
                    "stop_loss_pct": 0.08,
                    "effective_stop_loss_pct": 0.03,
                    "take_profit_pct": 0.02,
                    "trailing_stop_pct": 0.01,
                    "vwap_distance_pct": -0.006,
                    "volatility_regime": "normal",
                    "active_exit_axis": "Hold",
                    "watch_axes": ["Hard stop", "Peak drawdown"],
                    "exit_confirm_required": 2,
                    "exit_confirm_count": 0,
                },
            },
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:01+00:00",
                "stage": "monitor",
                "event": "state_transition",
                "event_name": "monitor.state_transition",
                "agent": "monitor",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "previous_posture": "BUY",
                    "current_posture": "HOLD",
                    "previous_reason": "entry_ready",
                    "current_reason": "hold_position",
                    "state_changed": True,
                    "trigger_delta": {"previous_active_exit_axis": "", "current_active_exit_axis": "Hold"},
                },
            },
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:02+00:00",
                "stage": "monitor",
                "event": "exit_decision_detail",
                "event_name": "monitor.exit_decision_detail",
                "agent": "monitor",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "exit_triggered": False,
                    "triggered_rule": "hold",
                    "confirm_count": 0,
                    "confirm_required": 2,
                    "guard_blocked": False,
                    "guard_reason": "",
                    "sell_submitted": False,
                    "sell_skipped_reason": "",
                    "final_reason": "hold_position",
                },
            },
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:02+00:00",
                "stage": "monitor",
                "event": "cycle_summary",
                "event_name": "monitor.cycle_summary",
                "agent": "monitor",
                "phase": "session",
                "symbol": "000660",
                "payload": {
                    "selected_symbol": "000660",
                    "monitor_symbol": "000660",
                    "posture": "HOLD",
                    "monitor_reason": "hold_position",
                    "open_position_count": 1,
                    "has_intent": False,
                    "intent_side": "NOOP",
                    "active_exit_axis": "Hold",
                    "price_source": "position.current_price",
                    "feature_source": "selected.features",
                },
            },
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:02+00:00",
                "stage": "decision_trace",
                "event": "entry_exit_decision",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "monitor_reason": "hold_position",
                        "exit_reason": "hold",
                        "price_source": "position.current_price",
                        "price_source_policy": "market.quote > position.current_price > selected > market_snapshot > position.avg_plus_unrealized",
                        "feature_source": "selected.features",
                        "price": 70500.0,
                        "avg_price": 70000.0,
                        "peak_price": 71600.0,
                        "peak_drawdown": -0.0154,
                        "current_drawdown": -0.0154,
                        "vwap_distance": -0.006,
                        "thresholds": {
                            "stop_loss_pct": 0.08,
                            "effective_stop_loss_pct": 0.03,
                            "effective_stop_reason": "adaptive_stop",
                            "take_profit_pct": 0.02,
                        },
                    },
                },
            },
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    assert out["trade_lifecycle_count"] == 1
    assert out["run_bundle_count"] == 2
    lifecycle_row = out["bundles"][0]
    assert lifecycle_row["status"] == "closed"
    assert lifecycle_row["report_status"] == "available"
    assert lifecycle_row["entry_run_id"] == "run-1"
    assert lifecycle_row["exit_run_id"] == "run-2"
    assert "run-3" in lifecycle_row["hold_run_ids"]
    assert "run-3" in lifecycle_row["linked_run_ids"]
    assert lifecycle_row["story_type"] == "simulation"
    assert "simulation" in str(lifecycle_row["execution_mode_label"]).lower()
    assert (report_dir / "live_execution_bundle_run-1.json").exists()
    assert (report_dir / "live_execution_bundle_run-2.json").exists()

    bundle_obj = json.loads((report_dir / "live_execution_bundle_run-1.json").read_text(encoding="utf-8"))
    assert bundle_obj["execution"]["action"] == "BUY"
    assert bundle_obj["execution"]["symbol"] == "000660"
    assert bundle_obj["strategist"]["playbook"] == "pullback"
    assert bundle_obj["artifacts"]["trade_explain_json"].endswith(f"trade_explain_{day}.json")
    assert bundle_obj["trade_id"] == lifecycle_row["trade_id"]
    assert bundle_obj["story_id"] == lifecycle_row["trade_id"]
    assert bundle_obj["market_context_human"]["summary"]
    assert bundle_obj["scanner_reason_human"]["summary"]
    assert bundle_obj["filters_human"]["summary"]

    canonical_dir = reports_root / "trades" / "2026" / "03" / lifecycle_row["trade_id"]
    new_trade_root = reports_root / "trades" / day / lifecycle_row["trade_id"]
    assert (canonical_dir / "trade_lifecycle.json").exists()
    assert (canonical_dir / "aggregated_execution_bundle.json").exists()
    assert (canonical_dir / "trade_story_input.json").exists()
    assert (canonical_dir / "trade_report.json").exists()
    assert (canonical_dir / "trade_report.md").exists()
    assert (new_trade_root / "lifecycle" / "trade_lifecycle.json").exists()
    assert (new_trade_root / "lifecycle" / "aggregated_execution_bundle.json").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report_input.json").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report.json").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report.md").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json").exists()
    assert (new_trade_root / "strategist" / "strategist_llm_response.json").exists()
    assert (new_trade_root / "evidence" / "strategist_evidence.json").exists()
    assert (new_trade_root / "evidence" / "scanner_evidence.json").exists()
    assert (new_trade_root / "evidence" / "monitor_timeline.json").exists()

    trade_lifecycle = json.loads((canonical_dir / "trade_lifecycle.json").read_text(encoding="utf-8"))
    assert trade_lifecycle["status"] == "closed"
    assert trade_lifecycle["entry"]["run_id"] == "run-1"
    assert trade_lifecycle["exit"]["run_id"] == "run-2"
    assert "run-3" in trade_lifecycle["holding"]["run_ids"]
    assert trade_lifecycle["summary"]["holding_duration"]
    assert (trade_lifecycle.get("evidence") or {}).get("strategist_event_count", 0) >= 1
    assert (trade_lifecycle.get("evidence") or {}).get("scanner_event_count", 0) >= 1
    assert (trade_lifecycle.get("evidence") or {}).get("monitor_event_count", 0) >= 1

    story_input = json.loads((canonical_dir / "trade_story_input.json").read_text(encoding="utf-8"))
    assert story_input["schema_version"] == "trade_story_input.v2"
    assert story_input["trade_id"] == lifecycle_row["trade_id"]
    assert story_input["status"] == "closed"
    assert story_input["symbol"] == "000660"
    assert story_input["story_type"] == "simulation"
    assert "run-3" in story_input["holding_summary"]["run_ids"]
    assert story_input["entry_summary"]["reason_human"]
    assert "price source" in " ".join(story_input["monitor_reason_human"]["bullets"]).lower()
    assert "position.current_price" in " ".join(story_input["monitor_reason_human"]["bullets"]).lower()
    assert story_input["monitor_reason_human"]["current_price"] == 70500.0
    assert story_input["monitor_reason_human"]["peak_price"] == 71600.0
    assert story_input["monitor_reason_human"]["peak_drawdown"] == -0.0154
    assert story_input["monitor_reason_human"]["active_exit_axis"] == "Hold"
    assert "Hard stop" in story_input["monitor_reason_human"]["watch_axes"]
    assert story_input["strategist_evidence"]["market_context_snapshots"][0]["event_name"] == "strategist.market_context_snapshot"
    assert story_input["scanner_evidence"]["candidate_ranking_tables"][0]["payload"]["rows"][0]["symbol"] == "000660"
    assert story_input["monitor_timeline"]["threshold_snapshots"][0]["payload"]["active_exit_axis"] == "Hold"

    trade_report = json.loads((canonical_dir / "trade_report.json").read_text(encoding="utf-8"))
    llm_response = json.loads((new_trade_root / "ai_trade_report" / "ai_trade_report_llm_response.json").read_text(encoding="utf-8"))
    strategist_llm = json.loads((new_trade_root / "strategist" / "strategist_llm_response.json").read_text(encoding="utf-8"))
    assert (trade_report.get("ai_report_diagnostics") or {}).get("report_status") == "available"
    assert trade_report["status"] == "closed"
    assert trade_report["monitor_snapshot"]["current_price"] == 70500.0
    assert trade_report["monitor_snapshot"]["peak_price"] == 71600.0
    assert trade_report["monitor_snapshot"]["peak_drawdown"] == -0.0154
    assert "Hard stop" in trade_report["monitor_snapshot"]["watch_axes"]
    assert trade_report["monitor_snapshot"]["price_source"] in {"position.current_price", "market.quote.price"}
    assert trade_report["monitor_snapshot"]["effective_stop_reason"] == "adaptive_stop"
    assert trade_report["market_context_at_entry"]["summary"]
    assert trade_report["why_this_symbol_was_chosen"]["summary"]
    assert trade_report["entry_decision"]["summary"]
    assert trade_report["holding_monitoring_story"]["summary"]
    assert trade_report["exit_decision"]["summary"]
    assert trade_report["execution_quality"]["summary"]
    assert trade_report["reporter_evaluation"]["summary"]
    assert trade_report["full_timeline"]
    assert trade_report["action"] == "SELL"
    assert trade_report["executive_summary"]["action"] == "SELL"
    assert trade_report["final_operator_conclusion"]["current_action"] == "SELL"
    assert "sentiment" in trade_report["market_context_at_entry"]["summary"].lower()
    assert "price source" in " ".join(trade_report["holding_monitoring_story"]["bullets"]).lower()
    assert llm_response["component"] == "ai_trade_report"
    assert llm_response["trade_id"] == lifecycle_row["trade_id"]
    assert strategist_llm["component"] == "strategist"
    assert strategist_llm["trade_id"] == lifecycle_row["trade_id"]
    strategist_evidence = json.loads((new_trade_root / "evidence" / "strategist_evidence.json").read_text(encoding="utf-8"))
    scanner_evidence = json.loads((new_trade_root / "evidence" / "scanner_evidence.json").read_text(encoding="utf-8"))
    monitor_timeline = json.loads((new_trade_root / "evidence" / "monitor_timeline.json").read_text(encoding="utf-8"))
    assert strategist_evidence["decision_frames"][0]["payload"]["playbook"] == "pullback"
    assert scanner_evidence["candidate_selection_reasons"][0]["payload"]["final_decision_basis"] == "value plus sector-theme alignment"
    assert monitor_timeline["threshold_snapshots"][0]["payload"]["watch_axes"] == ["Hard stop", "Peak drawdown"]
    new_bundle = json.loads((new_trade_root / "lifecycle" / "aggregated_execution_bundle.json").read_text(encoding="utf-8"))
    assert (new_bundle.get("artifacts") or {}).get("strategist_evidence_json", "").endswith("strategist_evidence.json")
    assert (new_bundle.get("artifacts") or {}).get("scanner_evidence_json", "").endswith("scanner_evidence.json")
    assert (new_bundle.get("artifacts") or {}).get("monitor_timeline_json", "").endswith("monitor_timeline.json")
    assert (new_bundle.get("evidence") or {}).get("paths", {}).get("strategist_evidence_json", "").endswith("strategist_evidence.json")
    assert (new_bundle.get("evidence") or {}).get("paths", {}).get("scanner_evidence_json", "").endswith("scanner_evidence.json")
    assert (new_bundle.get("evidence") or {}).get("paths", {}).get("monitor_timeline_json", "").endswith("monitor_timeline.json")
    assert new_bundle["artifacts"]["strategist_llm_response_json"].endswith("strategist_llm_response.json")
    assert new_bundle["artifacts"]["ai_trade_report_llm_response_json"].endswith("ai_trade_report_llm_response.json")
    assert new_bundle["artifacts"]["ai_trade_report_input_json"].endswith("ai_trade_report_input.json")

    trade_report_md = (canonical_dir / "trade_report.md").read_text(encoding="utf-8")
    assert "# Trade Report" in trade_report_md
    assert "## Monitor Snapshot" in trade_report_md
    assert "current_price: 70500.00" in trade_report_md
    assert "peak_price: 71600.00" in trade_report_md
    assert "peak_drawdown: -1.54%" in trade_report_md
    assert "watch_axis: Hard stop" in trade_report_md
    assert "price_source: position.current_price" in trade_report_md or "price_source: market.quote.price" in trade_report_md
    assert "## Market Context at Entry" in trade_report_md
    assert "## Why This Symbol Was Chosen" in trade_report_md
    assert "## Entry Decision" in trade_report_md
    assert "## Holding / Monitoring Story" in trade_report_md
    assert "## Exit Decision" in trade_report_md
    assert "## Execution Quality" in trade_report_md
    assert "## Full Timeline" in trade_report_md
    assert "## Scanner Logic and Filters" in trade_report_md


def test_live_execution_bundle_report_explains_missing_reporter_linkage(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 2}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["bundles"][0]["status"] == "partial"
    story_id = out["bundles"][0]["story_id"]
    trade_report = json.loads((reports_root / "trades" / "2026" / "03" / story_id / "trade_report.json").read_text(encoding="utf-8"))
    reporter_eval = trade_report["reporter_evaluation"]
    assert reporter_eval["status"] == "pending"
    assert "not linked" in reporter_eval["summary"].lower() or "pending" in reporter_eval["summary"].lower()


def test_live_execution_bundle_report_links_hold_run_from_monitor_trace_symbol(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-3", "ts": f"{day}T00:05:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}},
            {
                "run_id": "run-3",
                "ts": f"{day}T00:05:02+00:00",
                "stage": "decision_trace",
                "event": "entry_exit_decision",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "selected_symbol": "000660",
                        "monitor_reason": "hold_position",
                        "exit_reason": "hold",
                        "price_source": "position.current_price",
                    },
                },
            },
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    lifecycle = out["bundles"][0]
    assert lifecycle["status"] == "open"
    assert "run-3" in lifecycle["hold_run_ids"]
    trade_dir = reports_root / "trades" / "2026" / "03" / lifecycle["story_id"]
    story_input = json.loads((trade_dir / "trade_story_input.json").read_text(encoding="utf-8"))
    assert "run-3" in story_input["holding_summary"]["run_ids"]
    assert "price source" in " ".join(story_input["monitor_reason_human"]["bullets"]).lower()


def test_live_execution_bundle_report_keeps_open_lifecycle_without_exit(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-3", "ts": f"{day}T00:05:00+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "000660"}},
            {"run_id": "run-3", "ts": f"{day}T00:05:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["trade_lifecycle_count"] == 1
    lifecycle = out["bundles"][0]
    assert lifecycle["status"] == "open"
    assert lifecycle["report_status"] == "available"
    assert lifecycle["report_reason_code"] == ""
    story_id = lifecycle["story_id"]
    trade_dir = reports_root / "trades" / "2026" / "03" / story_id
    new_trade_root = reports_root / "trades" / day / story_id
    assert (trade_dir / "trade_story_input.json").exists()
    assert (trade_dir / "trade_report.json").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report_input.json").exists()
    assert (new_trade_root / "ai_trade_report" / "ai_trade_report.json").exists()
    bundle = json.loads((trade_dir / "aggregated_execution_bundle.json").read_text(encoding="utf-8"))
    diagnostics = bundle.get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "available"
    assert diagnostics.get("report_reason_code") == ""


def test_live_execution_bundle_report_backfills_open_monitor_snapshot_from_runtime_state(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    state_path = tmp_path / "state.json"

    def _fake_sparse_trace(event_log_path, evidence_log_path, report_dir, *, run_id=None, day=None, reports_root=None, max_news_titles=5):  # type: ignore[no-untyped-def]
        report_dir.mkdir(parents=True, exist_ok=True)
        rid = str(run_id or "run")
        js_path = report_dir / f"agent_pipeline_trace_{rid}.json"
        md_path = report_dir / f"agent_pipeline_trace_{rid}.md"
        out = {
            "run_id": rid,
            "day": day,
            "commander": {"route_ts": f"{day}T00:00:00+00:00"},
            "strategist": {
                "playbook": "defensive",
                "themes": ["semiconductor"],
                "global_sentiment_score": -0.08,
                "fear_index": {"level": 24.8},
                "llm_parsed_output": {"market_regime": "neutral", "market_sentiment": "neutral"},
            },
            "scanner": {
                "top_stock": "000660",
                "candidate_pool_after_filter": 4,
                "selected_candidate": {"symbol": "000660", "why": "top_value+sector_theme"},
            },
            "monitor": {
                "selected_symbol": "000660",
                "entry_reason": "no_position",
                "exit_reason": "hold",
                "monitor_reason": "hold_position",
                "thresholds": {
                    "stop_loss_pct": 0.08,
                    "effective_stop_loss_pct": 0.03,
                    "effective_stop_reason": "adaptive_stop",
                    "take_profit_pct": 0.02,
                },
                "position_age_seconds": 180,
                "exit_triggered": False,
            },
            "supervisor": {"verdict": "approve", "supervisor_allow": True, "supervisor_reason": "risk checks passed"},
            "executor": {"execution_ok": True, "execution_attempted": True, "broker_env": "mock", "effective_mode": "mock_broker_http"},
            "reporter": {"reporter_analysis_day_file_found": False, "reporter_analysis_found": False, "reporter_analysis_path": ""},
        }
        js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(f"# trace {rid}\n", encoding="utf-8")
        return md_path, js_path, out

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}},
            {"run_id": "run-2", "ts": f"{day}T00:05:02+00:00", "stage": "decision_trace", "event": "entry_exit_decision", "payload": {"agent": "monitor", "payload": {"selected_symbol": "000660", "monitor_reason": "hold_position", "exit_reason": "hold"}}},
        ],
    )
    _write_jsonl(evidence_log, [])
    state_path.write_text(
        json.dumps(
            {
                "portfolio_snapshot": {
                    "positions": [
                        {
                            "symbol": "000660",
                            "qty": 1,
                            "avg_price": 70000.0,
                            "current_price": 70500.0,
                            "unrealized_pnl": 500.0,
                        }
                    ]
                },
                "mock_positions": [
                    {
                        "symbol": "000660",
                        "qty": 1,
                        "avg_price": 70000.0,
                        "unrealized_pnl": 500.0,
                    }
                ],
                "position_peak_price": {"000660": 72000.0},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STATE_STORE_PATH", str(state_path))
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_sparse_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    lifecycle = out["bundles"][0]
    assert lifecycle["status"] == "open"
    trade_dir = reports_root / "trades" / "2026" / "03" / lifecycle["story_id"]
    story_input = json.loads((trade_dir / "trade_story_input.json").read_text(encoding="utf-8"))
    trade_report = json.loads((trade_dir / "trade_report.json").read_text(encoding="utf-8"))

    monitor_reason = story_input["monitor_reason_human"]
    assert monitor_reason["current_price"] == 70500.0
    assert monitor_reason["average_price"] == 70000.0
    assert monitor_reason["peak_price"] == 72000.0
    assert round(float(monitor_reason["current_drawdown"]), 6) == round((70500.0 / 70000.0) - 1.0, 6)
    assert round(float(monitor_reason["peak_drawdown"]), 6) == round((70500.0 / 72000.0) - 1.0, 6)
    assert monitor_reason["price_source"] == "runtime_state.position.current_price"
    assert "runtime_state.position.current_price" in " ".join(monitor_reason["bullets"])

    monitor_snapshot = trade_report["monitor_snapshot"]
    assert monitor_snapshot["current_price"] == 70500.0
    assert monitor_snapshot["average_price"] == 70000.0
    assert monitor_snapshot["peak_price"] == 72000.0
    assert round(float(monitor_snapshot["peak_drawdown"]), 6) == round((70500.0 / 72000.0) - 1.0, 6)
    assert monitor_snapshot["price_source"] == "runtime_state.position.current_price"


def test_live_execution_bundle_report_marks_skipped_when_report_not_requested(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    lifecycle = out["bundles"][0]
    assert lifecycle["report_status"] == "skipped"
    assert lifecycle["report_reason_code"] == "report_not_requested"
    trade_dir = reports_root / "trades" / "2026" / "03" / lifecycle["story_id"]
    assert not (trade_dir / "trade_report.json").exists()
    bundle = json.loads((trade_dir / "aggregated_execution_bundle.json").read_text(encoding="utf-8"))
    diagnostics = bundle.get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "skipped"
    assert diagnostics.get("report_reason_code") == "report_not_requested"


def test_live_execution_bundle_report_preserves_existing_ai_report_when_generation_is_disabled(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)

    first_rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    first_out = json.loads(capsys.readouterr().out.strip())
    assert first_rc == 0
    trade_id = str(first_out["bundles"][0]["trade_id"])
    trade_dir = reports_root / "trades" / "2026" / "03" / trade_id
    llm_response_path = trade_dir / "ai_trade_report_llm_response.json"
    if not llm_response_path.exists():
        llm_response_path = trade_dir / "ai_trade_report" / "ai_trade_report_llm_response.json"
    existing_report = (trade_dir / "trade_report.json").read_text(encoding="utf-8")
    existing_md = (trade_dir / "trade_report.md").read_text(encoding="utf-8")
    existing_llm = llm_response_path.read_text(encoding="utf-8") if llm_response_path.exists() else ""

    second_rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--no-trade-report-ai",
            "--json",
        ]
    )
    second_out = json.loads(capsys.readouterr().out.strip())
    assert second_rc == 0
    lifecycle = second_out["bundles"][0]
    assert lifecycle["report_status"] == "available"

    diagnostics = json.loads((trade_dir / "aggregated_execution_bundle.json").read_text(encoding="utf-8")).get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "available"
    assert "preserved" in str(diagnostics.get("report_reason_human") or "").lower()
    assert (trade_dir / "trade_report.json").read_text(encoding="utf-8") == existing_report
    assert (trade_dir / "trade_report.md").read_text(encoding="utf-8") == existing_md
    if existing_llm:
        assert llm_response_path.read_text(encoding="utf-8") == existing_llm


def test_story_type_classification_is_deterministic() -> None:
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": True, "broker_env": "mock"}) == "simulation"
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": False, "broker_env": "real"}) == "failed_execution"
    assert mod._classify_story_type({}, {"execution_attempted": False, "execution_ok": False, "broker_env": "real"}) == "decision_only"
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": True, "broker_env": "real"}) == "live_trade"


def test_live_execution_bundle_report_succeeds_with_zero_executions_for_explicit_day(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-3", "ts": f"{day}T00:20:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold"}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)

    rc = mod.main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["ok"] is True
    assert out["bundle_count"] == 0


def test_build_run_snapshots_prefers_canonical_agent_artifacts(tmp_path: Path) -> None:
    day = "2026-03-18"
    event_log = tmp_path / "events.jsonl"
    reports_root = tmp_path / "reports"
    canonical_dir = reports_root / "canonical" / day / "run-1"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:00+00:00", "stage": "commander_router", "event": "route", "payload": {"mode": "integrated_chain", "phase": "session"}},
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "BBB"}},
            {"run_id": "run-1", "ts": f"{day}T00:00:02+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "event_log_hold", "exit_reason": "event_log_hold"}},
            {"run_id": "run-1", "ts": f"{day}T00:00:03+00:00", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": False, "reason": "event_log_block"}},
            {"run_id": "run-1", "ts": f"{day}T00:00:04+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"action": "BUY", "symbol": "BBB", "qty": 1, "status": "EVENT_ONLY"}},
        ],
    )
    (canonical_dir / "commander.json").write_text(
        json.dumps({"agent": "commander", "run_id": "run-1", "mode": "integrated_chain", "phase": "session", "path": "integrated_chain", "status": "ok"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (canonical_dir / "scanner.json").write_text(
        json.dumps({"agent": "scanner", "run_id": "run-1", "selected_symbol": "AAA", "top_stock": "AAA"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (canonical_dir / "monitor.json").write_text(
        json.dumps({"agent": "monitor", "run_id": "run-1", "monitor_reason": "canonical_hold", "exit_reason": "canonical_hold", "selected_symbol": "AAA"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (canonical_dir / "supervisor.json").write_text(
        json.dumps({"agent": "supervisor", "run_id": "run-1", "supervisor_allow": True, "supervisor_reason": "canonical_allow"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (canonical_dir / "executor.json").write_text(
        json.dumps({"agent": "executor", "run_id": "run-1", "action": "BUY", "symbol": "AAA", "qty": 1, "status": "FILLED"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows = mod._build_run_snapshots(event_log, day, reports_root=reports_root)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AAA"
    assert row["monitor_reason"] == "canonical_hold"
    assert row["verdict_allowed"] is True
    assert row["verdict_reason"] == "canonical_allow"
    assert row["execution"]["symbol"] == "AAA"
    assert row["evidence_provenance"]["scanner"] == "canonical"
    assert row["evidence_provenance"]["monitor"] == "canonical"


def test_trade_evidence_links_cached_strategist_frame_run() -> None:
    day = "2026-03-19"
    lifecycle = {
        "trade_id": "TRD_20260319_032820_02",
        "symbol": "032820",
        "run_ids_all": ["cached-buy-run"],
    }
    event_rows = [
        {
            "ts": f"{day}T01:49:30+00:00",
            "run_id": "strategist-source-run",
            "event_name": "strategist.market_context_snapshot",
            "agent": "strategist",
            "payload": {
                "global_signal": {
                    "score": -0.22,
                    "status": "ok",
                    "source": "yfinance",
                    "macro_moves": {"vix_level": 25.09, "dxy_pct": 0.59},
                    "fear_index": {"level": 25.09, "level_pressure": 0.2545},
                },
                "macro_stress_overlay": {"active": True, "stress_flags": ["elevated_vix"]},
            },
        },
        {
            "ts": f"{day}T01:49:30+00:00",
            "run_id": "strategist-source-run",
            "event_name": "strategist.decision_frame",
            "agent": "strategist",
            "payload": {
                "market_regime": "neutral",
                "market_sentiment": "bearish",
                "playbook": "defensive",
                "themes": ["defensive_assets"],
            },
        },
        {
            "ts": f"{day}T01:50:19+00:00",
            "run_id": "cached-buy-run",
            "event_name": "commander_router.fast_path",
            "agent": "commander_router",
            "payload": {"path": "integrated_chain_cached_frame", "reuse_sec": 180, "reason": "flat_position_cached_strategist"},
        },
    ]

    strategist_evidence, _scanner_evidence, _monitor_timeline = mod._build_trade_evidence_from_events(
        event_rows=event_rows,
        lifecycle=lifecycle,
    )
    hydrated = mod._hydrate_strategist_payload_from_evidence({}, strategist_evidence)

    assert strategist_evidence["run_ids"] == ["strategist-source-run"]
    assert strategist_evidence["linked_cached_frame_sources"] == {"cached-buy-run": "strategist-source-run"}
    assert hydrated["market_regime"] == "neutral"
    assert hydrated["market_sentiment"] == "bearish"
    assert hydrated["playbook"] == "defensive"
    assert hydrated["global_sentiment_score"] == -0.22
    assert hydrated["fear_index"]["level"] == 25.09


def test_build_strategist_llm_response_artifact_reconstructs_cached_evidence() -> None:
    artifact = mod._build_strategist_llm_response_artifact(
        {
            "run_id": "cached-buy-run",
            "strategist": {
                "llm_ok": False,
                "llm_response": "",
                "llm_parsed_output": {"market_regime": "stale"},
            },
        },
        day="2026-03-19",
        trade_id="TRD_20260319_000660_02",
        strategist_evidence={
            "run_ids": ["source-strategist-run"],
            "llm_response_saved": [
                {
                    "event_name": "strategist.llm_response_saved",
                    "payload": {
                        "status": "ok",
                        "model": "minimax/minimax-m2.5",
                        "provider": "OpenRouter",
                        "attempts": 1,
                    },
                }
            ],
        },
        evidence_rows=[
            {
                "timestamp": "2026-03-19T02:20:02+00:00",
                "run_id": "source-strategist-run",
                "agent": "strategist",
                "stage": "theme_selection",
                "llm_prompt": "[system]\nFollow schema.\n[user]\nAssess macro context.",
                "llm_response": "{\"market_regime\": \"neutral\", \"market_sentiment\": \"bearish\"}",
                "parsed_output": {
                    "market_regime": "neutral",
                    "market_sentiment": "bearish",
                    "playbook": "defensive",
                },
            }
        ],
    )

    assert artifact["component"] == "strategist"
    assert artifact["trade_id"] == "TRD_20260319_000660_02"
    assert artifact["status"] == "ok"
    assert artifact["llm_status"] == "ok"
    assert artifact["model"] == "minimax/minimax-m2.5"
    assert artifact["raw_response_text"].startswith("{\"market_regime\"")
    assert artifact["parsed_output"]["market_regime"] == "neutral"
    assert artifact["parsed_output"]["playbook"] == "defensive"
    assert artifact["retry_count"] == 0
    assert artifact["meta"]["reconstructed_from_evidence_ledger"] is True
    assert artifact["meta"]["source_run_id"] == "source-strategist-run"
    assert artifact["meta"]["source_stage"] == "theme_selection"


def test_build_strategist_input_artifacts_reconstructs_trade_visible_input() -> None:
    input_artifact, compact_artifact = mod._build_strategist_input_artifacts(
        {
            "run_id": "cached-buy-run",
            "strategist": {},
        },
        day="2026-03-19",
        trade_id="TRD_20260319_005930_01",
        strategist_evidence={"run_ids": ["source-strategist-run"]},
        evidence_rows=[
            {
                "timestamp": "2026-03-19T02:19:59+00:00",
                "run_id": "source-strategist-run",
                "agent": "strategist",
                "stage": "theme_selection",
                "decision_link": {"stage": "strategist_input_collection"},
                "raw_input": {
                    "global_sentiment_inputs": {"score": -0.22, "fear_index": {"level": 25.09}},
                    "news_query_targets": ["KOSPI", "semiconductor"],
                    "llm_payload": {
                        "global_sentiment_signal": {"score": -0.22, "fear_index": {"level": 25.09}},
                        "news_context": {"headline_count": 75, "signal_total": 5},
                        "candidate_symbols_hint": ["005930", "000660"],
                    },
                },
            },
            {
                "timestamp": "2026-03-19T02:20:00+00:00",
                "run_id": "source-strategist-run",
                "agent": "strategist",
                "stage": "theme_selection",
                "llm_prompt": "[system]\nFollow schema.\n[user]\nAssess entry setup.",
                "raw_input": {
                    "global_sentiment_signal": {"score": -0.22},
                    "news_context": {"headline_count": 75},
                    "candidate_symbols_hint": ["005930"],
                },
            },
        ],
    )

    assert input_artifact["component"] == "strategist"
    assert input_artifact["run_id"] == "cached-buy-run"
    assert input_artifact["trade_id"] == "TRD_20260319_005930_01"
    assert input_artifact["status"] == "ok"
    assert input_artifact["source_input"]["global_sentiment_signal"]["score"] == -0.22
    assert input_artifact["source_input"]["news_context"]["headline_count"] == 75
    assert input_artifact["summary"]["global_sentiment_score"] == -0.22
    assert input_artifact["summary"]["headline_count"] == 75
    assert input_artifact["summary"]["candidate_symbols_hint"] == ["005930", "000660"]
    assert input_artifact["system_prompt"] == "Follow schema."
    assert input_artifact["user_prompt"] == "Assess entry setup."
    assert input_artifact["meta"]["source_run_id"] == "source-strategist-run"
    assert compact_artifact["component"] == "strategist"
    assert compact_artifact["compact_input"]["candidate_symbols_hint"] == ["005930"]
    assert compact_artifact["meta"]["reconstructed_from_evidence_ledger"] is True


def test_attach_strategy_anchor_adds_linkage_metadata() -> None:
    enriched = mod._attach_strategy_anchor(
        {"summary": "scanner selected 005930"},
        strategy_anchor_run_id="strategist-run-1",
        strategist_input_path=Path("reports/trades/2026-03-19/TRD_20260319_005930_01/strategist/strategist_input.json"),
        strategist_compact_input_path=Path("reports/trades/2026-03-19/TRD_20260319_005930_01/strategist/strategist_compact_input.json"),
        strategist_llm_response_path=Path("reports/trades/2026-03-19/TRD_20260319_005930_01/strategist/strategist_llm_response.json"),
    )

    assert enriched["entry_strategist_run_id"] == "strategist-run-1"
    assert enriched["strategy_anchor_run_id"] == "strategist-run-1"
    assert enriched["strategy_anchor"]["run_id"] == "strategist-run-1"
    assert enriched["strategy_anchor"]["artifacts"]["strategist_input_json"].endswith("strategist_input.json")


def test_enrich_strategist_from_input_summary_backfills_market_context_fields() -> None:
    enriched = mod._enrich_strategist_from_input_summary(  # type: ignore[attr-defined]
        {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "breakout",
            "global_sentiment_score": None,
            "fear_index": {},
            "global_macro_moves": {},
            "news_context": {"signal_total": 15},
            "market_news_query_count": 0,
            "market_news_total_headlines": None,
        },
        {
            "summary": {
                "global_sentiment_score": -0.2235,
                "vix_level": 25.09,
                "vix_change_pct": 12.16,
                "vix_level_pressure": 0.255,
                "headline_count": 75,
                "candidate_signal_total": 5,
                "market_signal_total": 10,
                "news_query_targets": ["코스피", "미국 증시", "국제유가", "환율"],
            }
        },
    )

    assert enriched["global_sentiment_score"] == -0.2235
    assert enriched["fear_index"]["level"] == 25.09
    assert enriched["global_macro_moves"]["vix_pct"] == 12.16
    assert enriched["news_context"]["headline_count"] == 75
    assert enriched["news_context"]["candidate_signal_total"] == 5
    assert enriched["news_context"]["market_signal_total"] == 10
    assert enriched["market_news_total_headlines"] == 75
    assert enriched["market_news_query_count"] == 4
    assert enriched["news_query_targets"] == ["코스피", "미국 증시", "국제유가", "환율"]



def test_enrich_scanner_reason_from_evidence_surfaces_selection_basis_and_runner_ups() -> None:
    enriched = mod._enrich_scanner_reason_from_evidence(  # type: ignore[attr-defined]
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

    assert enriched["why_selected"][0] == "highest total score (1.178)"
    assert enriched["selection_basis"] == "Scanner selected the highest-ranked candidate after strategist-guided weighting."
    assert enriched["tie_break_rule"] == "score_total desc -> confidence desc -> risk_score asc"
    assert enriched["runner_ups_lost"][0]["symbol"] == "005930"
    assert "Selection decision:" in " ".join(enriched["bullets"])
    assert "Runner-ups lost because:" in " ".join(enriched["bullets"])
