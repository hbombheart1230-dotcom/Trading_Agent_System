from __future__ import annotations

import json
from pathlib import Path

from scripts.run_agent_pipeline_trace_report import main as trace_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_agent_pipeline_trace_report_builds_all_agent_sections(tmp_path: Path, capsys) -> None:
    day = "2026-03-10"
    run_id = "run_trace_1"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "agent_pipeline_trace"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:00+00:00",
                "stage": "commander_router",
                "event": "route",
                "payload": {"mode": "integrated_chain", "agents": ["strategist", "scanner", "monitor", "supervisor", "executor", "reporter"]},
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:01+00:00",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"provider": "openrouter", "model": "minimax/minimax-m2.5", "ok": True, "latency_ms": 420},
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:02+00:00",
                "stage": "strategist",
                "event": "summary",
                "payload": {
                    "themes": ["semiconductor", "AI"],
                    "playbook": "breakout",
                    "scanner_bias": "leader",
                    "scanner_priority": ["momentum", "volume_surge"],
                    "macro_stress_overlay": {
                        "active": True,
                        "stress_flags": ["elevated_vix", "dollar_strength"],
                        "reason": "vix=27.10 pressure=0.355 dxy_pct=0.31 tnx_delta=0.0040",
                    },
                    "scanner_source_policy": {
                        "preferred_sources": ["top_change_rate", "condition_search", "top_volume"],
                        "include_change_rate": True,
                        "include_condition_search": True,
                    },
                    "monitor_guidance": "hold_through_noise",
                    "risk_tone": "normal",
                    "news_query_reasoning": "risk-on context added leader/risk-appetite market queries; theme hints expanded queries from semiconductor, AI",
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:03+00:00",
                "stage": "scanner",
                "event": "summary",
                "payload": {
                    "candidate_source": "kiwoom_market_data",
                    "candidate_pool_before_filter": 10,
                    "candidate_pool_after_filter": 6,
                    "condition_search_status": "unavailable",
                    "condition_search_source": "unavailable",
                    "condition_search_reason": "kiwoom_condition_websocket_not_integrated",
                    "top_stock": "005930",
                    "top_score": 0.87,
                    "top_ranked_symbols": ["005930", "000660"],
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:04+00:00",
                "stage": "decision_trace",
                "event": "candidate_selection",
                "payload": {
                    "agent": "scanner",
                    "payload": {
                        "selected_symbol": "005930",
                        "scanner_source_policy": {
                            "preferred_sources": ["top_change_rate", "condition_search", "top_volume"],
                            "include_change_rate": True,
                            "include_condition_search": True,
                        },
                        "runner_up_symbol": "000660",
                        "selection_basis": {
                            "summary": "Scanner selected 005930 after strategist-guided weighting.",
                        },
                        "ranking_factors": ["momentum", "volume_surge", "commander_mission"],
                        "rejected_candidates": [{"symbol": "000660", "reason": "lower conviction"}],
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
                            "summary": "prefer_shallow_pullback_candidates, penalize_overextended (low)",
                            "bias_strength": "low",
                        },
                        "candidate_bias_adjustments": [
                            {
                                "symbol": "005930",
                                "bias_adjustment": 0.003,
                                "bias_adjustments": [{"reason": "shallow pullback preference applied"}],
                            }
                        ],
                        "selection_reason_with_bias": "Scanner selected 005930 after strategist-guided weighting and shallow pullback preference.",
                        "score_breakdown_summary": {"momentum": 0.24, "trend": 0.20},
                        "selected_candidate": {
                            "symbol": "005930",
                            "sources": ["top_value", "top_volume"],
                            "feature_snapshot": {"quote_trading_value": 1000000.0},
                        },
                    },
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:05+00:00",
                "stage": "monitor",
                "event": "summary",
                "payload": {"selected_symbol": "005930", "monitor_reason": "hold", "exit_triggered": False},
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:06+00:00",
                "stage": "decision_trace",
                "event": "entry_exit_decision",
                "payload": {
                    "agent": "monitor",
                    "payload": {
                        "entry_reason": "breakout_confirmation",
                        "exit_reason": "",
                        "monitor_reason": "hold",
                        "entry_check_summary": "Monitor held because breakout confirmation remains valid.",
                        "entry_blockers": ["none"],
                        "policy_ref": {
                            "policy_source": "strategist",
                            "policy_validation_status": "ok",
                            "policy_fallback_used": False,
                            "policy_partial_normalized": True,
                            "policy_default_filled_fields": ["enabled"],
                            "policy_validation_missing_fields": ["enabled"],
                            "policy_validation_invalid_fields": [],
                            "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
                        },
                        "timing_assessment": {"latest_candle_ts": 1710249600},
                        "exit_trigger_basis": {"trigger_type": ""},
                        "received_policy": {
                            "timeframe_minutes": 1,
                            "volume_ratio_min": 0.68,
                            "pullback_min_pct": 0.008,
                            "max_extended_from_vwap_pct": 0.13,
                        },
                        "received_policy_source": "commander_applied_policy",
                        "effective_policy": {
                            "timeframe_minutes": 1,
                            "volume_ratio_min": 0.75,
                            "pullback_min_pct": 0.008,
                            "max_extended_from_vwap_pct": 0.05,
                        },
                        "effective_policy_source": "monitor_frame_adjusted",
                        "effective_policy_source_chain": ["commander_applied_policy", "strategy_frame_adjustment", "monitor_effective_policy"],
                        "policy_adjustments": {
                            "inputs": {
                                "playbook": "defensive",
                                "monitor_guidance": "defensive_exit",
                                "risk_tone": "conservative",
                                "trade_aggressiveness": "low",
                            },
                            "applied_rules": ["playbook:defensive"],
                            "changed_fields": ["volume_ratio_min", "max_extended_from_vwap_pct"],
                        },
                        "policy_adjustment_summary": "defensive + conservative adjusted volume_ratio_min, max_extended_from_vwap_pct",
                        "effective_policy_deltas": [
                            {"field": "volume_ratio_min", "from": 0.68, "to": 0.75},
                            {"field": "max_extended_from_vwap_pct", "from": 0.13, "to": 0.05},
                        ],
                        "applied_policy": {"timeframe_minutes": 1, "volume_ratio_min": 0.68, "pullback_min_pct": 0.008},
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
                        "shadow_used": True,
                        "strategist_fallback_used": False,
                        "position_age_seconds": 120,
                        "thresholds": {"stop_loss_pct": 0.03},
                        "min_hold_sec": 600,
                        "sell_cooldown_sec": 300,
                        "exit_confirm_ticks": 2,
                        "min_hold_blocked": False,
                        "sell_cooldown_blocked": False,
                    },
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:07+00:00",
                "stage": "decision_trace",
                "event": "verdict",
                "payload": {"agent": "supervisor", "payload": {"verdict": "APPROVE", "supervisor_allow": True, "supervisor_reason": "ok"}},
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:08+00:00",
                "stage": "decision_trace",
                "event": "result",
                "payload": {
                    "agent": "executor",
                    "payload": {"execution_attempted": True, "order_result": {"ok": True, "broker_code": "0", "broker_message": "ok"}},
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:09+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {
                    "ok": True,
                    "order": {"order_api_id": "TTTC0802U", "action": "BUY", "symbol": "005930", "qty": 1},
                    "payload": {
                        "mode": "real",
                        "execution_mode": "real",
                        "kiwoom_mode": "mock",
                        "broker_env": "mock",
                        "effective_mode": "mock_broker_http",
                        "meta": {"url": "https://mock-api.example/orders"},
                    },
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:10+00:00",
                "stage": "commander_router",
                "event": "end",
                "payload": {
                    "status": "ok",
                    "path": "integrated_chain",
                    "decision_summary": "Commander kept the day in measured risk mode.",
                    "command_intent": "OBSERVE_ONLY",
                    "strategist_invocation": "RUN",
                    "llm_policy": "ALLOW",
                    "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                    "shadow_assessment_summary": "Shadow commander wanted confirmation before new entry.",
                    "shadow_used": True,
                    "shadow_reason_code": "WAIT_FOR_CONFIRMATION",
                    "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                    "strategist_fallback_used": False,
                    "applied_policy": {"timeframe_minutes": 1, "volume_ratio_min": 0.68, "pullback_min_pct": 0.008},
                    "policy_source": "strategist",
                    "policy_validation_status": "ok",
                    "policy_fallback_used": False,
                    "policy_fallback_reason": "",
                    "override_reason": "",
                    "applied_policy_source_chain": ["strategist", "validation", "commander_confirmed"],
                },
            },
        ],
    )

    _write_jsonl(
        evidence_log,
        [
            {
                "run_id": run_id,
                "timestamp": f"{day}T00:00:01+00:00",
                "agent": "strategist",
                "stage": "theme_selection",
                "raw_input": {
                    "collected_news": {"005930": {"count": 2, "sample": ["NewsItem(title='삼성전자 반등')"]}},
                    "global_sentiment_inputs": {
                        "score": 0.12,
                        "status": "ok",
                        "source": "yfinance",
                        "reason": "market_ok",
                        "index_moves": {"sp500_pct": 1.2, "nasdaq_pct": 1.8, "dow_pct": 0.7},
                        "fear_index": {"level": 27.1, "level_pressure": 0.355, "change_pct": -1.2},
                    },
                    "llm_payload": {"news_context": {"summary": "semiconductor rotation"}},
                },
                "llm_prompt": "prompt text",
                "llm_response": "{\"themes\": [\"semiconductor\"]}",
                "parsed_output": {"themes": ["semiconductor"], "playbook": "breakout"},
            },
            {
                "run_id": run_id,
                "timestamp": f"{day}T00:00:02+00:00",
                "agent": "scanner",
                "stage": "symbol_selection",
                "raw_input": {
                    "candidates": [
                        {"symbol": "005930", "sources": ["top_value", "top_volume"]},
                        {"symbol": "000660", "sources": ["top_change_rate"]},
                    ]
                },
            },
            {"run_id": run_id, "timestamp": f"{day}T00:00:11+00:00", "agent": "reporter", "stage": "post_run_analysis"},
        ],
    )

    (reports_root / "reporter_analysis").mkdir(parents=True, exist_ok=True)
    (reports_root / "reporter_analysis" / f"reporter_analysis_{day}.json").write_text(
        json.dumps(
            {
                "schema_version": "reporter_analysis.v1",
                "day": day,
                "decision_trace_chain_summary": {
                    "run_total": 1,
                    "rendered_run_total": 1,
                    "complete_chain_total": 1,
                    "chains": [{"run_id": run_id}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = trace_main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--run-id",
            run_id,
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["schema_version"] == "agent_pipeline_trace.v1"
    assert out["run_id"] == run_id
    assert out["commander"]["mode"] == "integrated_chain"
    assert out["strategist"]["llm_provider"] == "openrouter"
    assert out["strategist"]["global_sentiment_source"] == "yfinance"
    assert out["strategist"]["global_index_moves"]["nasdaq_pct"] == 1.8
    assert out["strategist"]["macro_stress_overlay"]["active"] is True
    assert "theme hints expanded" in out["strategist"]["news_query_reasoning"]
    assert out["strategist"]["scanner_source_policy"]["preferred_sources"][0] == "top_change_rate"
    assert out["scanner"]["top_stock"] == "005930"
    assert out["scanner"]["selected_candidate"]["symbol"] == "005930"
    assert out["scanner"]["runner_up_symbol"] == "000660"
    assert out["scanner"]["scanner_source_policy"]["include_change_rate"] is True
    assert out["scanner"]["condition_search_status"] == "unavailable"
    assert out["scanner"]["playbook"] == "breakout"
    assert out["scanner"]["policy_source"] == "strategist"
    assert out["scanner"]["applied_policy_present"] is True
    assert out["scanner"]["scanner_bias_applied"] is True
    assert out["scanner"]["scanner_bias_summary"]["summary"]
    assert out["scanner"]["candidate_bias_adjustments"][0]["symbol"] == "005930"
    assert "shallow pullback" in out["scanner"]["selection_reason_with_bias"]
    assert out["monitor"]["selected_symbol"] == "005930"
    assert out["monitor"]["min_hold_sec"] == 600
    assert out["monitor"]["policy_source"] == "strategist"
    assert out["monitor"]["applied_policy"]["volume_ratio_min"] == 0.68
    assert out["monitor"]["received_policy"]["volume_ratio_min"] == 0.68
    assert out["monitor"]["effective_policy"]["volume_ratio_min"] == 0.75
    assert out["monitor"]["policy_adjustment_summary"]
    assert out["commander"]["policy_source"] == "strategist"
    assert out["commander"]["applied_policy"]["pullback_min_pct"] == 0.008
    assert isinstance(out["commander"].get("policy_partial_normalized"), bool)
    assert out["reasoning_trace"]["commander_summary"]["summary"] == "Commander kept the day in measured risk mode."
    assert out["reasoning_trace"]["commander_summary"]["policy_source"] == "strategist"
    assert out["reasoning_trace"]["strategist_summary"]["selected_playbook"] == "breakout"
    assert out["reasoning_trace"]["scanner_summary"]["summary"] == "Scanner selected 005930 after strategist-guided weighting."
    assert out["reasoning_trace"]["scanner_summary"]["policy_source"] == "strategist"
    assert out["reasoning_trace"]["scanner_summary"]["scanner_bias_applied"] is True
    assert out["reasoning_trace"]["scanner_summary"]["scanner_bias_summary"]["summary"]
    assert out["reasoning_trace"]["monitor_summary"]["summary"] == "Monitor held because breakout confirmation remains valid."
    assert out["reasoning_trace"]["monitor_summary"]["policy_source"] == "strategist"
    assert out["reasoning_trace"]["monitor_summary"]["effective_policy"]["volume_ratio_min"] == 0.75
    assert out["reasoning_provenance"]["commander_context_source"] == "event_payload"
    assert out["reasoning_provenance"]["strategist_plan_source"] == "event_payload"
    assert out["reasoning_provenance"]["scanner_reason_source"] == "event_payload"
    assert out["reasoning_provenance"]["monitor_reason_source"] == "event_payload"
    assert out["reasoning_provenance"]["shadow_used"] is True
    assert out["reasoning_provenance"]["strategist_fallback_used"] is False
    assert out["supervisor"]["verdict"] == "APPROVE"
    assert out["executor"]["execution_attempted"] is True
    assert out["executor"]["execution_mode"] == "real"
    assert out["executor"]["kiwoom_mode"] == "mock"
    assert out["executor"]["broker_env"] == "mock"
    assert out["executor"]["effective_mode"] == "mock_broker_http"
    assert out["reporter"]["in_run_trace_available"] is True
    assert out["reporter"]["reporter_analysis_day_file_found"] is True
    assert out["reporter"]["reporter_analysis_found"] is True

    md_path = report_dir / "agent_pipeline_trace_run_trace_1.md"
    js_path = report_dir / "agent_pipeline_trace_run_trace_1.json"
    assert md_path.exists()
    assert js_path.exists()

    md_body = md_path.read_text(encoding="utf-8")
    assert "## Commander" in md_body
    assert "## Strategist" in md_body
    assert "global_index_moves:" in md_body
    assert "macro_stress:" in md_body
    assert "news_query_reasoning:" in md_body
    assert "scanner_source_policy:" in md_body
    assert "## Scanner" in md_body
    assert "condition_search: status=unavailable" in md_body
    assert "## Monitor" in md_body
    assert "## Reasoning Trace" in md_body
    assert "## Supervisor" in md_body
    assert "## Executor" in md_body
    assert "effective_mode=mock_broker_http" in md_body
    assert "## Reporter" in md_body


def test_agent_pipeline_trace_report_returns_error_when_no_run_id(tmp_path: Path, capsys) -> None:
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "agent_pipeline_trace"
    _write_jsonl(event_log, [])
    _write_jsonl(evidence_log, [])

    rc = trace_main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 3
    assert out["ok"] is False
    assert "No run_id could be resolved" in str(out["error"])


def test_agent_pipeline_trace_report_marks_reporter_analysis_false_when_run_not_present(
    tmp_path: Path, capsys
) -> None:
    day = "2026-03-10"
    run_id = "run_trace_1"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "agent_pipeline_trace"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:00+00:00",
                "stage": "commander_router",
                "event": "route",
                "payload": {"mode": "integrated_chain", "agents": []},
            }
        ],
    )
    _write_jsonl(evidence_log, [])

    (reports_root / "reporter_analysis").mkdir(parents=True, exist_ok=True)
    (reports_root / "reporter_analysis" / f"reporter_analysis_{day}.json").write_text(
        json.dumps(
            {
                "schema_version": "reporter_analysis.v1",
                "day": day,
                "decision_trace_chain_summary": {
                    "run_total": 1,
                    "rendered_run_total": 1,
                    "complete_chain_total": 1,
                    "chains": [{"run_id": "another_run_id"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = trace_main(
        [
            "--event-log-path",
            str(event_log),
            "--evidence-log-path",
            str(evidence_log),
            "--report-dir",
            str(report_dir),
            "--reports-root",
            str(reports_root),
            "--run-id",
            run_id,
            "--day",
            day,
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["reporter"]["reporter_analysis_day_file_found"] is True
    assert out["reporter"]["reporter_analysis_found"] is False
