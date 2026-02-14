from pathlib import Path
import json

from scripts.generate_metrics_report import generate_metrics_report


def test_generate_metrics_report_aggregates_core_metrics(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": 1700000000,
                        "run_id": "r1",
                        "stage": "decision",
                        "event": "trace",
                        "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000001,
                        "run_id": "r1",
                        "stage": "decision",
                        "event": "trace",
                        "payload": {"decision_packet": {"intent": {"action": "NOOP"}}},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000002,
                        "run_id": "r1",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": True, "reason": "Allowed"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000003,
                        "run_id": "r2",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": False, "reason": "Symbol blocked"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000000,
                        "run_id": "r3",
                        "stage": "execute_from_packet",
                        "event": "start",
                        "payload": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000005,
                        "run_id": "r3",
                        "stage": "execute_from_packet",
                        "event": "end",
                        "payload": {"ok": True},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000010,
                        "run_id": "r4",
                        "stage": "execute_from_packet",
                        "event": "start",
                        "payload": {},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000014,
                        "run_id": "r4",
                        "stage": "execute_from_packet",
                        "event": "error",
                        "payload": {"api_id": "kt10000", "error": "timeout"},
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000020,
                        "run_id": "r5",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {
                            "ok": True,
                            "latency_ms": 120,
                            "attempts": 1,
                            "intent_action": "BUY",
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000021,
                        "run_id": "r6",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {
                            "ok": False,
                            "latency_ms": 350,
                            "attempts": 2,
                            "intent_action": "NOOP",
                            "error_type": "TimeoutError",
                        },
                    }
                ),
                json.dumps(
                    {
                        "ts": 1700000022,
                        "run_id": "r7",
                        "stage": "strategist_llm",
                        "event": "result",
                        "payload": {"ok": False, "intent_action": "NOOP"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    md, js = generate_metrics_report(events, out_dir, day="2023-11-14")
    assert md.exists() and js.exists()

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["intents_created_total"] == 1
    assert data["intents_approved_total"] == 1
    assert data["intents_blocked_total"] == 1
    assert data["intents_blocked_by_reason"]["Symbol blocked"] == 1
    assert data["execution_latency_seconds"]["count"] == 2.0
    assert abs(float(data["execution_latency_seconds"]["avg"]) - 4.5) < 1e-9
    assert data["api_error_total_by_api_id"]["kt10000"] == 1
    assert data["strategist_llm"]["total"] == 3
    assert data["strategist_llm"]["ok_total"] == 1
    assert data["strategist_llm"]["fail_total"] == 2
    assert abs(float(data["strategist_llm"]["success_rate"]) - (1.0 / 3.0)) < 1e-9
    assert data["strategist_llm"]["latency_ms"]["count"] == 2.0
    assert abs(float(data["strategist_llm"]["latency_ms"]["avg"]) - 235.0) < 1e-9
    assert data["strategist_llm"]["attempts"]["count"] == 2.0
    assert data["strategist_llm"]["error_type_total"]["TimeoutError"] == 1
    assert data["strategist_llm"]["error_type_total"]["unknown"] == 1


def test_generate_metrics_report_supports_iso_ts_and_latest_day(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-02-13T23:59:59+00:00",
                        "run_id": "old",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": False, "reason": "old-day"},
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-02-14T10:00:00+00:00",
                        "run_id": "new",
                        "stage": "execute_from_packet",
                        "event": "verdict",
                        "payload": {"allowed": True, "reason": "Allowed"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day=None)
    data = json.loads(js.read_text(encoding="utf-8"))

    assert data["day"] == "2026-02-14"
    assert data["intents_approved_total"] == 1
    assert data["intents_blocked_total"] == 0


def test_generate_metrics_report_empty_has_llm_summary_keys(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-14")
    data = json.loads(js.read_text(encoding="utf-8"))

    assert data["events"] == 0
    assert data["strategist_llm"]["total"] == 0
    assert data["strategist_llm"]["ok_total"] == 0
    assert data["strategist_llm"]["fail_total"] == 0
    assert data["strategist_llm"]["success_rate"] == 0.0
