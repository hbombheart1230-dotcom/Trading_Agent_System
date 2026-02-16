from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m22_closeout_check import main as closeout_main


def test_m22_10_closeout_check_passes_with_timeout_case(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-16",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["skill_hydration"]["total"] >= 2
    assert obj["skill_hydration"]["used_runner_total"] >= 2
    assert obj["skill_hydration"]["fallback_hint_total"] >= 1


def test_m22_10_closeout_check_fails_when_day_filter_excludes_events(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2099-01-01",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert any("skill_hydration.total" in x for x in obj["failures"])
