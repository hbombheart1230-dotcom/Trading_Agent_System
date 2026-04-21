from libs.reporting.trade_story_pipeline import (
    build_execution_outcome_human,
    build_trade_story_input,
    build_trade_story_input_from_bundle,
    build_lifecycle_bundle,
    build_market_context_human,
    build_monitor_reason_human,
    build_scanner_reason_human,
    enrich_filters_from_evidence,
    enrich_scanner_reason_from_evidence,
)
import json
from pathlib import Path


def test_build_execution_outcome_human_emits_korean_live_execution_summary() -> None:
    out = build_execution_outcome_human(
        {
            "action": "SELL",
            "symbol": "005380",
            "qty": 1,
            "filled_price": 537000,
            "ord_no": "0123456",
            "status": "filled",
        },
        {"broker_env": "real"},
        story_type="live_trade",
        mode_label="real",
    )

    assert out["summary"] == "005380 1주 매도 주문은 실거래로 체결됐고 체결 기준 가격은 537000.00였습니다."
    assert "Execution outcome:" not in "\n".join(str(row) for row in out["bullets"])
    assert any("주문 번호는 0123456였습니다." == row for row in out["bullets"])


def test_build_trade_story_input_from_bundle_synthesizes_execution_summary_from_lifecycle() -> None:
    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {
                "run_id": "RUN_ENTRY",
                "ts": "2026-04-21T00:10:00+00:00",
                "action": "BUY",
                "execution_details": {"order_id": "0100001", "filled_price": 537000},
                "scanner_context": {"selected_symbol": "005380"},
            },
            "hold": {"run_ids": ["RUN_MONITOR_1"]},
            "exit": {
                "run_id": "RUN_EXIT",
                "ts": "2026-04-21T00:11:00+00:00",
                "action": "SELL",
                "execution_details": {"order_id": "0100002", "filled_price": 537000},
            },
            "summary": {"lifecycle_summary_human": "closed"},
        },
        "execution_outcome_human": {},
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {"summary": "scanner", "selected_symbol": "005380"},
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "guard_reason_human": {"summary": "guard"},
        "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["execution_outcome_human"]["summary"] == "005380 거래는 매수 진입 후 매도 청산까지 기록됐습니다. 브로커 매수가/매도가는 537000.00 / 537000.00였습니다."
    assert any("진입 주문 번호는 0100001였습니다." == row for row in out["execution_outcome_human"]["bullets"])
    assert any("청산 주문 번호는 0100002였습니다." == row for row in out["execution_outcome_human"]["bullets"])


def test_build_trade_story_input_from_bundle_synthesizes_operator_conclusion_when_placeholder() -> None:
    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {
                "run_id": "RUN_ENTRY",
                "ts": "2026-04-21T00:10:00+00:00",
                "action": "BUY",
                "execution_details": {"order_id": "0100001", "filled_price": 537000},
                "scanner_context": {"selected_symbol": "005380"},
            },
            "hold": {"run_ids": ["RUN_MONITOR_1"]},
            "exit": {
                "run_id": "RUN_EXIT",
                "ts": "2026-04-21T00:11:00+00:00",
                "action": "SELL",
                "execution_details": {"order_id": "0100002", "filled_price": 537000},
            },
            "summary": {"lifecycle_summary_human": "closed"},
        },
        "execution_outcome_human": {},
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {"summary": "scanner", "selected_symbol": "005380"},
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "guard_reason_human": {"summary": "guard"},
        "reporter_status_human": {"status": "missing", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "최종 생애주기 결론은 기록되지 않았습니다."},
        "timeline": [],
        "warnings": [],
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["operator_conclusion_human"]["summary"] != "최종 생애주기 결론은 기록되지 않았습니다."
    assert "005380" in out["operator_conclusion_human"]["summary"]
    assert out["operator_conclusion_human"]["current_action"] == "SELL"
    assert out["report_section_seeds"]["final_operator_conclusion"]["summary"] == out["operator_conclusion_human"]["summary"]


def test_build_trade_story_input_from_bundle_normalizes_reporter_status_human() -> None:
    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {"run_id": "RUN_ENTRY", "action": "BUY", "scanner_context": {"selected_symbol": "005380"}},
            "hold": {"run_ids": []},
            "exit": {"run_id": "RUN_EXIT", "action": "SELL"},
            "summary": {"lifecycle_summary_human": "closed"},
        },
        "reporter_status_human": {
            "status": "missing",
            "summary": "Same-day reporter analysis was not generated yet.",
            "grade": "N/A",
            "bullets": [
                "Link same-day reporter analysis to this lifecycle for a complete quality review.",
                "Holding-phase evidence is thin; preserve more monitor context between entry and exit.",
            ],
        },
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["reporter_status_human"]["summary"] == "당일 리포터 분석은 아직 생성되지 않았습니다."
    assert out["reporter_status_human"]["bullets"] == [
        "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
        "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 문맥이 충분하지 않습니다.",
    ]


