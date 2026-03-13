from __future__ import annotations

import json
from pathlib import Path

import scripts.run_offhours_full_trace_bundle as mod


def test_offhours_full_trace_bundle_builds_single_run_bundle(tmp_path: Path, capsys, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    state_path = tmp_path / "state.json"
    event_log_path = tmp_path / "events.jsonl"
    evidence_log_path = tmp_path / "evidence.jsonl"
    report_dir = tmp_path / "reports"

    def fake_run_once(state):  # type: ignore[no-untyped-def]
        state["run_id"] = "run_bundle_1"
        state["decision"] = "approve"
        state["decision_reason"] = "within_policy"
        return state

    def fake_trace(**kwargs):  # type: ignore[no-untyped-def]
        report_path = kwargs["report_dir"]
        report_path.mkdir(parents=True, exist_ok=True)
        md_path = report_path / "agent_pipeline_trace_run_bundle_1.md"
        js_path = report_path / "agent_pipeline_trace_run_bundle_1.json"
        out = {
            "run_id": "run_bundle_1",
            "day": "2026-03-12",
            "strategist": {
                "news_source": "naver",
                "news_query_reasoning": "neutral context kept broad market and macro queries; theme hints expanded queries from semiconductor",
                "news_sample_titles": ["headline a"],
                "global_sentiment_score": 0.2,
                "global_sentiment_status": "ok",
                "global_sentiment_source": "yfinance",
                "global_index_moves": {"sp500_pct": 0.9, "nasdaq_pct": 1.4, "dow_pct": 0.5},
                "llm_model": "minimax/minimax-m2.5",
                "llm_ok": True,
                "themes": ["semiconductor"],
                "playbook": "breakout",
            },
            "scanner": {
                "candidate_source": "kiwoom_market_data",
                "kiwoom_source_mix": {"top_value": 5, "condition_search": 3},
                "top_stock": "005930",
                "top_score": 0.91,
                "selected_candidate": {"symbol": "005930", "sources": ["top_value"], "score_breakdown": {"momentum": 0.2}},
            },
            "monitor": {
                "entry_reason": "entry_candidate_selected",
                "exit_reason": "",
                "monitor_reason": "no_position",
                "thresholds": {"stop_loss_pct": 0.03},
                "min_hold_sec": 600,
                "sell_cooldown_sec": 300,
                "exit_confirm_ticks": 2,
            },
            "supervisor": {"verdict": "approve"},
            "executor": {
                "order_action": "BUY",
                "order_symbol": "005930",
                "order_qty": 1,
                "mode": "real",
                "execution_mode": "real",
                "kiwoom_mode": "mock",
                "broker_env": "mock",
                "effective_mode": "mock_broker_http",
                "execution_ok": True,
            },
            "reporter": {"reporter_analysis_found": True, "reporter_analysis_day_file_found": True},
        }
        md_path.write_text("trace", encoding="utf-8")
        js_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return md_path, js_path, out

    def fake_trade(event_log_path, report_dir, **kwargs):  # type: ignore[no-untyped-def]
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "trade_explain_2026-03-12.md"
        js_path = report_dir / "trade_explain_2026-03-12.json"
        out = {"execution_summary": {"executions_total": 1, "sell_pairs_total": 0}}
        md_path.write_text("trade", encoding="utf-8")
        js_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return md_path, js_path, out

    def fake_reporter(event_log_path, report_dir, **kwargs):  # type: ignore[no-untyped-def]
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "reporter_analysis_2026-03-12.md"
        js_path = report_dir / "reporter_analysis_2026-03-12.json"
        out = {
            "improvement_suggestions": ["review exit thresholds"],
            "report_focus_targets": ["theme_accuracy", "exit_quality"],
            "incident_postmortem": {"incident_total": 0},
        }
        md_path.write_text("reporter", encoding="utf-8")
        js_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return md_path, js_path, out

    monkeypatch.setattr(mod, "run_offhours_validation_once", fake_run_once)
    monkeypatch.setattr(mod, "generate_agent_pipeline_trace_report", fake_trace)
    monkeypatch.setattr(mod, "generate_trade_explain_report", fake_trade)
    monkeypatch.setattr(mod, "generate_reporter_analysis_report", fake_reporter)

    rc = mod.main(
        [
            "--env-path",
            str(env_path),
            "--state-path",
            str(state_path),
            "--event-log-path",
            str(event_log_path),
            "--evidence-log-path",
            str(evidence_log_path),
            "--report-dir",
            str(report_dir),
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["schema_version"] == "offhours_full_trace_bundle.v1"
    assert out["run_id"] == "run_bundle_1"
    assert "broad market and macro queries" in out["strategist"]["news_query_reasoning"]
    assert out["strategist"]["global_index_moves"]["sp500_pct"] == 0.9
    assert out["scanner"]["top_stock"] == "005930"
    assert out["future_learning"]["improvement_suggestions"] == ["review exit thresholds"]
    assert Path(out["report_json_path"]).exists()
    assert Path(out["report_md_path"]).exists()
    assert "global_index_moves:" in Path(out["report_md_path"]).read_text(encoding="utf-8")
    assert "news_query_reasoning:" in Path(out["report_md_path"]).read_text(encoding="utf-8")
    assert "effective_mode=mock_broker_http" in Path(out["report_md_path"]).read_text(encoding="utf-8")
