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
        "strategist": {
            "playbook": "pullback",
            "themes": ["semiconductor"],
            "global_sentiment_score": -0.12,
            "fear_index": {"level": 25.4},
            "news_query_reasoning": "defensive context",
        },
        "scanner": {
            "top_stock": "000660" if rid == "run-1" else "005930",
            "top_score": 1.23,
            "candidate_pool_after_filter": 5,
            "selected_candidate": {"symbol": "000660" if rid == "run-1" else "005930", "why": "top_value+sector_theme"},
        },
        "monitor": {
            "selected_symbol": "000660" if rid == "run-1" else "005930",
            "entry_reason": "no_position",
            "exit_reason": "no_position",
            "monitor_reason": "no_position",
            "thresholds": {"stop_loss_pct": 0.08},
        },
        "supervisor": {"verdict": "approve"},
        "executor": {"execution_ok": True},
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
    out = {"day": day, "ai_summary": "same-day reporter summary"}
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
