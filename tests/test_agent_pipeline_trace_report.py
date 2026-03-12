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
                    "monitor_guidance": "hold_through_noise",
                    "risk_tone": "normal",
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
                    "payload": {"selected_symbol": "005930", "score_breakdown_summary": {"momentum": 0.24, "trend": 0.20}},
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
                        "position_age_seconds": 120,
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
                    "payload": {"mode": "mock", "meta": {"url": "https://mock-api.example/orders"}},
                },
            },
            {
                "run_id": run_id,
                "ts": f"{day}T00:00:10+00:00",
                "stage": "commander_router",
                "event": "end",
                "payload": {"status": "ok", "path": "integrated_chain"},
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
                    "global_sentiment_inputs": {"score": 0.12, "status": "ok", "source": "yfinance", "reason": "market_ok"},
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
        json.dumps({"ok": True}, ensure_ascii=False),
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
    assert out["scanner"]["top_stock"] == "005930"
    assert out["monitor"]["selected_symbol"] == "005930"
    assert out["supervisor"]["verdict"] == "APPROVE"
    assert out["executor"]["execution_attempted"] is True
    assert out["reporter"]["in_run_trace_available"] is True

    md_path = report_dir / "agent_pipeline_trace_run_trace_1.md"
    js_path = report_dir / "agent_pipeline_trace_run_trace_1.json"
    assert md_path.exists()
    assert js_path.exists()

    md_body = md_path.read_text(encoding="utf-8")
    assert "## Commander" in md_body
    assert "## Strategist" in md_body
    assert "## Scanner" in md_body
    assert "## Monitor" in md_body
    assert "## Supervisor" in md_body
    assert "## Executor" in md_body
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
