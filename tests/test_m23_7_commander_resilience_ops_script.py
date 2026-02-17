from __future__ import annotations

import json
from pathlib import Path

from scripts.query_commander_resilience_events import main as query_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m23_7_query_commander_resilience_missing_path_returns_error(tmp_path: Path):
    missing = tmp_path / "missing.jsonl"
    rc = query_main(["--path", str(missing)])
    assert rc == 2


def test_m23_7_query_commander_resilience_only_incidents_json(tmp_path: Path, capsys):
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
                "payload": {"transition": "retry", "status": "retrying"},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:02+00:00",
                "stage": "commander_router",
                "event": "transition",
                "payload": {"transition": "cooldown", "status": "cooldown_wait"},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:03+00:00",
                "stage": "commander_router",
                "event": "resilience",
                "payload": {"reason": "cooldown_not_active", "incident_count": 0},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:04+00:00",
                "stage": "commander_router",
                "event": "resilience",
                "payload": {"reason": "cooldown_active", "incident_count": 3},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-17T00:00:05+00:00",
                "stage": "commander_router",
                "event": "error",
                "payload": {"error_type": "RuntimeError", "error": "boom"},
            },
        ],
    )

    rc = query_main(["--path", str(events), "--only-incidents", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    rows = obj["rows"]
    summary = obj["summary"]

    assert rc == 0
    assert len(rows) == 3
    assert [r["event"] for r in rows] == ["transition", "resilience", "error"]
    assert summary["cooldown_transition_total"] == 1
    assert summary["error_total"] == 1


def test_m23_7_query_commander_resilience_run_id_and_human_output(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-17T01:00:00+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume", "at_epoch": 100},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-17T01:00:01+00:00",
                "stage": "commander_router",
                "event": "intervention",
                "payload": {"type": "operator_resume", "at_epoch": 200},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-17T01:00:02+00:00",
                "stage": "commander_router",
                "event": "end",
                "payload": {"status": "resuming", "path": "graph_spine"},
            },
        ],
    )

    rc = query_main(["--path", str(events), "--run-id", "r2", "--limit", "10"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "intervention_total=1" in out
    assert "latest_run_id=r2" in out
    assert "event=intervention type=operator_resume" in out
    assert "event=end status=resuming path=graph_spine" in out
