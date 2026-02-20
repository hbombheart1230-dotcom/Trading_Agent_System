from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m27_closeout_check import main as closeout_main


def test_m27_10_closeout_check_passes_default(tmp_path: Path, capsys):
    event_log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"

    rc = closeout_main(
        [
            "--event-log-dir",
            str(event_log_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-20",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["m27_1"]["rc"] == 0
    assert obj["m27_5"]["applied_total"] >= 1
    assert obj["m27_6"]["alert_policy_rc"] == 0
    assert obj["m27_8"]["selected_provider"] == "slack_webhook"
    assert obj["m27_9"]["escalated_total"] >= 1


def test_m27_10_closeout_check_fails_with_injected_case(tmp_path: Path, capsys):
    event_log_dir = tmp_path / "logs"
    report_dir = tmp_path / "reports"

    rc = closeout_main(
        [
            "--event-log-dir",
            str(event_log_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-20",
            "--inject-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["m27_9"]["rc"] == 3
    assert any("m27_9" in x for x in obj["failures"])


def test_m27_10_closeout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_closeout_check.py"
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
            "2026-02-20",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
