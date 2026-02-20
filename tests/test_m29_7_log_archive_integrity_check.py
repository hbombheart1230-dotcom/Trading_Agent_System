from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m29_log_archive_integrity_check import main as archive_check_main


def test_m29_7_log_archive_integrity_check_passes_default(tmp_path: Path, capsys):
    archive_dir = tmp_path / "archive"
    reports = tmp_path / "reports"

    rc = archive_check_main(
        [
            "--archive-dir",
            str(archive_dir),
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
    assert obj["integrity"]["rc"] == 0
    assert obj["integrity"]["verified_total"] >= 1
    assert obj["integrity"]["hash_mismatch_total"] == 0
    assert obj["integrity"]["stale_archive_total"] == 0


def test_m29_7_log_archive_integrity_check_fails_with_injected_case(tmp_path: Path, capsys):
    archive_dir = tmp_path / "archive"
    reports = tmp_path / "reports"

    rc = archive_check_main(
        [
            "--archive-dir",
            str(archive_dir),
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
    assert obj["integrity"]["rc"] == 3
    assert obj["integrity"]["hash_mismatch_total"] >= 1
    assert obj["integrity"]["stale_archive_total"] >= 1


def test_m29_7_archive_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m29_log_archive_integrity_check.py"
    archive_dir = tmp_path / "archive"
    reports = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--archive-dir",
            str(archive_dir),
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
