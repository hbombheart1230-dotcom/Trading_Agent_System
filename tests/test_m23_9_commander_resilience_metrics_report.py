from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_metrics_report import generate_metrics_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m23_9_generate_metrics_report_aggregates_commander_resilience(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:00+00:00",
                "stage": "commander_router",
                "event": "route",
                "payload": {"mode": "graph_spine"},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:01+00:00",
                "stage": "commander_router",
                "event": "transition",
                "payload": {"transition": "cooldown", "status": "cooldown_wait"},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:02+00:00",
                "stage": "commander_router",
                "event": "resilience",
                "payload": {"reason": "cooldown_active", "incident_count": 5},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-17T00:00:03+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume", "status": "resuming"},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-17T00:00:04+00:00",
                "stage": "commander_router",
                "event": "end",
                "payload": {"status": "resuming", "path": "graph_spine"},
            },
            {
                "run_id": "r3",
                "ts": "2026-02-17T00:00:05+00:00",
                "stage": "commander_router",
                "event": "error",
                "payload": {"status": "error", "error_type": "RuntimeError"},
            },
        ],
    )

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-17")
    data = json.loads(js.read_text(encoding="utf-8"))

    cr = data["commander_resilience"]
    assert cr["total"] == 6
    assert cr["cooldown_transition_total"] == 1
    assert cr["intervention_total"] == 1
    assert cr["error_total"] == 1
    assert cr["transition_total"]["cooldown"] == 1
    assert cr["runtime_status_total"]["cooldown_wait"] == 1
    assert cr["runtime_status_total"]["resuming"] == 2
    assert cr["runtime_status_total"]["error"] == 1
    assert cr["cooldown_reason_total"]["cooldown_active"] == 1


def test_m23_9_generate_metrics_report_empty_has_commander_resilience_keys(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")

    out_dir = tmp_path / "reports"
    _, js = generate_metrics_report(events, out_dir, day="2026-02-17")
    data = json.loads(js.read_text(encoding="utf-8"))

    cr = data["commander_resilience"]
    assert cr["total"] == 0
    assert cr["cooldown_transition_total"] == 0
    assert cr["intervention_total"] == 0
    assert cr["error_total"] == 0
    assert cr["transition_total"] == {}
    assert cr["runtime_status_total"] == {}
    assert cr["cooldown_reason_total"] == {}
