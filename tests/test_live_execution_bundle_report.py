from __future__ import annotations

import json
from pathlib import Path

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
            {"run_id": "run-3", "ts": f"{day}T00:05:00+00:00", "stage": "scanner", "event": "summary", "payload": {"top_stock": "000660"}},
            {"run_id": "run-3", "ts": f"{day}T00:05:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold_position", "exit_reason": "hold"}},
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

    trade_lifecycle = json.loads((canonical_dir / "trade_lifecycle.json").read_text(encoding="utf-8"))
    assert trade_lifecycle["status"] == "closed"
    assert trade_lifecycle["entry"]["run_id"] == "run-1"
    assert trade_lifecycle["exit"]["run_id"] == "run-2"
    assert "run-3" in trade_lifecycle["holding"]["run_ids"]
    assert trade_lifecycle["summary"]["holding_duration"]

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
    new_bundle = json.loads((new_trade_root / "lifecycle" / "aggregated_execution_bundle.json").read_text(encoding="utf-8"))
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
