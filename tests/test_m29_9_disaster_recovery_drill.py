from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m29_disaster_recovery_drill import main as dr_main


def test_m29_9_disaster_recovery_drill_passes_default(tmp_path: Path, capsys):
    working = tmp_path / "working_dataset"
    archive = tmp_path / "archive"
    restored = tmp_path / "restored_dataset"
    reports = tmp_path / "reports"

    rc = dr_main(
        [
            "--working-dataset-root",
            str(working),
            "--archive-dir",
            str(archive),
            "--restored-dataset-root",
            str(restored),
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
    assert obj["archive_integrity"]["rc"] == 0
    assert obj["restored_replay"]["rc"] == 0
    assert obj["parity"]["ok"] is True
    assert obj["restore"]["copy_ok"] is True


def test_m29_9_disaster_recovery_drill_fails_with_injected_case(tmp_path: Path, capsys):
    working = tmp_path / "working_dataset"
    archive = tmp_path / "archive"
    restored = tmp_path / "restored_dataset"
    reports = tmp_path / "reports"

    rc = dr_main(
        [
            "--working-dataset-root",
            str(working),
            "--archive-dir",
            str(archive),
            "--restored-dataset-root",
            str(restored),
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
    assert obj["archive_integrity"]["rc"] == 3
    assert obj["archive_integrity"]["hash_mismatch_total"] >= 1
    assert obj["parity"]["ok"] is False


def test_m29_9_dr_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m29_disaster_recovery_drill.py"
    working = tmp_path / "working_dataset"
    archive = tmp_path / "archive"
    restored = tmp_path / "restored_dataset"
    reports = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--working-dataset-root",
            str(working),
            "--archive-dir",
            str(archive),
            "--restored-dataset-root",
            str(restored),
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
