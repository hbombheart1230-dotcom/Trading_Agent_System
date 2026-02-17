from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_m23_closeout_check import main as closeout_main


def test_m23_10_closeout_check_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            day,
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["resilience_closeout"]["rc"] == 0
    assert obj["commander_resilience"]["total"] >= 1
    assert obj["commander_resilience"]["cooldown_transition_total"] >= 1
    assert obj["commander_resilience"]["intervention_total"] >= 1
    assert obj["commander_resilience"]["error_total"] >= 1


def test_m23_10_closeout_check_fails_when_day_filter_excludes_events(tmp_path: Path, capsys):
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
    assert any("commander_resilience.total" in x for x in obj["failures"])


def test_m23_10_closeout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m23_closeout_check.py"
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
            "2026-02-17",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
