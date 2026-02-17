from __future__ import annotations

import json
from pathlib import Path

from scripts.query_m25_notification_events import main as query_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_m25_10_notification_events_query_summary(tmp_path: Path, capsys):
    events = tmp_path / "notify_events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-17T00:00:00+00:00",
                "stage": "ops_batch_notify",
                "event": "result",
                "payload": {"day": "2026-02-17", "provider": "webhook", "ok": True, "sent": True, "skipped": False, "reason": "sent", "status_code": 200},
            },
            {
                "ts": "2026-02-17T00:01:00+00:00",
                "stage": "ops_batch_notify",
                "event": "result",
                "payload": {"day": "2026-02-17", "provider": "webhook", "ok": True, "sent": False, "skipped": True, "reason": "dedup_suppressed", "status_code": 0},
            },
            {
                "ts": "2026-02-17T00:02:00+00:00",
                "stage": "ops_batch_notify",
                "event": "result",
                "payload": {"day": "2026-02-17", "provider": "slack_webhook", "ok": False, "sent": True, "skipped": False, "reason": "http_error", "status_code": 500},
            },
            {"ts": "2026-02-17T00:03:00+00:00", "stage": "decision", "event": "trace", "payload": {}},
        ],
    )
    rc = query_main(["--event-log-path", str(events), "--day", "2026-02-17", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["total"] == 3
    assert obj["ok_total"] == 2
    assert obj["fail_total"] == 1
    assert obj["sent_total"] == 2
    assert obj["skipped_total"] == 1
    assert obj["provider_total"]["webhook"] == 2
    assert obj["provider_total"]["slack_webhook"] == 1
    assert obj["reason_total"]["dedup_suppressed"] == 1
    assert obj["status_code_total"]["500"] == 1


def test_m25_10_notification_events_query_empty(tmp_path: Path, capsys):
    events = tmp_path / "missing.jsonl"
    rc = query_main(["--event-log-path", str(events), "--day", "2026-02-17", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["total"] == 0
    assert obj["provider_total"] == {}