def test_build_trade_story_input_from_bundle_normalizes_hold_lifecycle_shape() -> None:
    bundle_out = {
        "day": "2026-04-16",
        "trade_id": "TRD_20260416_000660_01",
        "run_id": "RUN_EXIT",
        "symbol": "000660",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {
                "run_id": "RUN_ENTRY",
                "ts": "2026-04-16T00:10:00+00:00",
                "action": "BUY",
                "reason_human": "entry ok",
                "scanner_context": {"selected_symbol": "000660"},
            },
            "hold": {"run_ids": ["RUN_MONITOR_1"]},
            "exit": {
                "run_id": "RUN_EXIT",
                "ts": "2026-04-16T00:11:00+00:00",
                "action": "SELL",
                "reason_human": "exit ok",
            },
        },
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {
            "summary": "scanner",
            "selected_symbol": "000660",
            "selected_rank": 1,
            "candidate_count": 5,
            "top_candidates": [{"symbol": "000660", "score": 1.2}],
        },
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "monitor": {
            "decision_action": "sell",
            "exit_reason": "peak_drawdown",
            "current_price": 536000.0,
            "avg_price": 537000.0,
            "account_pnl_ratio": -0.0108,
            "effective_pnl_ratio": -0.0108,
            "price_source": "position.current_price",
        },
        "guard_reason_human": {"summary": "guard"},
        "execution_outcome_human": {"summary": "execution"},
        "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "scanner_evidence": {
            "candidate_ranking_table": {
                "rows": [{"symbol": "000660", "score_total": 1.2}],
            }
        },
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["status"] == "closed"
    assert out["action"] == "SELL"
    assert out["symbol"] == "000660"
    assert out["scanner_reason_human"]["selected_symbol"] == "000660"
    assert out["scanner_selection_trace"]["selected_symbol"] == "000660"
    assert len(out["scanner_selection_trace"]["ranked_candidates"]) >= 1
    assert out["canonical_monitor"]["account_pnl_ratio"] == -0.0108
    assert out["canonical_monitor"]["current_price"] == 536000.0


