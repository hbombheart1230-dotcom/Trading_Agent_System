from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m29_audit_trail_check import main as m29_audit_main


def test_m29_6_audit_trail_check_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = m29_audit_main(
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
    assert obj["audit"]["rc"] == 0
    assert obj["audit"]["linked_complete_run_total"] >= 2
    assert obj["audit"]["missing_execution_start_total"] == 0
    assert obj["audit"]["missing_execution_payload_total"] == 0
    assert obj["audit"]["orphan_execution_run_total"] == 0


def test_m29_6_audit_trail_check_fails_with_injected_case(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = m29_audit_main(
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
    assert obj["audit"]["rc"] == 3
    assert obj["audit"]["missing_execution_payload_total"] >= 1
    assert obj["audit"]["orphan_execution_run_total"] >= 1


def test_m29_6_audit_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m29_audit_trail_check.py"
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
