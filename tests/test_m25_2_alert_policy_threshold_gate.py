from __future__ import annotations

import json
from pathlib import Path

from scripts.check_alert_policy_v1 import main as alert_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m25_2_alert_policy_passes_default_thresholds(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-17T00:00:00+00:00",
                "run_id": "r1",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
            },
            {
                "ts": "2026-02-17T00:00:01+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True, "reason": "Allowed"},
            },
            {
                "ts": "2026-02-17T00:00:02+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"ok": True},
            },
            {
                "ts": "2026-02-17T00:00:03+00:00",
                "run_id": "r2",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
        ],
    )

    rc = alert_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["alert_total"] == 0


def test_m25_2_alert_policy_fails_on_critical_by_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-17T00:00:00+00:00",
                "run_id": "r1",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
            },
            {
                "ts": "2026-02-17T00:00:01+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True, "reason": "Allowed"},
            },
            {
                "ts": "2026-02-17T00:00:02+00:00",
                "run_id": "r2",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": False, "error_type": "TimeoutError", "circuit_state": "open"},
            },
        ],
    )

    rc = alert_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["severity_total"]["critical"] >= 1
    codes = {str(a.get("code")) for a in obj["alerts"]}
    assert "strategist_success_rate_low" in codes
    assert "execution_approved_executed_gap_high" in codes


def test_m25_2_alert_policy_warning_can_fail_with_fail_on_warning(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-17T00:00:00+00:00",
                "run_id": "r1",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
            },
            {
                "ts": "2026-02-17T00:00:01+00:00",
                "run_id": "r2",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
            },
            {
                "ts": "2026-02-17T00:00:02+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked_1"},
            },
            {
                "ts": "2026-02-17T00:00:03+00:00",
                "run_id": "r2",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked_2"},
            },
            {
                "ts": "2026-02-17T00:00:04+00:00",
                "run_id": "r3",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
        ],
    )

    rc = alert_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--fail-on",
            "warning",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["severity_total"]["warning"] >= 1
    codes = {str(a.get("code")) for a in obj["alerts"]}
    assert "execution_blocked_rate_high" in codes
