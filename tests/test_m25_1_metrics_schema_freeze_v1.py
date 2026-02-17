from __future__ import annotations

import json
from pathlib import Path

import scripts.check_metrics_schema_v1 as schema_mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m25_1_metrics_schema_freeze_v1_passes(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-17T00:00:00+00:00",
                "run_id": "r1",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
            {
                "ts": "2026-02-17T00:00:01+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked_by_guard"},
            },
            {
                "ts": "2026-02-17T00:00:02+00:00",
                "run_id": "r1",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"allowed": True},
            },
        ],
    )

    rc = schema_mod.main(
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
    assert obj["schema_version"] == "metrics.v1"
    assert obj["failure_total"] == 0


def test_m25_1_metrics_schema_freeze_v1_fails_when_required_key_missing(tmp_path: Path, capsys, monkeypatch):
    reports = tmp_path / "reports"

    def _fake_generate_metrics_report(events_path, out_dir, day=None):  # type: ignore[no-untyped-def]
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        day_value = str(day or "2026-02-17")
        md = out_dir / f"metrics_{day_value}.md"
        js = out_dir / f"metrics_{day_value}.json"
        md.write_text("# fake\n", encoding="utf-8")
        js.write_text(
            json.dumps(
                {
                    "schema_version": "metrics.v1",
                    "strategist_llm": {"success_rate": 1.0, "latency_ms": {"p95": 100.0}, "circuit_open_rate": 0.0},
                    "execution": {"intents_created": 1, "intents_approved": 1, "intents_blocked": 0, "intents_executed": 1},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return md, js

    monkeypatch.setattr(schema_mod, "generate_metrics_report", _fake_generate_metrics_report)

    rc = schema_mod.main(
        [
            "--event-log-path",
            str(tmp_path / "events.jsonl"),
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
    assert obj["failure_total"] >= 1
    assert any("missing:execution.blocked_reason_topN" in x for x in obj["failures"])
    assert any("missing:broker_api.api_error_total_by_api_id" in x for x in obj["failures"])
