from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m30_final_golive_signoff import main as final_main


def test_m30_4_final_golive_signoff_passes_default(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"
    final_reports = tmp_path / "final_reports"

    rc = final_main(
        [
            "--event-log-dir",
            str(logs),
            "--quality-report-dir",
            str(quality_reports),
            "--signoff-report-dir",
            str(signoff_reports),
            "--policy-report-dir",
            str(policy_reports),
            "--report-dir",
            str(final_reports),
            "--day",
            "2026-02-21",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["approved"] is True
    assert obj["go_live_decision"] == "approve_go_live"
    assert obj["m30_1_quality_gates"]["ok"] is True
    assert obj["m30_2_signoff"]["release_ready"] is True
    assert obj["m30_3_policy"]["escalation_level"] == "normal"
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m30_4_final_golive_signoff_fails_with_injected_case(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"
    final_reports = tmp_path / "final_reports"

    rc = final_main(
        [
            "--event-log-dir",
            str(logs),
            "--quality-report-dir",
            str(quality_reports),
            "--signoff-report-dir",
            str(signoff_reports),
            "--policy-report-dir",
            str(policy_reports),
            "--report-dir",
            str(final_reports),
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
    assert obj["approved"] is False
    assert obj["go_live_decision"] == "hold_go_live"
    assert (
        obj["m30_1_quality_gates"]["ok"] is False
        or obj["m30_2_signoff"]["release_ready"] is False
        or obj["m30_3_policy"]["escalation_level"] != "normal"
    )


def test_m30_4_final_signoff_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m30_final_golive_signoff.py"
    logs = tmp_path / "logs"
    quality_reports = tmp_path / "quality_reports"
    signoff_reports = tmp_path / "signoff_reports"
    policy_reports = tmp_path / "policy_reports"
    final_reports = tmp_path / "final_reports"

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
            "--policy-report-dir",
            str(policy_reports),
            "--report-dir",
            str(final_reports),
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
