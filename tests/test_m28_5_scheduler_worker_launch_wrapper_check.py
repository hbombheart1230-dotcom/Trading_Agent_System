from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m28_scheduler_worker_launch_wrapper_check import main as wrapper_main


def _write_env(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in rows.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_m28_5_scheduler_worker_launch_wrapper_check_passes_default(tmp_path: Path, capsys):
    env_path = tmp_path / "dev.env"
    state_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "dev",
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
            "EXECUTION_ENABLED": "false",
            "ALLOW_REAL_EXECUTION": "false",
            "EVENT_LOG_PATH": "./data/logs/dev_events.jsonl",
            "REPORT_DIR": "./reports/dev",
            "M25_NOTIFY_PROVIDER": "none",
        },
    )

    rc = wrapper_main(
        [
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-dir",
            str(state_dir),
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
    assert obj["roles"]["scheduler"]["ok"] is True
    assert obj["roles"]["worker"]["ok"] is True
    assert obj["required_fail_total"] == 0
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m28_5_scheduler_worker_launch_wrapper_check_fails_with_injected_case(tmp_path: Path, capsys):
    env_path = tmp_path / "dev.env"
    state_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"
    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "dev",
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
            "EXECUTION_ENABLED": "false",
            "ALLOW_REAL_EXECUTION": "false",
            "EVENT_LOG_PATH": "./data/logs/dev_events.jsonl",
            "REPORT_DIR": "./reports/dev",
        },
    )

    rc = wrapper_main(
        [
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-dir",
            str(state_dir),
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
    assert obj["roles"]["scheduler"]["ok"] is True
    assert obj["roles"]["worker"]["ok"] is False
    assert obj["required_fail_total"] >= 1
    assert "check_failed:worker_preflight_green" in (obj["failures"] or [])


def test_m28_5_wrapper_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_scheduler_worker_launch_wrapper_check.py"
    env_path = tmp_path / "dev.env"
    state_dir = tmp_path / "state"
    report_dir = tmp_path / "reports"

    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "dev",
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
            "EXECUTION_ENABLED": "false",
            "ALLOW_REAL_EXECUTION": "false",
            "EVENT_LOG_PATH": "./data/logs/dev_events.jsonl",
            "REPORT_DIR": "./reports/dev",
        },
    )

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--profile",
            "dev",
            "--env-path",
            str(env_path),
            "--state-dir",
            str(state_dir),
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
