from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m30_post_golive_monitoring_policy import main as policy_main


def test_m30_3_post_golive_policy_passes_default(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"

    rc = policy_main(
        [
            "--event-log-dir",
            str(logs),
            "--quality-report-dir",
            str(quality_reports),
            "--signoff-report-dir",
            str(signoff_reports),
            "--report-dir",
            str(policy_reports),
            "--day",
            "2026-02-21",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["release_ready"] is True
    assert obj["escalation_level"] == "normal"
    assert obj["policy"]["manual_approval_only"] is False
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m30_3_post_golive_policy_fails_with_injected_case(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"

    rc = policy_main(
        [
            "--event-log-dir",
            str(logs),
            "--quality-report-dir",
            str(quality_reports),
            "--signoff-report-dir",
            str(signoff_reports),
            "--report-dir",
            str(policy_reports),
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
    assert obj["release_ready"] is False
    assert obj["escalation_level"] in ("watch", "incident")
    assert obj["policy"]["manual_approval_only"] is True


def test_m30_3_policy_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m30_post_golive_monitoring_policy.py"
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-dir",
            str(logs),
            "--quality-report-dir",
            str(quality_reports),
            "--signoff-report-dir",
            str(signoff_reports),
            "--report-dir",
            str(policy_reports),
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
