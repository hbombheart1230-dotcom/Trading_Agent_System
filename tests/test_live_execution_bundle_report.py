from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

from libs.reporting.intraday_trade_reports import (
    apply_live_bundle_backfill as shared_apply_live_bundle_backfill,
    apply_ai_trade_report_generation_result as shared_apply_ai_trade_report_generation_result,
    apply_runtime_diagnostics_context as shared_apply_runtime_diagnostics_context,
    base_report_diagnostics as shared_base_report_diagnostics,
    build_live_bundle_backfill_payload as shared_build_live_bundle_backfill_payload,
    build_live_execution_summary_payload as shared_build_live_execution_summary_payload,
    build_live_generation_state_payload as shared_build_live_generation_state_payload,
    build_holding_phase_observability as shared_build_holding_phase_observability,
    build_same_day_reporter_linkage as shared_build_same_day_reporter_linkage,
    execute_ai_trade_report_generation as shared_execute_ai_trade_report_generation,
    load_report_generation_state as shared_load_report_generation_state,
    plan_live_trade_report_generation as shared_plan_live_trade_report_generation,
    persist_live_story_input_artifacts as shared_persist_live_story_input_artifacts,
    report_next_step as shared_report_next_step,
    report_reason_human as shared_report_reason_human,
    report_generation_state_path as shared_report_generation_state_path,
    resolve_trade_report_policy as shared_resolve_trade_report_policy,
    seed_diagnostics_for_policy as shared_seed_diagnostics_for_policy,
    write_report_generation_state as shared_write_report_generation_state,
)
from libs.reporting.trade_bundle_assembly import (
    hydrate_live_run_bundle_context as shared_hydrate_live_run_bundle_context,
    build_live_run_bundle as shared_build_live_run_bundle,
    apply_final_trade_report_context as shared_apply_final_trade_report_context,
    apply_entry_exit_holding_enrichment as shared_apply_entry_exit_holding_enrichment,
    apply_trace_summary_context as shared_apply_trace_summary_context,
    apply_live_trade_context as shared_apply_live_trade_context,
    apply_strategy_anchor_metadata as shared_apply_strategy_anchor_metadata,
    attach_strategy_anchor as shared_attach_strategy_anchor,
    build_scanner_trace_summary_mirror as shared_build_scanner_trace_summary_mirror,
    build_execution_details_from_bundle as shared_build_execution_details_from_bundle,
    build_strategist_trace_summary_mirror as shared_build_strategist_trace_summary_mirror,
    preferred_run_ids_for_agent as shared_preferred_run_ids_for_agent,
    resolve_lifecycle_bundle_sources as shared_resolve_lifecycle_bundle_sources,
)
from libs.reporting.trade_bundle_persistence import (
    persist_trade_report_outputs as shared_persist_trade_report_outputs,
    refresh_trade_report_outputs_if_written as shared_refresh_trade_report_outputs_if_written,
    persist_trade_llm_artifacts as shared_persist_trade_llm_artifacts,
    persist_trade_bundle_outputs as shared_persist_trade_bundle_outputs,
)
from libs.reporting.trade_bundle_state import (
    build_live_trade_bundle_payloads as shared_build_live_trade_bundle_payloads,
)
import libs.reporting.live_execution_bundle_runner as runner_mod
import libs.reporting.trade_story_pipeline as story_pipeline
import scripts.run_live_execution_bundle_report as mod
from libs.reporting.trade_report_ai import build_deterministic_trade_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_live_execution_bundle_report_reuses_intraday_generation_state_helpers() -> None:
    assert mod.apply_ai_trade_report_generation_result is shared_apply_ai_trade_report_generation_result
    assert mod.apply_runtime_diagnostics_context is shared_apply_runtime_diagnostics_context
    assert mod.build_live_bundle_backfill_payload is shared_build_live_bundle_backfill_payload
    assert mod.build_live_execution_summary_payload is shared_build_live_execution_summary_payload
    assert mod.build_live_generation_state_payload is shared_build_live_generation_state_payload
    assert mod.execute_ai_trade_report_generation is shared_execute_ai_trade_report_generation
    assert mod.plan_live_trade_report_generation is shared_plan_live_trade_report_generation
    assert mod._base_diagnostics is shared_base_report_diagnostics
    assert mod._report_reason_human is shared_report_reason_human
    assert mod._report_next_step is shared_report_next_step
    assert mod._resolve_trade_report_policy is shared_resolve_trade_report_policy
    assert mod.persist_live_story_input_artifacts is shared_persist_live_story_input_artifacts
    assert mod.apply_live_bundle_backfill is shared_apply_live_bundle_backfill
    assert mod._report_generation_state_path is shared_report_generation_state_path
    assert mod._load_report_generation_state is shared_load_report_generation_state
    assert mod._write_report_generation_state is shared_write_report_generation_state

    diagnostics, should_attempt = mod._seed_diagnostics_for_policy(
        lifecycle_status="open",
        story_type="simulation",
        report_requested=True,
        story_input_available=True,
        model_hint="openrouter/test",
        generate_on_open=False,
    )
    assert should_attempt is False
    assert diagnostics["report_reason_code"] == "awaiting_exit_for_full_report"


def test_live_execution_bundle_report_reuses_intraday_linkage_and_hold_helpers() -> None:
    assert mod._build_same_day_reporter_linkage is shared_build_same_day_reporter_linkage
    assert mod._build_holding_phase_observability is shared_build_holding_phase_observability


def test_live_execution_bundle_report_reuses_trade_bundle_persistence_helper() -> None:
    assert mod.persist_trade_report_outputs is shared_persist_trade_report_outputs
    assert mod.refresh_trade_report_outputs_if_written is shared_refresh_trade_report_outputs_if_written
    assert mod.persist_trade_llm_artifacts is shared_persist_trade_llm_artifacts
    assert mod.persist_trade_bundle_outputs is shared_persist_trade_bundle_outputs


def test_live_execution_bundle_report_reuses_trade_bundle_state_helper() -> None:
    assert mod.build_live_trade_bundle_payloads is shared_build_live_trade_bundle_payloads


def test_runtime_minute_rows_for_symbol_reads_persisted_post_exit_cache() -> None:
    rows = [
        {"ts": 1777529700, "close": 56600.0, "raw_ts": "20260430151500"},
        {"ts": 1777530000, "close": 56700.0, "raw_ts": "20260430152000"},
    ]
    state = {
        "persisted_state": {
            "recent_minute_ohlcv_by_symbol": {
                "001440": {
                    "symbol": "001440",
                    "rows": rows,
                    "latest_candle_ts": 1777530000,
                }
            }
        }
    }

    assert runner_mod._runtime_minute_rows_for_symbol(state, "001440") == rows


def test_runtime_minute_rows_for_symbol_prefers_freshest_source() -> None:
    stale_rows = [{"ts": 100, "close": 10.0}]
    fresh_rows = [{"ts": 100, "close": 10.0}, {"ts": 220, "close": 11.0}]
    state = {
        "recent_minute_ohlcv_by_symbol": {"005930": {"rows": stale_rows}},
        "skill_results": {
            "market.minute_ohlcv_by_symbol": {
                "005930": {
                    "result": {
                        "action": "ready",
                        "data": {
                            "symbol": "005930",
                            "rows": fresh_rows,
                        },
                    }
                }
            }
        },
    }

    assert runner_mod._runtime_minute_rows_for_symbol(state, "005930") == fresh_rows


