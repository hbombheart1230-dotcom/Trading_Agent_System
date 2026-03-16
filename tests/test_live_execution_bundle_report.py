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
            "top_stock": "000660" if rid == "run-1" else "005930",
            "top_score": 1.23,
            "candidate_pool_after_filter": 5,
            "top_ranked_symbols": ["000660", "005930", "035420"] if rid == "run-1" else ["005930", "000660", "035420"],
            "selected_candidate": {
                "symbol": "000660" if rid == "run-1" else "005930",
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
            "selected_symbol": "000660" if rid == "run-1" else "005930",
            "entry_reason": "no_position",
            "exit_reason": "stop_loss" if rid == "run-2" else "no_position",
            "monitor_reason": "confirmed_exit_signal" if rid == "run-2" else "entry_ready",
            "thresholds": {"stop_loss_pct": 0.08, "take_profit_pct": 0.02},
            "position_age_seconds": 120,
            "exit_triggered": rid == "run-2",
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


def test_live_execution_bundle_report_creates_one_bundle_per_executed_run(tmp_path: Path, capsys, monkeypatch) -> None:
    day = "2026-03-16"
    event_log = tmp_path / "events.jsonl"
    evidence_log = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports" / "dev" / "analysis" / "live_execution_bundles"
    reports_root = tmp_path / "reports"

    _write_jsonl(
        event_log,
        [
            {"run_id": "run-1", "ts": f"{day}T00:00:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "BUY", "symbol": "000660", "qty": 1}, "payload": {"response_payload": {"ord_no": "A1", "return_msg": "ok"}}}},
            {"run_id": "run-2", "ts": f"{day}T00:10:01+00:00", "stage": "execute_from_packet", "event": "execution", "payload": {"order": {"action": "SELL", "symbol": "005930", "qty": 2}, "payload": {"response_payload": {"ord_no": "A2", "return_msg": "ok"}}}},
            {"run_id": "run-3", "ts": f"{day}T00:20:01+00:00", "stage": "monitor", "event": "summary", "payload": {"monitor_reason": "hold"}},
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
    assert out["ok"] is True
    assert out["bundle_count"] == 2
    assert [row["run_id"] for row in out["bundles"]] == ["run-1", "run-2"]
    assert (report_dir / "live_execution_bundle_run-1.json").exists()
    assert (report_dir / "live_execution_bundle_run-2.json").exists()

    bundle_obj = json.loads((report_dir / "live_execution_bundle_run-1.json").read_text(encoding="utf-8"))
    assert bundle_obj["execution"]["action"] == "BUY"
    assert bundle_obj["execution"]["symbol"] == "000660"
    assert bundle_obj["strategist"]["playbook"] == "pullback"
    assert bundle_obj["artifacts"]["trade_explain_json"].endswith(f"trade_explain_{day}.json")
    assert bundle_obj["story_contract"]["story_type"] == "simulation"
    assert bundle_obj["market_context_human"]["summary"]
    assert bundle_obj["scanner_reason_human"]["summary"]
    assert bundle_obj["filters_human"]["summary"]

    canonical_dir = reports_root / "trades" / "2026" / "03" / bundle_obj["story_id"]
    assert (canonical_dir / "aggregated_execution_bundle.json").exists()
    assert (canonical_dir / "trade_story_input.json").exists()
    assert (canonical_dir / "trade_report.json").exists()
    assert (canonical_dir / "trade_report.md").exists()

    story_input = json.loads((canonical_dir / "trade_story_input.json").read_text(encoding="utf-8"))
    assert story_input["symbol"] == "000660"
    assert story_input["story_type"] == "simulation"
    assert "Scanner selected 000660" in story_input["scanner_reason_human"]["summary"]

    trade_report = json.loads((canonical_dir / "trade_report.json").read_text(encoding="utf-8"))
    assert trade_report["market_context"]["summary"]
    assert trade_report["why_this_symbol"]["summary"]
    assert trade_report["scanner_logic_and_filters"]["summary"]
    assert "scanner" in trade_report["why_this_symbol"]["summary"].lower() or "selected" in trade_report["why_this_symbol"]["summary"].lower()
    assert "sentiment" in trade_report["market_context"]["summary"].lower()

    trade_report_md = (canonical_dir / "trade_report.md").read_text(encoding="utf-8")
    assert "## Market Context" in trade_report_md
    assert "## Why This Symbol" in trade_report_md
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
    story_id = out["bundles"][0]["story_id"]
    trade_report = json.loads((reports_root / "trades" / "2026" / "03" / story_id / "trade_report.json").read_text(encoding="utf-8"))
    reporter_eval = trade_report["reporter_evaluation"]
    assert reporter_eval["status"] == "pending"
    assert "not linked" in reporter_eval["summary"].lower() or "pending" in reporter_eval["summary"].lower()


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
