from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m28_registration_helper_check import main as registration_main


def test_m28_8_registration_helper_check_passes_default(tmp_path: Path, capsys):
    output_dir = tmp_path / "helpers"
    template_dir = tmp_path / "templates"
    report_dir = tmp_path / "reports"

    # Minimal launch template placeholders referenced by registration helpers.
    (template_dir / "windows").mkdir(parents=True, exist_ok=True)
    (template_dir / "linux").mkdir(parents=True, exist_ok=True)
    (template_dir / "windows" / "scheduler_task.xml").write_text("<Task/>", encoding="utf-8")
    (template_dir / "windows" / "worker_task.xml").write_text("<Task/>", encoding="utf-8")
    (template_dir / "linux" / "scheduler.service").write_text("[Service]\n", encoding="utf-8")
    (template_dir / "linux" / "worker.service").write_text("[Service]\n", encoding="utf-8")

    rc = registration_main(
        [
            "--output-dir",
            str(output_dir),
            "--template-dir",
            str(template_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-21",
            "--profile",
            "dev",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["required_fail_total"] == 0
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m28_8_registration_helper_check_fails_with_injected_case(tmp_path: Path, capsys):
    output_dir = tmp_path / "helpers"
    template_dir = tmp_path / "templates"
    report_dir = tmp_path / "reports"
    (template_dir / "windows").mkdir(parents=True, exist_ok=True)
    (template_dir / "linux").mkdir(parents=True, exist_ok=True)

    rc = registration_main(
        [
            "--output-dir",
            str(output_dir),
            "--template-dir",
            str(template_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-21",
            "--profile",
            "dev",
            "--inject-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["required_fail_total"] >= 1
    assert "check_failed:windows_worker_register_ref" in (obj["failures"] or [])
    assert "check_failed:linux_worker_register_ref" in (obj["failures"] or [])


def test_m28_8_registration_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_registration_helper_check.py"
    output_dir = tmp_path / "helpers"
    template_dir = tmp_path / "templates"
    report_dir = tmp_path / "reports"
    (template_dir / "windows").mkdir(parents=True, exist_ok=True)
    (template_dir / "linux").mkdir(parents=True, exist_ok=True)
    (template_dir / "windows" / "scheduler_task.xml").write_text("<Task/>", encoding="utf-8")
    (template_dir / "windows" / "worker_task.xml").write_text("<Task/>", encoding="utf-8")
    (template_dir / "linux" / "scheduler.service").write_text("[Service]\n", encoding="utf-8")
    (template_dir / "linux" / "worker.service").write_text("[Service]\n", encoding="utf-8")

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-dir",
            str(output_dir),
            "--template-dir",
            str(template_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            "2026-02-21",
            "--profile",
            "dev",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
