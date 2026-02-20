from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m28_rollout_rollback_check import main as rollout_main


def test_m28_3_rollout_rollback_check_passes_default(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    rc = rollout_main(
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
    assert obj["go_no_go"] == "go"
    assert obj["required_fail_total"] == 0
    assert obj["rollback_ready"] is True
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m28_3_rollout_rollback_check_fails_with_injected_case(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    rc = rollout_main(
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
    assert obj["go_no_go"] == "hold"
    assert obj["required_fail_total"] >= 1


def test_m28_3_rollout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_rollout_rollback_check.py"
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
