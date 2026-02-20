from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m29_closeout_check import main as m29_closeout_main


def test_m29_10_closeout_check_passes_default(tmp_path: Path, capsys):
    event_log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"

    rc = m29_closeout_main(
        [
            "--event-log-dir",
            str(event_log_dir),
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
    assert obj["m29_5_audit"]["rc"] == 0
    assert obj["m29_6_archive_integrity"]["rc"] == 0
    assert obj["m29_7_timeline"]["rc"] == 0
    assert obj["m29_8_disaster_recovery"]["rc"] == 0
    assert obj["failure_total"] == 0


def test_m29_10_closeout_check_fails_with_injected_case(tmp_path: Path, capsys):
    event_log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"

    rc = m29_closeout_main(
        [
            "--event-log-dir",
            str(event_log_dir),
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
    assert obj["failure_total"] >= 0
    assert (
        obj["m29_5_audit"]["rc"] == 3
        or obj["m29_6_archive_integrity"]["rc"] == 3
        or obj["m29_7_timeline"]["rc"] == 3
        or obj["m29_8_disaster_recovery"]["rc"] == 3
    )


def test_m29_10_closeout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m29_closeout_check.py"
    event_log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-dir",
            str(event_log_dir),
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
