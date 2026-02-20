from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m29_incident_timeline_check import main as timeline_check_main


def test_m29_8_incident_timeline_check_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = timeline_check_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["timeline"]["rc"] == 0
    assert obj["timeline"]["incident_total"] >= 2
    assert obj["timeline"]["unresolved_incident_total"] == 0


def test_m29_8_incident_timeline_check_fails_with_injected_case(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = timeline_check_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--inject-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["timeline"]["rc"] == 3
    assert obj["timeline"]["unresolved_incident_total"] >= 1


def test_m29_8_timeline_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m29_incident_timeline_check.py"
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
