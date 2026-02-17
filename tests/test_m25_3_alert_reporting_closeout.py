from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m25_closeout_check import main as closeout_main


def test_m25_3_closeout_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = closeout_main(
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
    assert obj["metrics_schema"]["rc"] == 0
    assert obj["alert_policy"]["rc"] == 0
    assert obj["daily_report"]["events"] >= 1
    assert Path(obj["alert_report"]["path_json"]).exists()
    assert Path(obj["alert_report"]["path_md"]).exists()


def test_m25_3_closeout_fails_when_critical_injected(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-17",
            "--inject-critical-case",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["alert_policy"]["rc"] == 3
    assert obj["alert_policy"]["severity_total"]["critical"] >= 1
    assert any("alert_policy" in x for x in obj["failures"])
