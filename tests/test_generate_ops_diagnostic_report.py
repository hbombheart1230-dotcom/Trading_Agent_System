from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_ops_diagnostic_report import generate_ops_diagnostic_report, main as ops_main


def test_generate_ops_diagnostic_report_aggregates_core_fields(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    rows = [
        {
            "ts": "2026-03-05T01:00:00+00:00",
            "run_id": "r1",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "NOOP", "reason": "model_no_signal"}}, "trace": {}},
        },
        {
            "ts": "2026-03-05T01:00:10+00:00",
            "run_id": "r2",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "NOOP", "reason": "missing_rationale"}}, "trace": {}},
        },
        {
            "ts": "2026-03-05T01:00:20+00:00",
            "run_id": "r3",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "NOOP", "reason": "post_exit_cooldown"}}, "trace": {}},
        },
        {
            "ts": "2026-03-05T01:01:00+00:00",
            "run_id": "r4",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": False, "reason": "noop_intent_skipped"},
        },
        {
            "ts": "2026-03-05T01:01:05+00:00",
            "run_id": "r5",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": False, "reason": "insufficient_mock_cash"},
        },
        {
            "ts": "2026-03-05T01:02:00+00:00",
            "run_id": "r6",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "market"},
                "payload": {"broker_code": "0", "order_id": "A1"},
            },
        },
        {
            "ts": "2026-03-05T01:02:10+00:00",
            "run_id": "r7",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "order": {"action": "SELL", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "market"},
                "payload": {"broker_code": "20"},
            },
        },
        {
            "ts": "2026-03-05T01:02:20+00:00",
            "run_id": "r8",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {
                "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "market"},
                "payload": {"api_ok": True},
            },
        },
        {
            "ts": "2026-03-05T01:03:00+00:00",
            "run_id": "r9",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": True, "latency_ms": 100},
        },
        {
            "ts": "2026-03-05T01:03:05+00:00",
            "run_id": "r10",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": False, "latency_ms": 200},
        },
        {
            "ts": "2026-03-05T01:03:10+00:00",
            "run_id": "r11",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": True, "latency_ms": 1000},
        },
        # different day (excluded)
        {
            "ts": "2026-03-04T23:59:59+00:00",
            "run_id": "old",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"payload": {"broker_code": "20"}},
        },
    ]
    events.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    out_dir = tmp_path / "reports"
    md, js = generate_ops_diagnostic_report(events, out_dir, day="2026-03-05")
    assert md.exists() and js.exists()

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["schema_version"] == "ops_diagnostic.v1"
    assert data["day"] == "2026-03-05"
    assert data["events"] == 11
    assert data["execution"]["execution_total"] == 3
    assert data["execution"]["verdict_block_total"] == 2
    assert data["execution"]["broker_success_total"] == 2
    assert data["execution"]["broker_fail_total"] == 1
    assert data["execution"]["broker_unknown_total"] == 0
    assert abs(float(data["execution"]["broker_success_rate"]) - (2.0 / 3.0)) < 1e-9
    assert data["execution"]["broker_failure_topN"][0]["broker_code"] == "20"
    assert data["execution"]["broker_failure_topN"][0]["count"] == 1
    assert data["noop"]["total"] == 3
    assert abs(float(data["noop"]["focus_reason_ratio"]["model_no_signal"]) - (1.0 / 3.0)) < 1e-9
    assert abs(float(data["noop"]["focus_reason_ratio"]["missing_rationale"]) - (1.0 / 3.0)) < 1e-9
    assert abs(float(data["noop"]["focus_reason_ratio"]["post_exit_cooldown"]) - (1.0 / 3.0)) < 1e-9
    assert data["strategist_llm"]["total"] == 3
    assert data["strategist_llm"]["ok_total"] == 2
    assert data["strategist_llm"]["error_total"] == 1
    assert data["strategist_llm"]["latency_ms"]["count"] == 3.0
    assert data["strategist_llm"]["latency_ms"]["p50"] == 200.0
    assert data["strategist_llm"]["latency_ms"]["p95"] == 1000.0


def test_generate_ops_diagnostic_report_main_json(tmp_path: Path, capsys) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    report_dir = tmp_path / "reports"

    rc = ops_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-03-05",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["schema_version"] == "ops_diagnostic.v1"
    assert obj["events"] == 0
    assert (report_dir / "ops_diagnostic_2026-03-05.json").exists()
    assert (report_dir / "ops_diagnostic_2026-03-05.md").exists()