def test_build_trade_story_input_from_bundle_loads_canonical_monitor_from_artifact_path(tmp_path: Path) -> None:
    canonical_monitor = tmp_path / "reports" / "canonical" / "2026-04-21" / "run-1" / "monitor.json"
    canonical_monitor.parent.mkdir(parents=True, exist_ok=True)
    canonical_monitor.write_text(
        json.dumps(
            {
                "decision_action": "sell",
                "exit_reason": "peak_drawdown",
                "current_price": 536000.0,
                "avg_price": 537000.0,
                "account_pnl_ratio": -0.0108,
                "effective_pnl_ratio": -0.0108,
                "price_source": "position.current_price",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {"run_id": "RUN_ENTRY", "action": "BUY", "scanner_context": {"selected_symbol": "034020"}},
            "exit": {"run_id": "RUN_EXIT", "action": "SELL", "reason_human": "exit ok"},
        },
        "artifacts": {
            "canonical_monitor_json": str(canonical_monitor),
        },
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {"summary": "scanner", "selected_symbol": "034020"},
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "guard_reason_human": {"summary": "guard"},
        "execution_outcome_human": {"summary": "execution"},
        "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["canonical_monitor"]["account_pnl_ratio"] == -0.0108
    assert out["canonical_monitor"]["current_price"] == 536000.0


def test_build_trade_story_input_from_bundle_reanchors_scanner_symbol_for_monitor_fallback_trade() -> None:
    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {"run_id": "RUN_ENTRY", "action": "BUY", "scanner_context": {"selected_symbol": "034020"}},
            "exit": {"run_id": "RUN_EXIT", "action": "SELL", "reason_human": "exit ok"},
        },
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {
            "summary": "Scanner selected 034020.",
            "selected_symbol": "034020",
            "selected_rank": 1,
            "selected_score": 1.703,
            "top_candidates": [
                {"rank": 1, "symbol": "034020", "score_total": 1.703, "risk_score": 0.085, "confidence": 0.99},
                {"rank": 2, "symbol": "036930", "score_total": 1.639, "risk_score": 0.454, "confidence": 0.96},
                {"rank": 3, "symbol": "005380", "score_total": 1.606, "risk_score": 0.146, "confidence": 0.965},
            ],
        },
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "monitor": {
            "decision_action": "buy",
            "scanner_monitor_handoff": {
                "scanner_selected_symbol": "034020",
                "monitor_selected_symbol": "005380",
                "scanner_rank": 1,
                "entry_candidate_cascade": {
                    "fallback_used": True,
                    "fallback_to_symbol": "005380",
                    "reason": "breakout_not_ready",
                    "fallback_trace": [
                        {"symbol": "005380", "triggered": True, "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"}
                    ],
                    "runner_rows": [
                        {
                            "rank": 3,
                            "symbol": "005380",
                            "score_total": 1.606,
                            "risk_score": 0.146,
                            "confidence": 0.965,
                            "score_breakdown": {"trading_value": 0.211, "momentum": 0.208, "trend": 0.155},
                        }
                    ],
                },
            },
        },
        "scanner": {
            "selected_symbol": "034020",
            "top_stock": "034020",
            "ranking_table": [
                {"rank": 1, "symbol": "034020", "score_total": 1.703, "risk_score": 0.085, "confidence": 0.99},
                {"rank": 2, "symbol": "036930", "score_total": 1.639, "risk_score": 0.454, "confidence": 0.96},
                {"rank": 3, "symbol": "005380", "score_total": 1.606, "risk_score": 0.146, "confidence": 0.965},
            ],
        },
        "guard_reason_human": {"summary": "guard"},
        "execution_outcome_human": {"summary": "execution"},
        "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["symbol"] == "005380"
    assert out["scanner_reason_human"]["selected_symbol"] == "005380"
    assert out["scanner_reason_human"]["monitor_fallback_used"] is True
    assert out["scanner_reason_human"]["scanner_top_pick_symbol"] == "034020"
    assert "034020" in out["scanner_reason_human"]["summary"]
    assert "005380" in out["scanner_reason_human"]["summary"]
    assert out["scanner_selection_trace"]["selected_symbol"] == "005380"
    assert out["scanner_selection_trace"]["monitor_fallback_used"] is True
    assert out["scanner_selection_trace"]["scanner_top_pick_symbol"] == "034020"


def test_build_trade_story_input_from_bundle_prefers_entry_run_monitor_for_fallback_reanchor(tmp_path: Path) -> None:
    canonical_root = tmp_path / "reports" / "canonical" / "2026-04-21"
    entry_run = canonical_root / "run-entry"
    exit_run = canonical_root / "run-exit"
    entry_run.mkdir(parents=True, exist_ok=True)
    exit_run.mkdir(parents=True, exist_ok=True)
    (entry_run / "scanner.json").write_text(
        json.dumps({"selected_symbol": "034020", "top_stock": "034020"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (entry_run / "monitor.json").write_text(
        json.dumps(
            {
                "scanner_monitor_handoff": {
                    "scanner_selected_symbol": "034020",
                    "monitor_selected_symbol": "005380",
                    "entry_candidate_cascade": {
                        "fallback_used": True,
                        "fallback_to_symbol": "005380",
                        "reason": "breakout_not_ready",
                        "fallback_trace": [
                            {
                                "symbol": "005380",
                                "triggered": True,
                                "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                            }
                        ],
                        "runner_rows": [
                            {"rank": 3, "symbol": "005380", "score_total": 1.606, "risk_score": 0.146, "confidence": 0.965}
                        ],
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (exit_run / "monitor.json").write_text(
        json.dumps(
            {
                "decision_action": "sell",
                "current_price": 536000.0,
                "scanner_monitor_handoff": {
                    "scanner_selected_symbol": "005380",
                    "monitor_selected_symbol": "005380",
                    "entry_candidate_cascade": {
                        "attempted": False,
                        "fallback_used": False,
                        "fallback_to_symbol": "",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle_out = {
        "day": "2026-04-21",
        "trade_id": "TRD_20260421_005380_01",
        "run_id": "RUN_EXIT",
        "symbol": "005380",
        "trade_lifecycle_status": "closed",
        "lifecycle": {
            "entry": {"run_id": "run-entry", "action": "BUY", "scanner_context": {"selected_symbol": "034020"}},
            "exit": {"run_id": "run-exit", "action": "SELL", "reason_human": "exit ok"},
        },
        "artifacts": {
            "canonical_scanner_json": str(entry_run / "scanner.json"),
            "canonical_monitor_json": str(exit_run / "monitor.json"),
        },
        "market_context_human": {"summary": "market"},
        "scanner_reason_human": {"summary": "scanner", "selected_symbol": "034020", "selected_rank": 1},
        "filters_human": {"summary": "filters"},
        "monitor_reason_human": {"summary": "monitor"},
        "guard_reason_human": {"summary": "guard"},
        "execution_outcome_human": {"summary": "execution"},
        "reporter_status_human": {"status": "linked_run", "summary": "reporter"},
        "operator_conclusion_human": {"summary": "conclusion"},
        "timeline": [],
        "warnings": [],
        "monitor_timeline": {},
    }

    out = build_trade_story_input_from_bundle(bundle_out)

    assert out["scanner_reason_human"]["selected_symbol"] == "005380"
    assert out["scanner_reason_human"]["monitor_fallback_used"] is True
    assert out["scanner_selection_trace"]["selected_symbol"] == "005380"


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
                "score_breakdown": {"trading_value": 0.22, "trend": 0.16, "theme_boost": 0.0624, "sentiment": 0.018},
                "component_snapshot": {"news_sentiment": 0.04, "global_sentiment": 0.08, "sentiment_component": 0.052},
                "feature_snapshot": {"engine_ma20_gap": 0.05, "engine_adx14": 13.17, "engine_trend_strength": 0.13},
            },
            "candidate_preview": [
                {"symbol": "005930", "why": "weaker sector fit"},
                {"symbol": "047040", "why": "higher volatility and lower confidence"},
            ],
        },
        {
            "playbook": "breakout",
            "themes": ["broad_market_leaders"],
            "news_query_targets": ["KOSPI", "US indices"],
            "news_evidence_ranked": {
                "market_news_ranked": [{"title": "KOSPI advanced on institutional flows."}],
                "candidate_news_ranked": [{"symbol": "000660", "title": "000660 gained on AI memory demand headlines."}],
            },
        },
    )

    assert out["selected_symbol"] == "000660"
    assert out["selected_rank"] == 1
    assert out["selected_score"] == 1.1776
    assert len(out["top_candidates"]) == 3
    assert out["runner_ups"][0]["symbol"] == "005930"
    assert "score gap" in out["runner_ups"][0]["why"]
    assert any("Top candidates:" in row for row in out["bullets"])
    assert any("Why not others:" in row for row in out["bullets"])
    assert any("Core score contributions:" in row for row in out["bullets"])
    assert any("Sentiment input trace:" in row for row in out["bullets"])
    assert out["news_scanner_contribution"]["core_score_contributions"]["sentiment"]["value"] == 0.018
    assert out["news_scanner_contribution"]["theme_alignment_trace"]["theme_source_matched"] is True
    assert out["scanner_selection_trace"]["news_scanner_contribution"]["news_linkage_trace"]["symbol_headline_count"] >= 0


def test_scanner_reason_human_includes_trace_chart_feature_coverage_when_available() -> None:
    out = build_scanner_reason_human(
        {
            "selected_symbol": "000660",
            "ranking_table": [
                {
                    "rank": 1,
                    "symbol": "000660",
                    "score_total": 1.1776,
                    "risk_score": 0.6281,
                    "confidence": 0.8099,
                    "feature_coverage": {"present": 12, "total": 13, "quality": "strong"},
                }
            ],
            "candidate_ranking_table": {
                "rows": [
                    {
                        "rank": 1,
                        "symbol": "000660",
                        "score_total": 1.1776,
                        "feature_coverage": {"present": 12, "total": 13, "quality": "strong"},
                    }
                ]
            },
            "selected_candidate": {
                "symbol": "000660",
                "sources": ["top_value"],
                "score_total": 1.1776,
                "confidence": 0.8099,
                "risk_score": 0.6281,
                "score_breakdown": {"trading_value": 0.22},
                "feature_snapshot": {"engine_ma20_gap": 0.05, "engine_adx14": 13.17},
            },
        },
        {"playbook": "breakout"},
    )

    trace = out["scanner_selection_trace"]
    assert trace["chart_feature_coverage"]["present"] == 12
    assert trace["chart_feature_coverage"]["total"] == 13


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
            "entry_condition_path": "breakout_path",
            "entry_condition_paths_passed": ["breakout_path"],
            "entry_condition_scores": {
                "breakout_score": 1.0,
                "volume_score": 0.72,
                "pullback_score": 0.51,
                "confidence_score": 0.55,
                "confidence_threshold": 0.55,
            },
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
    assert out["entry_condition_path"] == "breakout_path"
    assert any("Entry timeframe: 1m" in row for row in out["bullets"])
    assert any("Grouped entry path: breakout_path" in row for row in out["bullets"])
    assert any("Volume ratio: 2.31" in row for row in out["bullets"])
    assert any("Extended from VWAP:" in row for row in out["bullets"])
    assert "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation" in out["summary"]
    assert "Path: breakout path." in out["summary"]


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


def test_monitor_reason_human_surfaces_eod_carry_anomaly() -> None:
    out = build_monitor_reason_human(
        {
            "monitor_reason": "hold",
            "position_age_seconds": 1280,
            "eod_carry_anomaly": True,
            "eod_carry_anomaly_reason": "minutes_to_close_missing",
            "exit_triggered": False,
        },
        {"action": "NOOP"},
    )

    assert "without a valid end-of-day carry decision" in out["summary"]
    assert out["eod_carry_anomaly"] is True
    assert out["eod_carry_anomaly_reason"] == "minutes_to_close_missing"
    assert any("EOD carry anomaly: yes (minutes_to_close_missing)" in row for row in out["bullets"])


def test_build_lifecycle_bundle_populates_top_level_summary_fields() -> None:
    out = build_lifecycle_bundle(
        day="2026-03-27",
        trade_id="TRD_20260327_032820_01",
        run_id="run-1",
        symbol="032820",
        lifecycle={
            "entry": {"decision": "BUY", "reason_human": "Breakout confirmation captured."},
            "holding": {"holding_events": [{"ts": "2026-03-27T05:10:00+00:00", "status": "HOLD"}]},
            "exit": {"decision": "SELL", "reason_human": "Peak drawdown triggered."},
            "summary": {
                "holding_duration": "23m",
                "entry_reason_human": "Breakout confirmation captured.",
                "exit_reason_human": "Peak drawdown triggered.",
            },
        },
        strategist_summary={"playbook": "breakout"},
        scanner_summary={"selected_symbol": "032820"},
        monitor_summary={"monitor_reason": "peak_drawdown"},
        commander_summary={"path": "cached_strategist"},
        story_input={
            "trade_id": "TRD_20260327_032820_01",
            "story_id": "TRD_20260327_032820_01",
            "symbol": "032820",
            "status": "closed",
            "action": "SELL",
            "monitor_reason_human": {"pnl": 1200, "current_drawdown": -0.011},
            "entry_reason_human": {"summary": "Breakout confirmation captured."},
            "section_provenance": {},
            "evidence_provenance": {},
        },
        diagnostics={},
        canonical_refs={},
        llm_refs={},
        artifact_links={},
    )

    assert isinstance(out["entry"], dict)


def test_build_trade_story_input_derives_provenance_from_canonical_artifacts_when_missing() -> None:
    lifecycle = {
        "trade_id": "TRD_20260415_000660_99",
        "symbol": "000660",
        "status": "closed",
        "entry": {"run_id": "entry-run", "ts": "2026-04-15T00:00:00+00:00", "action": "BUY"},
        "holding": {},
        "exit": {"run_id": "exit-run", "ts": "2026-04-15T00:05:00+00:00", "action": "SELL"},
        "summary": {"holding_duration": "5m", "lifecycle_summary_human": "Closed trade."},
    }
    bundle_out = {
        "day": "2026-04-15",
        "run_id": "exit-run",
        "trade_id": "TRD_20260415_000660_99",
        "story_contract": {"story_type": "live_trade", "execution_mode_label": "live"},
        "artifacts": {
            "agent_pipeline_trace_json": "reports/trades/2026-04-15/TRD_20260415_000660_99/agent_pipeline_trace.json",
            "canonical_commander_json": "reports/canonical/2026-04-15/exit-run/commander.json",
            "canonical_scanner_json": "reports/canonical/2026-04-15/entry-run/scanner.json",
            "canonical_monitor_json": "reports/canonical/2026-04-15/exit-run/monitor.json",
            "canonical_executor_json": "reports/canonical/2026-04-15/exit-run/executor.json",
        },
        "canonical_agent_artifacts": {
            "commander": {"selected_route": "monitor_only"},
            "scanner": {
                "selected_symbol": "000660",
                "selected_candidate": {"symbol": "000660", "confidence": 0.81, "score_total": 1.22},
                "ranking_table": [{"rank": 1, "symbol": "000660", "score_total": 1.22, "confidence": 0.81}],
            },
            "monitor": {
                "trigger_type": "peak_drawdown",
                "thresholds": {"hard_stop_pct": 0.02, "take_profit_pct": 0.01},
            },
            "executor": {"action": "SELL", "order_status": "filled", "avg_price": 1000.0},
        },
        "evidence_provenance": {},
        "scanner_reason_human": {"summary": "Scanner rationale.", "scanner_selection_trace": {}, "ranked_candidates": []},
        "monitor_reason_human": {"summary": "Monitor rationale.", "monitor_stop_policy_trace": {}, "monitor_blocker_trace": {}},
        "execution_outcome_human": {"summary": "Execution completed."},
        "reporter_status_human": {"status": "missing", "summary": "Reporter missing."},
        "operator_conclusion_human": {"summary": "Trade closed.", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "same_day_reporter_linkage": {"status": "missing", "linkage_source": "missing", "linkage_reason": "missing"},
    }

    out = build_trade_story_input(bundle_out, trade_lifecycle=lifecycle)

    assert out["evidence_provenance"]["scanner"] == "canonical"
    assert out["evidence_provenance"]["monitor"] == "canonical"
    assert out["evidence_provenance"]["executor"] == "canonical"
    assert out["section_provenance"]["scanner_reason_human"]["source"] == "canonical"
    assert out["section_provenance"]["monitor_reason_human"]["source"] == "canonical"
    assert out["section_provenance"]["execution_outcome_human"]["source"] == "canonical"
    assert out["report_section_seeds"]["market_context_at_entry"]["summary"] == "Market context was not captured."
    assert out["report_section_seeds"]["strategist_summary"]["summary"] == "Market context was not captured."
    assert out["report_section_seeds"]["why_this_symbol_was_chosen"]["summary"] == "Scanner rationale."
    assert out["report_section_seeds"]["entry_decision"]["summary"] == "Scanner rationale."
    assert out["report_section_seeds"]["holding_monitoring_story"]["summary"] == "Monitor rationale."
    assert out["report_section_seeds"]["exit_decision"]["summary"] == "Execution completed."
    assert out["report_section_seeds"]["scanner_filters"]["summary"] == ""
    assert out["report_section_seeds"]["execution_quality"]["summary"] == "Execution completed."
    assert out["report_section_seeds"]["guard_approval_result"]["summary"] == ""
    assert out["report_section_seeds"]["reporter_evaluation"]["summary"] == "Reporter missing."
    assert out["report_section_seeds"]["final_operator_conclusion"]["summary"] == "Trade closed."
    assert out["section_provenance"]["report_section_provenance_seeds"]["market_context_at_entry"]["source"] == "fallback"
    assert out["section_provenance"]["report_section_provenance_seeds"]["strategist_summary"]["source"] == "fallback"
    assert out["section_provenance"]["report_section_provenance_seeds"]["why_this_symbol_was_chosen"]["source"] == "canonical"
    assert out["section_provenance"]["report_section_provenance_seeds"]["entry_decision"]["source"] == "canonical"
    assert out["section_provenance"]["report_section_provenance_seeds"]["holding_monitoring_story"]["source"] == "canonical"
    assert out["section_provenance"]["report_section_provenance_seeds"]["exit_decision"]["source"] == "canonical"
    assert out["section_provenance"]["report_section_provenance_seeds"]["scanner_filters"]["artifact_path"].endswith("scanner.json")
    assert out["section_provenance"]["report_section_provenance_seeds"]["execution_quality"]["source"] == "canonical"
    assert out["section_provenance"]["report_section_provenance_seeds"]["guard_approval_result"]["source"] == "fallback"
    assert out["section_provenance"]["report_section_provenance_seeds"]["reporter_evaluation"]["source"] == "fallback"
    assert out["section_provenance"]["report_section_provenance_seeds"]["final_operator_conclusion"]["source"] == "canonical"
    assert out["artifacts"]["canonical_scanner_json"].endswith("scanner.json")
    assert out["same_day_reporter_linkage"]["status"] == "missing"


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


def test_trade_story_human_sections_surface_strategist_evidence_selection_trace_and_stop_layers() -> None:
    market = build_market_context_human(
        {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "defensive",
            "news_query_targets": ["KOSPI", "semiconductor"],
            "global_sentiment_signal": {"score": 0.12, "status": "ok"},
            "fear_index": {"vix_level": 18.4},
            "candidate_symbols_hint": ["122630", "233740", "005930"],
            "news_evidence_ranked": {
                "market_news_ranked": [
                    {"title": "KOSPI opens firmer on chip optimism."},
                    {"title": "US futures steady ahead of macro prints."},
                ],
                "candidate_news_ranked": [
                    {"symbol": "005930", "title": "005930 benefits from foreign inflows."},
                    {"symbol": "005930", "title": "Memory leaders extend gains."},
                ],
            },
            "key_events": ["AI demand re-rating"],
        }
    )

    scanner = build_scanner_reason_human(
        {
            "universe_size": 5,
            "selected_symbol": "005930",
            "ranking_table": [
                {"rank": 1, "symbol": "005930", "score_total": 1.15, "risk_score": 0.62, "confidence": 0.81},
                {"rank": 2, "symbol": "000660", "score_total": 1.14, "risk_score": 0.65, "confidence": 0.79},
            ],
            "selected_candidate": {
                "symbol": "005930",
                "sources": ["top_value", "sector_theme"],
                "score_total": 1.15,
                "risk_score": 0.62,
                "confidence": 0.81,
                "score_breakdown": {"trading_value": 0.22, "momentum": 0.19, "trend": 0.17},
            },
        },
        {"playbook": "defensive"},
    )

    monitor = build_monitor_reason_human(
        {
            "entry_evaluated": True,
            "entry_triggered": False,
            "monitor_reason": "reclaim_not_confirmed",
            "hard_stop_pct": 0.03,
            "adaptive_exit": {"stop_loss_pct": 0.0092},
            "trailing_stop_pct": 0.012,
            "take_profit_pct": 0.025,
            "entry_metrics": {
                "volume_ratio": 0.61,
                "extended_from_vwap_pct": 0.03,
                "pullback_depth_pct": 0.004,
            },
            "entry_thresholds": {
                "volume_ratio_min": 0.68,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.008,
            },
            "decision_trace": {
                "entry_check_summary": "mission=wait_for_confirmation | reason=reclaim_not_confirmed",
                "entry_blockers": ["volume_ok", "vwap_reclaim_ok"],
                "policy_ref": {
                    "exit_plan": {
                        "adaptive_exit": {
                            "stop_loss_pct": 0.0081,
                            "take_profit_pct": 0.0175,
                            "trailing_stop_pct": 0.011,
                        }
                    }
                },
            },
        },
        {"action": "NOOP"},
    )

    assert market["candidate_hints"] == ["122630", "233740", "005930"]
    assert market["market_headlines"][0] == "KOSPI opens firmer on chip optimism."
    assert market["symbol_headlines"][0] == "005930 benefits from foreign inflows."
    assert market["strategist_evidence_trace"]["global_sentiment_signal"]["score"] == 0.12
    assert scanner["scanner_selection_trace"]["selected_symbol"] == "005930"
    assert scanner["scanner_selection_trace"]["selection_reason"]
    assert scanner["selected_symbol_score_drivers"]["trading_value"] == 0.22
    assert monitor["monitor_stop_policy_trace"]["hard_stop_pct"] == 0.03
    assert monitor["monitor_stop_policy_trace"]["adaptive_stop_loss_pct"] == 0.0092
    assert monitor["monitor_stop_policy_trace"]["effective_stop_loss_pct"] == 0.0092
    assert monitor["monitor_stop_policy_trace"]["strategist_baseline_stop_loss_pct"] == 0.0081
    assert monitor["monitor_stop_policy_trace"]["strategist_baseline_take_profit_pct"] == 0.0175
    assert "volume ratio 0.61 below min 0.68" in monitor["threshold_shortfalls"][0]
    assert monitor["monitor_blocker_trace"]["entry_blockers"] == ["volume_ok", "vwap_reclaim_ok"]


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


def test_enrich_scanner_reason_from_evidence_prefers_reported_feature_coverage_and_updates_reason() -> None:
    out = enrich_scanner_reason_from_evidence(
        {
            "selected_symbol": "005930",
            "selection_reason": "highest score; chart feature coverage 6/12",
            "top_reasons": ["highest combined scanner score (1.173)", "chart feature coverage 6/12"],
            "bullets": ["Chart / feature coverage: 6/12"],
            "scanner_selection_trace": {"selected_symbol": "005930"},
        },
        {
            "candidate_ranking_tables": [
                {
                    "payload": {
                        "rows": [
                            {
                                "symbol": "005930",
                                "feature_coverage": {
                                    "present": 12,
                                    "total": 13,
                                    "coverage_ratio": 12.0 / 13.0,
                                    "quality": "strong",
                                },
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

    assert out["feature_coverage"]["present"] == 12
    assert out["feature_coverage"]["total"] == 13
    assert out["feature_coverage"]["source"] == "feature_coverage_reported"
    assert out["selection_reason"] == "highest score; chart feature coverage 12/13"
    assert out["top_reasons"][1] == "chart feature coverage 12/13"
    assert any("Chart / feature coverage: 12/13" == row for row in out["bullets"])
    assert any(str(row).startswith("Chart features present:") for row in out["bullets"])
    assert any(str(row).startswith("Chart features missing:") for row in out["bullets"])
    trace = out["scanner_selection_trace"]
    assert trace["chart_feature_coverage"]["present"] == 12
    assert trace["chart_feature_coverage"]["total"] == 13


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
        "strategist": {
            "news_query_targets": ["shipping", "KOSPI"],
            "candidate_symbols_hint": ["003280", "000660"],
            "candidate_hypotheses": [
                {"symbol": "003280", "hypothesis": "shipping momentum candidate"},
                {"symbol": "000660", "hypothesis": "large-cap ballast candidate"},
            ],
            "news_evidence_ranked": {
                "market_news_ranked": [{"title": "Shipping names stay active in early trade."}],
                "candidate_news_ranked": [{"symbol": "003280", "title": "003280 extends shipping-theme momentum."}],
            },
        },
        "scanner_summary": {
            "selected_symbol": "003280",
            "runner_up_symbol": "000660",
            "selection_summary": "003280 ranked first with better liquidity.",
        },
        "scanner": {
            "selected_symbol": "003280",
            "top_ranked_symbols": ["003280", "000660"],
            "candidate_ranking_table": {
                "rows": [
                    {"symbol": "003280", "rank": 1, "score_total": 1.18},
                    {"symbol": "000660", "rank": 2, "score_total": 1.11},
                ]
            },
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
    assert story_input["news_symbol_linkage"]["selected_symbol"] == "003280"
    assert story_input["news_symbol_linkage"]["runner_up_symbol"] == "000660"
    assert story_input["news_symbol_linkage"]["selected_symbol_in_candidate_hints"] is True
    assert story_input["news_symbol_linkage"]["runner_up_symbol_in_candidate_hints"] is True
    assert story_input["market_context_human"]["news_symbol_linkage"]["linkage_strength"] == "strong"
    assert "runner-up 000660" in story_input["news_symbol_linkage"]["selected_vs_runner_up"]["comparison_summary"]
    assert story_input["strategist_feedback_input"]["selected_symbol"] == "003280"
    assert story_input["strategist_feedback_input"]["candidate_symbols_hint"] == ["003280", "000660"]
    assert "runner-up 000660" in story_input["strategist_feedback_input"]["selected_vs_runner_up_summary"]
    assert story_input["strategist_feedback_input"]["entry_pattern_type"] == "unknown"
    assert story_input["strategist_feedback_input"]["entry_confirmation_quality"] == "unknown"
    assert story_input["strategist_feedback_input"]["exit_pattern_type"] == "unknown"
    assert story_input["strategist_feedback_input"]["improvement_tags"] == []

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
    assert lifecycle_bundle["news_symbol_linkage"]["selected_symbol"] == "003280"
    assert lifecycle_bundle["news_symbol_linkage"]["runner_up_symbol"] == "000660"
    assert lifecycle_bundle["strategist_feedback_input"]["selected_symbol"] == "003280"
    assert "runner-up 000660" in lifecycle_bundle["strategist_feedback_input"]["selected_vs_runner_up_summary"]
    assert lifecycle_bundle["strategist_feedback_input"] == story_input["strategist_feedback_input"]


def test_trade_story_input_replaces_empty_placeholder_traces_with_normalized_values() -> None:
    bundle_out = {
        "day": "2026-03-24",
        "run_id": "run-placeholder-1",
        "trade_id": "TRD_TEST_PLACEHOLDER",
        "story_id": "TRD_TEST_PLACEHOLDER",
        "scanner_reason_human": {
            "summary": "scanner summary",
            "scanner_selection_trace": {
                "ranked_candidates": [],
                "selected_symbol": "",
                "selected_rank": 0,
                "selection_reason": "",
                "selected_symbol_score_drivers": {},
            },
            "ranked_candidates": [],
        },
        "monitor_reason_human": {
            "summary": "monitor summary",
            "monitor_stop_policy_trace": {
                "hard_stop_pct": None,
                "adaptive_stop_loss_pct": None,
                "effective_stop_loss_pct": None,
                "trailing_stop_pct": None,
                "take_profit_pct": None,
            },
            "monitor_blocker_trace": {},
        },
        "scanner_summary": {"selected_symbol": "005930"},
        "monitor_summary": {"decision": "WAIT"},
        "canonical_agent_artifacts": {
            "strategist": {
                "themes": ["semiconductor"],
                "news_query_targets": ["KOSPI", "US indices"],
                "news_evidence_ranked": {
                    "market_news_ranked": [{"title": "KOSPI advanced as institutions bought semiconductors."}],
                    "candidate_news_ranked": [{"symbol": "005930", "title": "005930 gained after semiconductor demand outlook improved."}],
                },
            },
            "scanner": {
                "selected_symbol": "005930",
                "top_stock": "005930",
                "selected_candidate": {
                    "symbol": "005930",
                    "sources": ["top_value", "sector_theme"],
                    "score_total": 1.12,
                    "score_breakdown": {
                        "trading_value": 0.22,
                        "momentum": 0.14,
                        "trend": 0.13,
                        "theme_boost": 0.05,
                        "sentiment": 0.02,
                    },
                    "component_snapshot": {
                        "news_sentiment": 0.04,
                        "global_sentiment": 0.08,
                        "sentiment_component": 0.052,
                    },
                },
                "candidate_ranking_table": {
                    "rows": [
                        {"symbol": "005930", "rank": 1, "score_total": 1.12},
                        {"symbol": "000660", "rank": 2, "score_total": 1.04},
                    ]
                },
            },
            "monitor": {
                "threshold_snapshot": {
                    "hard_stop_pct": 0.03,
                    "stop_loss_pct": 0.0092,
                    "effective_stop_loss_pct": 0.0092,
                    "trailing_stop_pct": 0.014,
                    "take_profit_pct": 0.0175,
                }
            },
        },
    }

    story_input = build_trade_story_input(bundle_out)

    scanner_trace = story_input["scanner_reason_human"]["scanner_selection_trace"]
    monitor_trace = story_input["monitor_reason_human"]["monitor_stop_policy_trace"]

    assert scanner_trace["selected_symbol"] == "005930"
    assert len(scanner_trace["ranked_candidates"]) == 2
    assert len(story_input["scanner_reason_human"]["ranked_candidates"]) == 2
    assert story_input["scanner_reason_human"]["news_scanner_contribution"]["core_score_contributions"]["theme_boost"]["value"] == 0.05
    assert scanner_trace["news_scanner_contribution"]["sentiment_inputs"]["weighted_sentiment_score_contribution"] == 0.02
    assert any(
        row.startswith("Core score contributions:")
        for row in list(story_input["scanner_reason_human"].get("bullets") or [])
    )
    assert monitor_trace["hard_stop_pct"] == 0.03
    assert monitor_trace["effective_stop_loss_pct"] == 0.0092


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


def test_trade_story_input_prefers_authoritative_open_status_over_placeholder_exit() -> None:
    out = build_trade_story_input(
        {
            "day": "2026-04-16",
            "run_id": "run-buy",
            "trade_id": "TRD_TEST_OPEN",
            "trade_lifecycle_status": "open",
            "execution": {"symbol": "000660", "action": "BUY"},
            "trade_lifecycle": {
                "trade_id": "TRD_TEST_OPEN",
                "symbol": "000660",
                "status": "closed",
                "entry": {
                    "run_id": "run-buy",
                    "ts": "2026-04-16T00:07:45+00:00",
                    "action": "BUY",
                    "reason_human": "selected",
                    "scanner_context": {"selected_symbol": "000660"},
                },
                "holding": {
                    "hold_duration": "1.1m",
                    "hold_duration_sec": 66,
                },
                "exit": {
                    "action": "SELL",
                    "execution_details": {
                        "order_status": None,
                        "order_id": None,
                        "execution_mode": None,
                        "broker_env": None,
                        "filled_qty": None,
                        "avg_price": None,
                    },
                },
            },
            "market_context_human": {"summary": "Market context"},
            "scanner_reason_human": {"summary": "Scanner summary", "selected_symbol": "000660"},
            "monitor_reason_human": {"summary": "Monitor summary"},
            "operator_conclusion_human": {"summary": "Operator conclusion"},
            "execution_outcome_human": {"summary": "Execution was not attempted."},
            "guard_reason_human": {"summary": "No guard escalation."},
            "reporter_status_human": {"summary": "Reporter ready."},
        }
    )

    assert out["status"] == "open"
    assert out["action"] == "HOLD"


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
