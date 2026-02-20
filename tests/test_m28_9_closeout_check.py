from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m28_closeout_check import main as m28_closeout_main


def test_m28_9_closeout_check_passes_default(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    rc = m28_closeout_main(
        [
            "--work-dir",
            str(work_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-21",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["m28_1_profile"]["rc"] == 0
    assert obj["m28_2_lifecycle"]["rc"] == 0
    assert obj["m28_3_rollout"]["rc"] == 0
    assert obj["m28_4_preflight"]["rc"] == 0
    assert obj["m28_5_scheduler_worker"]["rc"] == 0
    assert obj["m28_6_launch_hook"]["rc"] == 0
    assert obj["m28_7_templates"]["rc"] == 0
    assert obj["m28_8_registration_helpers"]["rc"] == 0
    assert obj["failure_total"] == 0


def test_m28_9_closeout_check_fails_with_injected_case(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    rc = m28_closeout_main(
        [
            "--work-dir",
            str(work_dir),
            "--report-dir",
            str(report_dir),
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
    assert obj["m28_8_registration_helpers"]["rc"] == 3
    assert obj["failure_total"] >= 0


def test_m28_9_closeout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_closeout_check.py"
    work_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--work-dir",
            str(work_dir),
            "--report-dir",
            str(report_dir),
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