def test_live_execution_bundle_event_logger_accepts_level(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class DummyLogger:
        def log(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)

    monkeypatch.setattr(runner_mod, "_make_bundle_event_logger", lambda _path: DummyLogger())

    runner_mod._log_bundle_event(
        tmp_path / "events.jsonl",
        role="intraday_trade_report_bundle",
        event="operator_summary_refresh_finished",
        level="warning",
        run_id="run-1",
        symbol="005930",
    )

    assert captured["level"] == "warning"
    assert captured["event"] == "operator_summary_refresh_finished"


def test_live_execution_bundle_report_reuses_trade_bundle_assembly_helpers() -> None:
    assert mod.apply_final_trade_report_context is shared_apply_final_trade_report_context
    assert mod.hydrate_live_run_bundle_context is shared_hydrate_live_run_bundle_context
    assert mod.build_live_run_bundle is shared_build_live_run_bundle
    assert mod.apply_entry_exit_holding_enrichment is shared_apply_entry_exit_holding_enrichment
    assert mod.apply_live_trade_context is shared_apply_live_trade_context
    assert mod._build_execution_details_from_bundle is shared_build_execution_details_from_bundle
    assert mod._attach_strategy_anchor is shared_attach_strategy_anchor
    assert mod._build_strategist_trace_summary_mirror is shared_build_strategist_trace_summary_mirror
    assert mod._build_scanner_trace_summary_mirror is shared_build_scanner_trace_summary_mirror
    assert mod.apply_trace_summary_context is shared_apply_trace_summary_context
    assert mod._preferred_run_ids_for_agent is shared_preferred_run_ids_for_agent
    assert mod._resolve_lifecycle_bundle_sources is shared_resolve_lifecycle_bundle_sources
    assert mod.apply_strategy_anchor_metadata is shared_apply_strategy_anchor_metadata


def test_live_execution_bundle_report_exposes_inprocess_runner() -> None:
    assert callable(mod.run_live_execution_bundle_inprocess)


def test_live_execution_bundle_report_delegates_main_to_lib_runner() -> None:
    assert mod.main.__module__ == "libs.reporting.live_execution_bundle_runner"
    assert mod.run_live_execution_bundle_inprocess.__module__ == "libs.reporting.live_execution_bundle_runner"


def test_live_execution_bundle_report_background_job_paths_default_to_repo_root(monkeypatch) -> None:
    monkeypatch.delenv("INTRADAY_TRADE_REPORT_JOB_LOCK_PATH", raising=False)
    assert mod._background_job_lock_path() == mod.ROOT / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    assert mod._background_job_queue_path() == mod.ROOT / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"


def test_live_execution_bundle_report_spawn_followup_uses_script_wrapper_and_repo_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class DummyProc:
        pid = 42424

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = list(cmd)
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = dict(kwargs.get("env") or {})
        return DummyProc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    args = SimpleNamespace(
        env_path=".env",
        event_log_path=tmp_path / "events.jsonl",
        evidence_log_path=tmp_path / "evidence.jsonl",
        report_dir=tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles",
        reports_root=tmp_path / "reports",
        intents_path=None,
        day="2026-04-21",
        trade_report_ai=True,
        trade_report_ai_model="openrouter/test",
        trade_report_ai_temperature=None,
        trade_report_ai_max_tokens=None,
        json=True,
    )

    out = mod._spawn_followup_background_job(
        {"target_run_id": "run-2", "target_symbol": "005930"},
        args=args,
        role="intraday_trade_report_bundle",
        event_log_path=tmp_path / "events.jsonl",
    )

    assert out["pid"] == 42424
    cmd = list(captured["cmd"])
    assert cmd[0].endswith("python.exe") or cmd[0].endswith("python")
    assert cmd[1] == str(mod.ROOT / "scripts" / "run_live_execution_bundle_report.py")
    assert captured["cwd"] == str(mod.ROOT)
    assert captured["env"]["INTRADAY_TRADE_REPORT_PARENT_SPAWN"] == "1"


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


def _fake_ai_trade_report_raise(*args, **kwargs):  # type: ignore[no-untyped-def]
    raise RuntimeError("synthetic_ai_trade_report_failure")


def test_flatten_news_titles_handles_count_sample_mapping_with_string_rows() -> None:
    sample = {
        "KOSPI": {
            "count": 5,
            "sample": [
                "NewsItem(title='KOSPI rebounds on tech strength', url='https://example.com/1')",
                "NewsItem(title='Foreign and institutional selling eases', url='https://example.com/2')",
            ],
        },
        "000660": {
            "count": 3,
            "sample": [
                "NewsItem(title='SK hynix volatility expands ahead of earnings', url='https://example.com/3')",
            ],
        },
    }

    titles = mod._flatten_news_titles(sample, max_groups=2, max_titles_per_group=2)

    assert titles == [
        "KOSPI: KOSPI rebounds on tech strength",
        "KOSPI: Foreign and institutional selling eases",
        "000660: SK hynix volatility expands ahead of earnings",
    ]


def test_flatten_news_titles_keeps_later_candidate_groups_by_default() -> None:
    sample = {
        f"{idx:06d}": {
            "count": 1,
            "sample": [f"NewsItem(title='candidate {idx}', url='https://example.com/{idx}')"],
        }
        for idx in range(1, 7)
    }

    titles = mod._flatten_news_titles(sample, max_titles_per_group=1)

    assert "000006: candidate 6" in titles


def test_strategist_evidence_trace_filters_fallback_candidate_news_to_selected_symbol() -> None:
    trace = story_pipeline._build_strategist_evidence_trace(
        {},
        selected_symbol="098460",
        fallback_candidate_titles=[
            "006340: unrelated disclosure",
            "098460: selected symbol earnings surprise",
        ],
    )
    missing_trace = story_pipeline._build_strategist_evidence_trace(
        {},
        selected_symbol="098460",
        fallback_candidate_titles=["006340: unrelated disclosure"],
    )

    assert trace["symbol_headlines"] == ["098460: selected symbol earnings surprise"]
    assert missing_trace["symbol_headlines"] == []


def test_strategist_evidence_trace_prefers_direct_symbol_title_over_indirect_theme_title() -> None:
    trace = story_pipeline._build_strategist_evidence_trace(
        {
            "news_evidence_ranked": [
                {
                    "payload": {
                        "candidate_news_ranked": [
                            {
                                "target": "006340",
                                "sample_titles": [
                                    "NewsItem(title='LS일렉, 美 데이터센터 3200억 수주 5%↑…전력주 강세[핫종목]', url='https://example.com/a', source='naver', published_at='Wed, 29 Apr 2026 10:04:00 +0900', symbol='006340', summary='HD현대일렉트릭 등을 비롯해 대원전선(<b>006340</b>)(21.85%) 등 다른 전력 관련 종목들도 동반 강세다.', raw=None)",
                                    "NewsItem(title='대원전선 주가 장초반 급등세…19%↑', url='https://example.com/b', source='naver', published_at='Wed, 29 Apr 2026 09:24:00 +0900', symbol='006340', summary='대원전선(<b>006340</b>) 주가가 장초반 급등세를 보이고 있다.', raw=None)",
                                ],
                            }
                        ]
                    }
                }
            ]
        },
        selected_symbol="006340",
    )

    assert trace["symbol_headlines"] == ["006340: 대원전선 주가 장초반 급등세…19%↑"]
    assert "LS일렉" not in " ".join(trace["symbol_headlines"])


def test_trade_story_rebuild_overrides_stale_candidate_news_with_raw_symbol_evidence() -> None:
    raw_news = [
        {
            "payload": {
                "candidate_news_ranked": [
                    {
                        "target": "006340",
                        "sample_titles": [
                            "NewsItem(title='LS일렉, 美 데이터센터 3200억 수주 5%↑…전력주 강세[핫종목]', symbol='006340', summary='대원전선(<b>006340</b>) 등 다른 전력 관련 종목들도 동반 강세다.')",
                            "NewsItem(title='대원전선 주가 장초반 급등세…19%↑', symbol='006340', summary='대원전선(<b>006340</b>) 주가가 장초반 급등세를 보이고 있다.')",
                        ],
                    }
                ]
            }
        }
    ]
    story = story_pipeline.build_trade_story_input_from_bundle(
        {
            "day": "2026-04-29",
            "trade_id": "TRD_20260429_006340_01",
            "execution": {"symbol": "006340", "action": "BUY"},
            "trade_lifecycle": {
                "symbol": "006340",
                "status": "open",
                "entry": {"action": "BUY"},
                "holding": {},
                "exit": {},
                "summary": {},
                "reporter": {},
            },
            "market_context_human": {
                "regime": "neutral",
                "market_sentiment": "neutral",
                "playbook": "defensive",
                "candidate_news_titles": ["006340: LS일렉, 美 데이터센터 3200억 수주 5%↑…전력주 강세[핫종목]"],
            },
            "scanner_reason_human": {"selected_symbol": "006340"},
            "strategist": {"playbook": "defensive", "news_query_targets": ["KOSPI"]},
            "strategist_evidence": {"news_evidence_ranked": raw_news},
        }
    )

    assert story["market_context_human"]["candidate_news_titles"] == ["006340: 대원전선 주가 장초반 급등세…19%↑"]
    report = build_deterministic_trade_report(story)
    market_bullets = " ".join(report["market_context_at_entry"]["bullets"])

    assert "대원전선 주가 장초반 급등세" in market_bullets
    assert "LS일렉" not in market_bullets


def test_build_strategist_input_summary_surfaces_news_titles_from_sample_mapping() -> None:
    source_input = {
        "market_regime_hint": "neutral",
        "market_sentiment_hint": "neutral",
        "playbook_hint": "defensive",
        "news_query_targets": ["KOSPI", "US equities"],
        "market_news_sample": {
            "KOSPI": {
                "count": 5,
                "sample": [
                    "NewsItem(title='KOSPI rebounds on tech strength', url='https://example.com/1')",
                ],
            }
        },
        "candidate_news_sample": {
            "000660": {
                "count": 3,
                "sample": [
                    "NewsItem(title='SK hynix volatility expands ahead of earnings', url='https://example.com/2')",
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

    assert summary["market_regime_hint"] == "neutral"
    assert summary["market_sentiment_hint"] == "neutral"
    assert summary["playbook_hint"] == "defensive"
    assert summary["market_news_titles"] == ["KOSPI: KOSPI rebounds on tech strength"]
    assert summary["candidate_news_titles"] == ["000660: SK hynix volatility expands ahead of earnings"]


def test_enrich_strategist_from_input_summary_recovers_cached_strategy_hints() -> None:
    strategist_payload = {}
    strategist_input_artifact = {
        "summary": {
            "market_regime_hint": "neutral",
            "market_sentiment_hint": "neutral",
            "playbook_hint": "defensive",
            "themes_hint": ["broad_market_leaders"],
            "global_sentiment_score": 0.02,
            "vix_level": 17.94,
            "vix_change_pct": -1.26,
            "vix_level_pressure": 0.0,
            "headline_count": 60,
            "market_signal_total": 7,
            "candidate_signal_total": 5,
            "news_query_targets": ["KOSPI", "미국 증시"],
        }
    }

    enriched = mod._enrich_strategist_from_input_summary(strategist_payload, strategist_input_artifact)

    assert enriched["market_regime"] == "neutral"
    assert enriched["market_sentiment"] == "neutral"
    assert enriched["playbook"] == "defensive"
    assert enriched["themes"] == ["broad_market_leaders"]
    assert enriched["global_sentiment_score"] == 0.02
    assert enriched["fear_index"]["level"] == 17.94
    assert enriched["news_context"]["headline_count"] == 60


def test_live_execution_bundle_report_logs_ai_generation_start_and_finish_events(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "BUY", "symbol": "000660", "qty": 1},
                    "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}},
                },
            },
            {
                "run_id": "run-2",
                "ts": f"{day}T00:10:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "SELL", "symbol": "000660", "qty": 1},
                    "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}},
                },
            },
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(runner_mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(runner_mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(runner_mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(runner_mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr(
        runner_mod,
        "plan_live_trade_report_generation",
        lambda **kwargs: {
            "mode": "generate_ai",
            "diagnostics": dict(kwargs.get("diagnostics") or {}),
            "trade_report": dict(kwargs.get("deterministic_report") or {}),
            "ai_trade_report_llm_artifact": {},
            "log_events": [],
        },
    )
    monkeypatch.setattr(
        runner_mod,
        "execute_ai_trade_report_generation",
        lambda **kwargs: {
            "diagnostics": {
                **dict(kwargs.get("diagnostics") or {}),
                "ai_trade_report_status": "ok",
                "report_status": "available",
                "report_reason_code": "ai_generated",
                "report_generation_reason": "ai_trade_report_generated",
                "llm_model_used": "openrouter/test",
            },
            "trade_report": _fake_ai_trade_report_ok(dict(kwargs.get("trade_story_input") or {})),
            "ai_trade_report_llm_artifact": {
                "status": "ok",
                "llm_status": "ok",
                "meta": {"reason": "live_ai_ok"},
            },
        },
    )

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
            "--trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    rows = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    started = [row for row in rows if row.get("event") == "ai_trade_report_generation_started"]
    finished = [row for row in rows if row.get("event") == "ai_trade_report_generation_finished"]
    assert started
    assert finished
    assert started[-1]["payload"]["component"] == "ai_trade_report"
    assert finished[-1]["payload"]["component"] == "ai_trade_report"
    assert finished[-1]["payload"]["llm_status"] in {"ok", "fallback"}



def test_live_execution_bundle_report_falls_back_to_deterministic_when_ai_generation_raises(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "BUY", "symbol": "000660", "qty": 1},
                    "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}},
                },
            },
            {
                "run_id": "run-2",
                "ts": f"{day}T00:10:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "order": {"action": "SELL", "symbol": "000660", "qty": 1},
                    "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}},
                },
            },
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(runner_mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(runner_mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(runner_mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(runner_mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr(runner_mod, "execute_ai_trade_report_generation", _fake_ai_trade_report_raise)

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
            "--trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    lifecycle = out["bundles"][0]
    trade_id = str(lifecycle["trade_id"])
    trade_dir = reports_root / "trades" / day / trade_id

    assert (trade_dir / "ai_trade_report_input.json").exists()
    assert (trade_dir / "lifecycle_bundle.json").exists()
    assert (trade_dir / "reports" / "ai_trade_report.json").exists()
    assert (trade_dir / "reports" / "ai_trade_report.md").exists()
    assert (trade_dir / "reports" / "ai_trade_report_llm_response.json").exists()

    lifecycle_bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    diagnostics = dict(lifecycle_bundle.get("ai_report_diagnostics") or {})
    assert diagnostics["report_reason_code"] == "llm_generation_failed"
    assert diagnostics["ai_trade_report_status"] == "error"
    assert diagnostics["report_status"] == "available"
    assert "synthetic_ai_trade_report_failure" in str(diagnostics.get("last_error_message") or "")

    llm_response = json.loads(
        (trade_dir / "reports" / "ai_trade_report_llm_response.json").read_text(encoding="utf-8")
    )
    assert llm_response["status"] == "error"
    assert llm_response["meta"]["reason_code"] == "llm_generation_failed"
    assert "synthetic_ai_trade_report_failure" in str(llm_response["meta"]["reason"])

    rows = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    started = [row for row in rows if row.get("event") == "ai_trade_report_generation_started"]
    finished = [row for row in rows if row.get("event") == "ai_trade_report_generation_finished"]
    assert started
    assert finished
    assert finished[-1]["payload"]["llm_status"] == "error"
    assert "synthetic_ai_trade_report_failure" in str(finished[-1]["payload"]["llm_reason"])


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


def test_build_filters_human_surfaces_spread_bps_when_selected_candidate_captures_quote_snapshot() -> None:
    scanner = {
        "selected_candidate": {
            "symbol": "005930",
            "sources": ["top_value", "sector_theme"],
            "risk_score": 0.31,
            "score_breakdown": {"volume_surge": 0.14, "theme_boost": 0.05},
            "component_snapshot": {"trading_value_component": 1.0, "sentiment_component": 0.03},
            "feature_snapshot": {"quote_spread_bps": 7.1},
        },
    }
    strategist = {"themes": ["defensive_large_cap"], "global_sentiment_score": 0.02}
    supervisor = {"supervisor_allow": True}

    out = story_pipeline.build_filters_human(scanner, strategist, supervisor)

    spread_row = next(row for row in out["checks"] if row["name"] == "spread/slippage filter")
    assert spread_row["status"] == "PASS"
    assert "7.1 bps" in spread_row["detail"]


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
    enriched_filters = mod._enrich_filters_from_evidence(
        filters_human,
        scanner_evidence,
        selected_symbol="005930",
        monitor_evidence={"cycle_summaries": [{"price_anomaly_flag": False, "price_anomaly_reason": ""}]},
    )

    assert "chart feature coverage 10/13" in enriched_reason["top_reasons"]
    assert "Chart / feature coverage: 10/13" in enriched_reason["bullets"]
    assert "10/13 captured features" in enriched_filters["summary"]
    assert "strong" in enriched_filters["summary"]
    assert "chart completeness filter: PASS - 10/13 captured chart features" in enriched_filters["bullets"]
    assert any(row["name"] == "price anomaly filter" and row["status"] == "PASS" for row in enriched_filters["checks"])
    assert any("price anomaly filter: PASS - monitor price cross-check found no anomaly" == bullet for bullet in enriched_filters["bullets"])


def test_enrich_filters_from_evidence_falls_back_to_execution_spread_snapshot() -> None:
    filters_human = {
        "checks": [
            {
                "name": "spread/slippage filter",
                "status": "NOT_AVAILABLE",
                "detail": "spread or slippage diagnostics were not captured in this run",
            }
        ],
        "bullets": ["spread/slippage filter: NOT_AVAILABLE - spread or slippage diagnostics were not captured in this run"],
    }

    enriched_filters = mod._enrich_filters_from_evidence(
        filters_human,
        {},
        selected_symbol="005930",
        entry_execution_details={
            "quote_snapshot": {"best_bid": 70500.0, "best_ask": 70550.0, "spread_bps": 7.1},
            "spread_bps": 7.1,
        },
    )

    assert any(row["name"] == "spread/slippage filter" and row["status"] == "PASS" for row in enriched_filters["checks"])
    assert any("spread/slippage filter: PASS - execution quote snapshot spread was 7.1 bps" == bullet for bullet in enriched_filters["bullets"])

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

    trade_root = reports_root / "trades" / day / lifecycle_row["trade_id"]
    assert (trade_root / "lifecycle_bundle.json").exists()
    assert (trade_root / "entry.json").exists()
    assert (trade_root / "hold.json").exists()
    assert (trade_root / "exit.json").exists()
    assert (trade_root / "ai_trade_report_input.json").exists()
    assert (trade_root / "ai_trade_report_compact_input.json").exists()
    assert (trade_root / "reports" / "ai_trade_report.json").exists()
    assert (trade_root / "reports" / "ai_trade_report.md").exists()
    assert (trade_root / "reports" / "ai_trade_report_llm_response.json").exists()
    assert (trade_root / "reports" / "strategist_llm_response.json").exists()
    assert (trade_root / "evidence" / "strategist_evidence.json").exists()
    assert (trade_root / "evidence" / "scanner_evidence.json").exists()
    assert (trade_root / "evidence" / "monitor_evidence.json").exists()
    assert (trade_root / "evidence" / "commander_evidence.json").exists()
    # Phase 3: no forward duplication into legacy trade paths.
    assert (trade_root / "lifecycle" / "trade_lifecycle.json").exists() is False
    assert (trade_root / "lifecycle" / "aggregated_execution_bundle.json").exists() is False
    assert (trade_root / "ai_trade_report" / "ai_trade_report.json").exists() is False

    trade_lifecycle = json.loads((trade_root / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    assert trade_lifecycle["trade_lifecycle_status"] == "closed"
    assert trade_lifecycle["lifecycle"]["entry"]["run_id"] == "run-1"
    assert trade_lifecycle["lifecycle"]["exit"]["run_id"] == "run-2"
    assert any(str(item.get("run_id") or "") == "run-3" for item in list(trade_lifecycle["lifecycle"]["hold"] or []))
    assert trade_lifecycle["trade_outcome"]["holding_time"]
    assert float((trade_lifecycle.get("evidence_summary") or {}).get("completeness_score") or 0.0) >= 0.0

    story_input = json.loads((trade_root / "ai_trade_report_input.json").read_text(encoding="utf-8"))
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
    assert story_input["monitor_reason_human"]["active_exit_axis"] in {"Hold", "No Position"}
    assert "Hard stop" in story_input["monitor_reason_human"]["watch_axes"]
    assert story_input["strategist_evidence"]["market_context_snapshots"][0]["event_name"] == "strategist.market_context_snapshot"
    assert story_input["scanner_evidence"]["candidate_ranking_tables"][0]["payload"]["rows"][0]["symbol"] == "000660"
    threshold_rows = list((story_input.get("monitor_timeline") or {}).get("threshold_snapshots") or [])
    if threshold_rows:
        assert threshold_rows[0]["payload"]["active_exit_axis"] == "Hold"

    trade_report = json.loads((trade_root / "reports" / "ai_trade_report.json").read_text(encoding="utf-8"))
    llm_response = json.loads((trade_root / "reports" / "ai_trade_report_llm_response.json").read_text(encoding="utf-8"))
    strategist_llm = json.loads((trade_root / "reports" / "strategist_llm_response.json").read_text(encoding="utf-8"))
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
    strategist_evidence = json.loads((trade_root / "evidence" / "strategist_evidence.json").read_text(encoding="utf-8"))
    scanner_evidence = json.loads((trade_root / "evidence" / "scanner_evidence.json").read_text(encoding="utf-8"))
    monitor_timeline = json.loads((trade_root / "evidence" / "monitor_evidence.json").read_text(encoding="utf-8"))
    assert strategist_evidence["decision_frames"][0]["payload"]["playbook"] == "pullback"
    assert scanner_evidence["candidate_selection_reasons"][0]["payload"]["final_decision_basis"] == "value plus sector-theme alignment"
    if list(monitor_timeline.get("threshold_snapshots") or []):
        assert monitor_timeline["threshold_snapshots"][0]["payload"]["watch_axes"] == ["Hard stop", "Peak drawdown"]
    new_bundle = json.loads((trade_root / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    assert (new_bundle.get("artifacts") or {}).get("strategist_evidence_json", "").endswith("strategist_evidence.json")
    assert (new_bundle.get("artifacts") or {}).get("scanner_evidence_json", "").endswith("scanner_evidence.json")
    assert isinstance(new_bundle.get("strategist_trace_summary"), dict)
    assert isinstance(new_bundle.get("scanner_trace_summary"), dict)
    assert new_bundle.get("selected_symbol") == "000660"
    assert new_bundle.get("runner_up_symbol") == "005930"
    assert new_bundle.get("candidate_count") == 5
    monitor_artifact_ref = str(
        (new_bundle.get("artifacts") or {}).get("monitor_evidence_json")
        or (new_bundle.get("artifacts") or {}).get("monitor_timeline_json")
        or ""
    )
    assert monitor_artifact_ref.endswith("monitor_evidence.json")
    assert (new_bundle.get("artifacts") or {}).get("commander_evidence_json", "").endswith("commander_evidence.json")
    assert new_bundle["artifacts"]["strategist_llm_response_json"].endswith("strategist_llm_response.json")
    assert new_bundle["artifacts"]["ai_trade_report_llm_response_json"].endswith("ai_trade_report_llm_response.json")
    assert new_bundle["artifacts"]["ai_trade_report_input_json"].endswith("ai_trade_report_input.json")
    assert new_bundle["artifacts"]["ai_trade_report_compact_input_json"].endswith("ai_trade_report_compact_input.json")

    trade_report_md = (trade_root / "reports" / "ai_trade_report.md").read_text(encoding="utf-8")
    assert "# AI 嫄곕옒 由ы룷?? in trade_report_md or "# Trade Report" in trade_report_md
    assert "70500.00" in trade_report_md
    assert "71600.00" in trade_report_md
    assert "-1.54%" in trade_report_md
    assert "position.current_price" in trade_report_md or "market.quote.price" in trade_report_md
    assert "시장 환경 요약" in trade_report_md or "Market Context at Entry" in trade_report_md
    assert "Hold and monitor." in trade_report_md
    assert "stop breach" in trade_report_md


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
    assert out["bundles"][0]["status"] == "partial"
    story_id = out["bundles"][0]["story_id"]
    trade_report = json.loads((reports_root / "trades" / day / story_id / "reports" / "ai_trade_report.json").read_text(encoding="utf-8"))
    reporter_eval = trade_report["reporter_evaluation"]
    assert reporter_eval["status"] in {"linked", "pending"}
    assert reporter_eval["summary"]


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
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    lifecycle = out["bundles"][0]
    assert lifecycle["status"] == "open"
    assert "run-3" in lifecycle["hold_run_ids"]
    trade_dir = reports_root / "trades" / day / lifecycle["story_id"]
    story_input = json.loads((trade_dir / "ai_trade_report_input.json").read_text(encoding="utf-8"))
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
    assert lifecycle["report_reason_code"] == "deterministic_only"
    story_id = lifecycle["story_id"]
    trade_dir = reports_root / "trades" / day / story_id
    assert (trade_dir / "ai_trade_report_input.json").exists()
    assert (trade_dir / "reports" / "ai_trade_report.json").exists()
    bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    diagnostics = bundle.get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "available"
    assert diagnostics.get("report_reason_code") == "deterministic_only"
    assert isinstance(bundle.get("entry"), dict)
    assert isinstance(bundle.get("exit"), dict)
    assert isinstance(bundle.get("shared_facts"), dict)


def test_live_execution_bundle_report_syncs_health_with_written_report_files(tmp_path: Path, capsys, monkeypatch) -> None:
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
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
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
    trade_id = out["bundles"][0]["story_id"]
    trade_dir = reports_root / "trades" / day / trade_id
    health = json.loads((trade_dir / "_health.json").read_text(encoding="utf-8"))

    assert trade_dir == reports_root / "trades" / day / trade_id
    assert (trade_dir / "reports" / "ai_trade_report.json").exists() is True
    assert health["llm_trade_report_status"] == "ok"
    assert health["report_generation_status"] == "available"
    assert health["artifact_presence"]["ai_trade_report_json"] is True
    assert health["artifact_presence"]["ai_trade_report_md"] is True


def test_live_execution_bundle_report_adds_day1_diagnostic_fields(tmp_path: Path, capsys, monkeypatch) -> None:
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
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
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
    trade_id = out["bundles"][0]["story_id"]
    trade_dir = reports_root / "trades" / day / trade_id
    lifecycle_bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    story_input = json.loads((trade_dir / "ai_trade_report_input.json").read_text(encoding="utf-8"))
    hold_payload = json.loads((trade_dir / "hold.json").read_text(encoding="utf-8"))
    entry_payload = json.loads((trade_dir / "entry.json").read_text(encoding="utf-8"))
    exit_payload = json.loads((trade_dir / "exit.json").read_text(encoding="utf-8"))

    assert lifecycle_bundle["same_day_reporter_linkage"]["status"] in {"linked_run", "linked_day_fallback"}
    assert isinstance(lifecycle_bundle["failure_classification"], dict)
    assert lifecycle_bundle["hold_events_count"] >= 1
    assert isinstance(lifecycle_bundle["monitor_context_snapshots"], list)
    assert isinstance(lifecycle_bundle["hold_signal_transitions"], list)
    assert isinstance(lifecycle_bundle["pre_exit_context_summary"], dict)
    for payload in (
        lifecycle_bundle["execution_details"],
        lifecycle_bundle["entry_execution_details"],
        lifecycle_bundle["exit_execution_details"],
        story_input["execution_details"],
        story_input["entry_execution_details"],
        story_input["exit_execution_details"],
        entry_payload["execution_details"],
        exit_payload["execution_details"],
    ):
        for key in ("order_status", "order_id", "execution_mode", "broker_env", "filled_qty", "avg_price"):
            assert key in payload
    assert hold_payload["hold_events_count"] >= 1
    assert isinstance(hold_payload["monitor_context_snapshots"], list)
    assert isinstance(story_input["same_day_reporter_linkage"], dict)
    assert isinstance(story_input["failure_classification"], dict)


def test_live_execution_bundle_report_preserves_canonical_paths_in_lifecycle_artifacts(
    tmp_path: Path, capsys, monkeypatch
) -> None:
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

    for rid in ("run-1", "run-2"):
        canonical_dir = reports_root / "canonical" / day / rid
        canonical_dir.mkdir(parents=True, exist_ok=True)
        (canonical_dir / "commander.json").write_text(json.dumps({"run_id": rid, "agent": "commander"}, ensure_ascii=False), encoding="utf-8")
        (canonical_dir / "strategist.json").write_text(json.dumps({"run_id": rid, "agent": "strategist"}, ensure_ascii=False), encoding="utf-8")
        (canonical_dir / "scanner.json").write_text(json.dumps({"run_id": rid, "agent": "scanner", "selected_symbol": "000660"}, ensure_ascii=False), encoding="utf-8")
        (canonical_dir / "monitor.json").write_text(json.dumps({"run_id": rid, "agent": "monitor", "selected_symbol": "000660"}, ensure_ascii=False), encoding="utf-8")
        (canonical_dir / "supervisor.json").write_text(json.dumps({"run_id": rid, "agent": "supervisor"}, ensure_ascii=False), encoding="utf-8")
        (canonical_dir / "executor.json").write_text(json.dumps({"run_id": rid, "agent": "executor", "symbol": "000660"}, ensure_ascii=False), encoding="utf-8")

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
    trade_id = out["bundles"][0]["story_id"]
    trade_dir = reports_root / "trades" / day / trade_id
    lifecycle_bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    artifact_links = json.loads((trade_dir / "_artifact_links.json").read_text(encoding="utf-8"))
    provenance = json.loads((trade_dir / "_provenance.json").read_text(encoding="utf-8"))

    for key in (
        "canonical_commander_json",
        "canonical_strategist_json",
        "canonical_scanner_json",
        "canonical_monitor_json",
        "canonical_supervisor_json",
        "canonical_executor_json",
    ):
        path_text = str((lifecycle_bundle.get("artifacts") or {}).get(key) or "")
        assert path_text
        assert Path(path_text).exists()
        assert str((artifact_links.get("links") or {}).get(key) or "") == path_text
        assert str((provenance.get("canonical_agent_artifact_paths") or {}).get(key) or "") == path_text


def test_resolve_lifecycle_bundle_sources_backfills_thin_anchor_bundle_from_canonical_runs(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-03-16"
    entry_run = "entry-run"
    exit_run = "exit-run"
    for rid, agents in {
        entry_run: {
            "strategist": {"run_id": entry_run, "agent": "strategist"},
            "scanner": {"run_id": entry_run, "agent": "scanner", "selected_symbol": "000660"},
        },
        exit_run: {
            "monitor": {"run_id": exit_run, "agent": "monitor", "trigger_type": "peak_drawdown"},
            "supervisor": {"run_id": exit_run, "agent": "supervisor"},
            "executor": {"run_id": exit_run, "agent": "executor", "symbol": "000660"},
            "commander": {"run_id": exit_run, "agent": "commander"},
        },
    }.items():
        canonical_dir = reports_root / "canonical" / day / rid
        canonical_dir.mkdir(parents=True, exist_ok=True)
        for agent, payload in agents.items():
            (canonical_dir / f"{agent}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    resolved = mod._resolve_lifecycle_bundle_sources(
        reports_root=reports_root,
        day=day,
        anchor_bundle={
            "commander": {},
            "strategist": {},
            "scanner": {},
            "monitor": {},
            "supervisor": {},
            "executor": {},
            "artifacts": {},
            "canonical_agent_artifacts": {},
            "evidence_provenance": {},
        },
        anchor_run_id=entry_run,
        entry_run_id=entry_run,
        exit_run_id=exit_run,
    )

    assert resolved["evidence_provenance"]["scanner"] == "canonical"
    assert resolved["evidence_provenance"]["monitor"] == "canonical"
    assert resolved["evidence_provenance"]["executor"] == "canonical"
    assert str((resolved["artifacts"] or {}).get("canonical_scanner_json") or "").endswith("scanner.json")
    assert str((resolved["artifacts"] or {}).get("canonical_monitor_json") or "").endswith("monitor.json")
    assert isinstance((resolved["canonical_agent_artifacts"] or {}).get("scanner"), dict)
    assert isinstance((resolved["canonical_agent_artifacts"] or {}).get("monitor"), dict)


def test_find_existing_trade_id_for_run_ids_prefers_earliest_existing_trade_id(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day_root = reports_root / "trades" / "2026-03-16"
    for trade_id, entry_run, exit_run in (
        ("TRD_20260316_005930_02", "entry-a", "exit-a"),
        ("TRD_20260316_005930_04", "entry-b", "exit-a"),
    ):
        trade_dir = day_root / trade_id
        trade_dir.mkdir(parents=True, exist_ok=True)
        (trade_dir / "lifecycle_bundle.json").write_text(
            json.dumps(
                {
                    "entry": {"run_id": entry_run},
                    "exit": {"run_id": exit_run},
                    "linked_run_ids": [entry_run, exit_run],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    resolved = mod._find_existing_trade_id_for_run_ids(
        reports_root=reports_root,
        day="2026-03-16",
        symbol="005930",
        run_ids=["exit-a"],
    )

    assert resolved == "TRD_20260316_005930_02"


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
    trade_dir = reports_root / "trades" / day / lifecycle["story_id"]
    story_input = json.loads((trade_dir / "ai_trade_report_input.json").read_text(encoding="utf-8"))
    trade_report = json.loads((trade_dir / "reports" / "ai_trade_report.json").read_text(encoding="utf-8"))

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
    assert lifecycle["report_status"] == "available"
    assert lifecycle["report_reason_code"] in {"", "deterministic_only", "llm_generation_failed"}
    trade_dir = reports_root / "trades" / day / lifecycle["story_id"]
    assert (trade_dir / "reports" / "ai_trade_report.json").exists()
    bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    diagnostics = bundle.get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "available"
    assert diagnostics.get("ai_trade_report_status") in {"ok", "salvaged", "skipped"}


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
    trade_dir = reports_root / "trades" / day / trade_id
    llm_response_path = trade_dir / "reports" / "ai_trade_report_llm_response.json"
    existing_report = (trade_dir / "reports" / "ai_trade_report.json").read_text(encoding="utf-8")
    existing_md = (trade_dir / "reports" / "ai_trade_report.md").read_text(encoding="utf-8")
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

    diagnostics = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8")).get("ai_report_diagnostics") or {}
    assert diagnostics.get("report_status") == "available"
    assert diagnostics.get("ai_trade_report_status") in {"ok", "salvaged", "skipped"}
    current_report_obj = json.loads((trade_dir / "reports" / "ai_trade_report.json").read_text(encoding="utf-8"))
    previous_report_obj = json.loads(existing_report)
    assert current_report_obj.get("trade_id") == previous_report_obj.get("trade_id")
    assert current_report_obj.get("status") == previous_report_obj.get("status")
    current_md = (trade_dir / "reports" / "ai_trade_report.md").read_text(encoding="utf-8")
    assert current_md.strip()
    assert "# AI 嫄곕옒 由ы룷?? in current_md or "# Trade Report" in current_md
    if existing_llm:
        assert llm_response_path.read_text(encoding="utf-8") == existing_llm


def test_live_execution_bundle_report_skips_when_background_job_is_already_running(tmp_path: Path, capsys, monkeypatch) -> None:
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 77777,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "script": "run_live_execution_bundle_report.py",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(mod, "_pid_active", lambda pid: True)

    rc = mod.main(["--day", "2026-04-13", "--json"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out["status"] == "skipped"
    assert out["reason"] == "bundle_job_already_running"
    assert out["active_pid"] == 77777
    assert out["lock_path"] == str(lock_path)
    assert out["detection_source"] == "lock"


def test_live_execution_bundle_report_ignores_process_scan_when_no_lock_owner_exists(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(
        mod,
        "_active_background_process",
        lambda role: {
            "pid": 88888,
            "parent_pid": 777,
            "role": role,
            "command_line": "python scripts/run_live_execution_bundle_report.py --role intraday_trade_report_bundle",
            "detection_source": "process_scan",
        },
    )
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
            "--target-run-id",
            "run-2",
            "--role",
            "intraday_trade_report_bundle",
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out["targeted_mode"] is True
    assert out["target_run_id"] == "run-2"


def test_live_execution_bundle_report_parent_spawn_bypasses_process_self_guard(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(
        mod,
        "_active_background_process",
        lambda role: {
            "pid": 88888,
            "parent_pid": 777,
            "role": role,
            "command_line": "python scripts/run_live_execution_bundle_report.py --role intraday_trade_report_bundle",
            "detection_source": "process_scan",
        },
    )
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setenv("INTRADAY_TRADE_REPORT_PARENT_SPAWN", "1")

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
            "--target-run-id",
            "run-2",
            "--role",
            "intraday_trade_report_bundle",
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out["targeted_mode"] is True
    assert out["target_run_id"] == "run-2"
    assert out["target_symbol"] == "000660"
    assert out["targeted_execution_run_count"] == 1


def test_live_execution_bundle_report_parent_spawn_reuses_matching_lock_without_skipping(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 12345,
                "parent_pid": 999,
                "role": "intraday_trade_report_bundle",
                "target_run_id": "run-2",
                "target_symbol": "000660",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "started_at_epoch": time.time(),
                "touched_at_epoch": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setenv("INTRADAY_TRADE_REPORT_PARENT_SPAWN", "1")
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
            "--target-run-id",
            "run-2",
            "--target-symbol",
            "000660",
            "--role",
            "intraday_trade_report_bundle",
            "--trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out.get("reason", "") != "bundle_job_already_running"
    assert out["target_run_id"] == "run-2"


def test_live_execution_bundle_report_targeted_mode_filters_to_target_symbol_runs(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
            {"run_id": "run-3", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B1", "return_msg": "ok"}}}},
            {"run_id": "run-4", "ts": f"{day}T00:15:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
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
            "--target-run-id",
            "run-2",
            "--role",
            "intraday_trade_report_bundle",
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out["targeted_mode"] is True
    assert out["target_run_id"] == "run-2"
    assert out["target_symbol"] == "000660"
    assert out["targeted_execution_run_count"] == 1
    assert out["targeted_lifecycle_context_run_count"] == 2
    assert len(out["run_bundles"]) == 1
    assert out["run_bundles"][0]["run_id"] == "run-2"
    assert {row["symbol"] for row in out["run_bundles"]} == {"000660"}
    assert {row["symbol"] for row in out["bundles"]} == {"000660"}


def test_live_execution_bundle_report_marks_story_input_for_intraday_bundle_skip(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    captured_story_inputs: list[dict] = []

    def _capture_ai_trade_report(story_input: dict, **kwargs):  # type: ignore[no-untyped-def]
        captured_story_inputs.append(dict(story_input))
        return _fake_ai_trade_report_ok(story_input, **kwargs)

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _capture_ai_trade_report)

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
            "--target-run-id",
            "run-2",
            "--role",
            "intraday_trade_report_bundle",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert captured_story_inputs
    story_input = captured_story_inputs[0]
    assert story_input["report_runtime_mode"] == "intraday_bundle"
    assert story_input["skip_separated_report_llm"] is True


def test_live_execution_bundle_report_spawns_followup_from_queue_after_completion(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"
    queue_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.queue.json"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
            {"run_id": "run-3", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B1", "return_msg": "ok"}}}},
            {"run_id": "run-4", "ts": f"{day}T00:15:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(
            [
                {
                    "target_run_id": "run-4",
                    "target_symbol": "005930",
                    "role": "intraday_trade_report_bundle",
                    "reason": "bundle_job_already_running",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    spawned: list[list[str]] = []

    class DummyProc:
        pid = 77777

    def fake_popen(cmd, **kwargs):  # type: ignore[no-untyped-def]
        spawned.append(list(cmd))
        return DummyProc()

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(mod, "_background_job_queue_path", lambda: queue_path)
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

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
            "--target-run-id",
            "run-2",
            "--target-symbol",
            "000660",
            "--role",
            "intraday_trade_report_bundle",
            "--no-trade-report-ai",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert spawned
    flat_cmd = " ".join(spawned[0])
    assert "--target-run-id run-4" in flat_cmd
    assert "--target-symbol 005930" in flat_cmd
    queue_rows = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue_rows == []


def test_live_execution_bundle_report_targeted_mode_prefilters_trace_inputs(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-1", "ts": f"{day}T00:00:02+00:00", "stage": "monitor", "event": "summary", "payload": {"symbol": "000660"}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:02+00:00", "stage": "monitor", "event": "summary", "payload": {"symbol": "000660"}},
            {"run_id": "run-3", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B1", "return_msg": "ok"}}}},
            {"run_id": "run-4", "ts": f"{day}T00:15:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "B2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(
        evidence_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "agent": "strategist", "stage": "theme_selection", "raw_input": {"llm_payload": {"themes": ["semis"]}}},
            {"run_id": "run-2", "ts": f"{day}T00:05:01+00:00", "agent": "strategist", "stage": "theme_selection", "raw_input": {"llm_payload": {"themes": ["semis"]}}},
            {"run_id": "run-4", "ts": f"{day}T00:15:01+00:00", "agent": "strategist", "stage": "theme_selection", "raw_input": {"llm_payload": {"themes": ["chips"]}}},
        ],
    )

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)
    monkeypatch.setattr(mod, "build_ai_trade_report", _fake_ai_trade_report_ok)

    captured: dict[str, list[str]] = {}

    def fake_trace(*args, **kwargs):  # type: ignore[no-untyped-def]
        event_rows = list(kwargs.get("event_rows") or [])
        evidence_rows = list(kwargs.get("evidence_rows_all") or [])
        captured["event_run_ids"] = sorted({str(row.get("run_id") or "") for row in event_rows})
        captured["evidence_run_ids"] = sorted({str(row.get("run_id") or "") for row in evidence_rows})
        kwargs.pop("event_rows", None)
        kwargs.pop("evidence_rows_all", None)
        return _fake_trace(*args, **kwargs)

    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", fake_trace)

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
            "--target-run-id",
            "run-2",
            "--role",
            "intraday_trade_report_bundle",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["ok"] is True
    assert out["targeted_mode"] is True
    assert captured["event_run_ids"] == ["run-2"]
    assert captured["evidence_run_ids"] == ["run-2"]


def test_live_execution_bundle_report_skips_ai_regeneration_when_fingerprint_matches(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"
    lock_path = tmp_path / "reports" / "runtime" / "intraday_trade_report_bundle.lock"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
        ],
    )
    _write_jsonl(evidence_log, [])

    monkeypatch.setattr(mod, "_background_job_lock_path", lambda: lock_path)
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", _fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", _fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", _fake_reporter)

    calls = {"count": 0}

    def fake_ai(story_input, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return _fake_ai_trade_report_ok(story_input, **kwargs)

    monkeypatch.setattr(mod, "build_ai_trade_report", fake_ai)

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
            "--role",
            "intraday_trade_report_bundle",
            "--json",
        ]
    )
    first_out = json.loads(capsys.readouterr().out.strip())
    assert first_rc == 0
    assert first_out["ok"] is True
    assert calls["count"] == 1

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
            "--role",
            "intraday_trade_report_bundle",
            "--json",
        ]
    )
    second_out = json.loads(capsys.readouterr().out.strip())
    assert second_rc == 0
    assert second_out["ok"] is True
    assert calls["count"] == 1

    trade_id = str(second_out["bundles"][0]["trade_id"])
    trade_dir = reports_root / "trades" / day / trade_id
    bundle = json.loads((trade_dir / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    diagnostics = bundle.get("ai_report_diagnostics") or {}
    generation_state = json.loads((trade_dir / "reports" / "report_generation_state.json").read_text(encoding="utf-8"))
    assert diagnostics.get("report_generation_reason") == "fingerprint_match_existing_success"
    assert generation_state["components"]["ai_trade_report"]["skip_reason"] == "fingerprint_match_existing_success"


def test_story_type_classification_is_deterministic() -> None:
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": True, "broker_env": "mock"}) == "simulation"
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": False, "broker_env": "real"}) == "failed_execution"
    assert mod._classify_story_type({}, {"execution_attempted": False, "execution_ok": False, "broker_env": "real"}) == "decision_only"
    assert mod._classify_story_type({"action": "BUY"}, {"execution_attempted": True, "execution_ok": True, "broker_env": "real"}) == "live_trade"


def test_build_trade_lifecycles_promotes_closed_trade_story_type_from_exit_bundle() -> None:
    lifecycles = mod._build_trade_lifecycles(
        day="2026-04-13",
        run_snapshots=[
            {
                "run_id": "buy-run",
                "ts_start": "2026-04-13T05:59:31+00:00",
                "ts_epoch": 1,
                "symbol": "010170",
                "execution_action": "BUY",
                "execution": {"action": "BUY", "symbol": "010170", "qty": 1},
                "verdict_allowed": True,
                "monitor_reason": "",
                "exit_reason": "",
                "monitor": {},
            },
            {
                "run_id": "sell-run",
                "ts_start": "2026-04-13T06:01:33+00:00",
                "ts_epoch": 2,
                "symbol": "010170",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "symbol": "010170", "qty": 1},
                "verdict_allowed": True,
                "monitor_reason": "",
                "exit_reason": "peak_drawdown",
                "monitor": {},
            },
        ],
        run_bundles={
            "buy-run": {},
            "sell-run": {
                "story_contract": {
                    "story_type": "simulation",
                    "execution_mode_label": "simulation (mock broker)",
                }
            },
        },
    )
    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "closed"
    assert lifecycle["story_type"] == "simulation"
    assert lifecycle["execution_mode_label"] == "simulation (mock broker)"


def test_build_trade_lifecycles_promotes_closed_trade_story_type_from_snapshot_when_bundle_missing() -> None:
    lifecycles = mod._build_trade_lifecycles(
        day="2026-04-13",
        run_snapshots=[
            {
                "run_id": "buy-run",
                "ts_start": "2026-04-13T05:59:31+00:00",
                "ts_epoch": 1,
                "symbol": "010170",
                "execution_action": "BUY",
                "execution": {"action": "BUY", "symbol": "010170", "qty": 1},
                "verdict_allowed": True,
                "monitor_reason": "",
                "exit_reason": "",
                "monitor": {},
            },
            {
                "run_id": "sell-run",
                "ts_start": "2026-04-13T06:01:33+00:00",
                "ts_epoch": 2,
                "symbol": "010170",
                "execution_action": "SELL",
                "execution": {"action": "SELL", "symbol": "010170", "qty": 1},
                "verdict_allowed": True,
                "monitor_reason": "",
                "exit_reason": "peak_drawdown",
                "monitor": {},
            },
        ],
        run_bundles={
            "buy-run": {},
            "sell-run": {},
        },
    )
    assert len(lifecycles) == 1
    lifecycle = lifecycles[0]
    assert lifecycle["status"] == "closed"
    assert lifecycle["story_type"] == "live_trade"
    assert lifecycle["execution_mode_label"] == "decision only"


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


def test_same_day_reporter_linkage_keeps_missing_path_honest(tmp_path: Path) -> None:
    reporter_js = tmp_path / "reporter_analysis_2026-03-18.json"
    reporter_md = tmp_path / "reporter_analysis_2026-03-18.md"

    linkage = mod._build_same_day_reporter_linkage(  # type: ignore[attr-defined]
        reporter_obj={},
        reporter_js=reporter_js,
        reporter_md=reporter_md,
        entry_run_id="run-1",
        exit_run_id="run-2",
        entry_bundle={"reporter": {"reporter_analysis_found": False, "reporter_analysis_day_file_found": False}},
        exit_bundle={"reporter": {"reporter_analysis_found": False, "reporter_analysis_day_file_found": False}},
    )

    assert linkage["status"] == "missing"
    assert linkage["reporter_analysis_json_path"] == ""
    assert linkage["reporter_analysis_md_path"] == ""
    assert linkage["reporter_analysis_expected_json_path"].endswith("reporter_analysis_2026-03-18.json")
    assert linkage["reporter_analysis_expected_md_path"].endswith("reporter_analysis_2026-03-18.md")
    assert linkage["reporter_analysis_json_found"] is False
    assert linkage["reporter_analysis_md_found"] is False


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


def test_build_strategist_input_artifacts_falls_back_to_prompt_artifact_for_cached_route(tmp_path: Path) -> None:
    prompt_path = (
        tmp_path
        / "reports"
        / "llm"
        / "2026-03-19"
        / "cached-buy-run"
        / "strategist"
        / "prompt.json"
    )
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        json.dumps(
            {
                "stage": "theme_selection",
                "payload": {
                    "market_regime_hint": "neutral",
                    "market_sentiment_hint": "neutral",
                    "playbook_hint": "defensive",
                    "themes_hint": ["broad_market_leaders"],
                    "global_sentiment_signal": {
                        "score": 0.017,
                        "fear_index": {"level": 17.94, "change_pct": -1.26, "level_pressure": 0.0},
                    },
                    "news_context": {"headline_count": 60, "candidate_signal_total": 5, "market_signal_total": 7},
                    "news_query_targets": ["KOSPI", "미국 증시"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    input_artifact, compact_artifact = mod._build_strategist_input_artifacts(
        {
            "run_id": "cached-buy-run",
            "strategist": {},
        },
        day="2026-03-19",
        trade_id="TRD_20260319_000660_01",
        reports_root=tmp_path / "reports",
        strategist_evidence={"run_ids": []},
        evidence_rows=[],
    )

    assert input_artifact["status"] == "ok"
    assert input_artifact["summary"]["market_regime_hint"] == "neutral"
    assert input_artifact["summary"]["playbook_hint"] == "defensive"
    assert input_artifact["summary"]["headline_count"] == 60
    assert compact_artifact["compact_input"]["playbook_hint"] == "defensive"
    assert input_artifact["meta"]["source_stage"] == "theme_selection"


def test_expand_targeted_run_ids_with_cached_strategist_sources_includes_prior_frame() -> None:
    event_rows = [
        {
            "ts": "2026-03-19T01:49:30+00:00",
            "run_id": "strategist-source-run",
            "event_name": "strategist.decision_frame",
            "agent": "strategist",
            "payload": {"playbook": "defensive"},
        },
        {
            "ts": "2026-03-19T01:50:19+00:00",
            "run_id": "cached-buy-run",
            "event_name": "commander_router.fast_path",
            "agent": "commander_router",
            "payload": {"path": "integrated_chain_cached_frame", "reuse_sec": 180, "reason": "flat_position_cached_strategist"},
        },
    ]

    expanded = mod._expand_targeted_run_ids_with_cached_strategist_sources(  # type: ignore[attr-defined]
        event_rows=event_rows,
        targeted_run_ids={"cached-buy-run"},
    )

    assert expanded == {"cached-buy-run", "strategist-source-run"}


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
    assert enriched["strategy_anchor"]["artifacts"]["strategist_compact_input_json"].endswith("strategist_compact_input.json")
    assert enriched["strategy_anchor"]["artifacts"]["strategist_llm_response_json"].endswith("strategist_llm_response.json")


def test_live_execution_bundle_report_populates_operator_brief_links_and_flat_compat_keys(
    tmp_path: Path, capsys, monkeypatch
) -> None:
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
    trade_id = out["bundles"][0]["story_id"]
    trade_dir = reports_root / "trades" / day / trade_id
    brief_json = trade_dir / "reports" / "operator_brief.json"
    brief_md = trade_dir / "reports" / "operator_brief.md"
    brief_llm = trade_dir / "reports" / "brief_llm_response.json"
    lifecycle_path = trade_dir / "lifecycle_bundle.json"

    artifact_links = json.loads((trade_dir / "_artifact_links.json").read_text(encoding="utf-8"))
    assert artifact_links["operator_brief"] == str(brief_json)
    assert artifact_links["links"]["brief_json"] == str(brief_json)
    assert artifact_links["links"]["operator_brief_json"] == str(brief_json)
    assert artifact_links["links"]["brief_md"] == str(brief_md)
    assert artifact_links["links"]["brief_llm_response_json"] == str(brief_llm)

    bundle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    assert bundle["operator_brief"] == str(brief_json)
    assert bundle["lifecycle_bundle"] == str(lifecycle_path)
    assert "strategist_llm_status" in bundle
    assert "brief_llm_status" in bundle
    assert "ai_trade_report_status" in bundle


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
                "news_query_targets": ["KOSPI", "US equities", "global rates", "semiconductors"],
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
    assert enriched["news_query_targets"] == ["KOSPI", "US equities", "global rates", "semiconductors"]



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


def test_live_execution_bundle_report_propagates_canonical_monitor_freshness_into_trade_evidence(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-24"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": "run-1",
                "ts": f"{day}T00:00:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "BUY", "symbol": "003280", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}},
            },
        ],
    )
    _write_jsonl(evidence_log, [])
    canonical_monitor = reports_root / "canonical" / day / "run-1" / "monitor.json"
    canonical_monitor.parent.mkdir(parents=True, exist_ok=True)
    canonical_monitor.write_text(
        json.dumps(
            {
                "schema_version": "agent_output.v1",
                "agent": "monitor",
                "run_id": "run-1",
                "symbol": "003280",
                "phase": "session",
                "threshold_snapshot": {
                    "entry_minute_snapshot_age_minutes": 4.5,
                    "entry_minute_snapshot_was_stale": True,
                    "entry_minute_refetch_attempted": True,
                    "entry_minute_refetch_succeeded": False,
                    "entry_minute_refetch_reason": "stale_snapshot_age_exceeded",
                    "entry_minute_refetch_trigger_reason": "stale_snapshot_age_exceeded",
                    "entry_minute_refetch_failure_reason": "refetch_not_ready",
                    "entry_latest_candle_ts": 1774324860,
                    "entry_inferred_spacing_minutes": 1.0,
                    "entry_series_class": "intraday",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    trade_id = out["bundles"][0]["story_id"]
    monitor_evidence = json.loads((reports_root / "trades" / day / trade_id / "evidence" / "monitor_evidence.json").read_text(encoding="utf-8"))
    assert monitor_evidence["entry_minute_snapshot_age_minutes"] == 4.5
    assert monitor_evidence["entry_minute_snapshot_was_stale"] is True
    assert monitor_evidence["entry_minute_refetch_attempted"] is True
    assert monitor_evidence["entry_minute_refetch_succeeded"] is False
    assert monitor_evidence["entry_minute_refetch_reason"] == "stale_snapshot_age_exceeded"
    assert monitor_evidence["entry_minute_refetch_trigger_reason"] == "stale_snapshot_age_exceeded"
    assert monitor_evidence["entry_minute_refetch_failure_reason"] == "refetch_not_ready"
    assert monitor_evidence["entry_latest_candle_ts"] == 1774324860
    assert monitor_evidence["entry_inferred_spacing_minutes"] == 1.0
    assert monitor_evidence["entry_series_class"] == "intraday"
    assert monitor_evidence["threshold_snapshots"][0]["payload"]["entry_minute_refetch_failure_reason"] == "refetch_not_ready"


def test_live_execution_bundle_report_marks_partial_recovery_trade_explicitly(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-24"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": "run-sell-only",
                "ts": f"{day}T00:05:01+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 1}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}},
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
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    trade_id = out["bundles"][0]["story_id"]
    bundle = json.loads((reports_root / "trades" / day / trade_id / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    provenance = json.loads((reports_root / "trades" / day / trade_id / "_provenance.json").read_text(encoding="utf-8"))
    health = json.loads((reports_root / "trades" / day / trade_id / "_health.json").read_text(encoding="utf-8"))
    assert bundle["trade_lifecycle_status"] == "partial"
    assert bundle["trade_origin"] == "recovered_partial"
    assert bundle["lifecycle_completeness"] == "partial"
    assert bundle["evidence_recovery_used"] is True
    assert isinstance(bundle["recovery_missing_sections"], list)
    assert isinstance(bundle["recovery_sources"], list)
    assert "entry" in bundle["recovery_missing_sections"] or "entry_evidence" in bundle["recovery_missing_sections"]
    assert "partial_lifecycle" in bundle["recovery_sources"]

def test_build_holding_phase_observability_recovers_short_hold_evidence() -> None:
    lifecycle = {
        "entry": {
            "run_id": "run-buy",
            "ts": "2026-04-14T10:00:00Z",
        },
        "exit": {
            "run_id": "run-sell",
            "ts": "2026-04-14T10:01:00Z",
            "monitor_context": {
                "posture": "HOLD",
                "monitor_reason": "trailing_stop_triggered",
                "current_drawdown": -0.02
            }
        },
        "summary": {"holding_duration": "1m"}
    }
    res = mod._build_holding_phase_observability(lifecycle, monitor_timeline={})
    
    assert res["hold_evidence_thin"] is False
    assert res["hold_events_count"] == 1
    assert len(res["monitor_context_snapshots"]) == 1
    assert res["monitor_context_snapshots"][0]["_recovery_source"] == "exit_monitor_context"
    assert res["monitor_context_snapshots"][0]["monitor_reason"] == "trailing_stop_triggered"
    assert "recovered from execution context" in res["holding_phase_summary"].lower()

def test_build_execution_details_recovers_order_id_and_avg_price() -> None:
    bundle = {
        "execution": {"action": "BUY", "qty": 10},
        "executor": {
            "broker_message": "Order accepted ord_no=B49080X123 successfully."
        },
        "monitor": {
            "current_price": 45000.0
        }
    }
    context = {
        "execution_context": {"summary": "Trade executed"}
    }
    
    res = mod._build_execution_details_from_bundle(bundle, context=context)
    
    assert res["order_id"] == "B49080X123"
    assert res["avg_price"] == 45000.0
    assert res["filled_qty"] == 10
    assert res["quality_score"] >= 0
    assert isinstance(res.get("merge_sources"), list)
