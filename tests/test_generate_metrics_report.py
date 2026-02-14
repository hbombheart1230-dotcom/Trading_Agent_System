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
