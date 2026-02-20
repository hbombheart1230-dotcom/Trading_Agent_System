from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.runtime.runtime_profile import validate_runtime_profile
from scripts.check_runtime_profile import main as check_main
from scripts.run_m28_runtime_profile_scaffold_check import main as scaffold_main


def _write_env(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in rows.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_m28_1_validate_runtime_profile_prod_passes_with_required_keys():
    env = {
        "KIWOOM_MODE": "real",
        "DRY_RUN": "0",
        "EXECUTION_ENABLED": "true",
        "ALLOW_REAL_EXECUTION": "true",
        "EVENT_LOG_PATH": "./data/logs/prod_events.jsonl",
        "REPORT_DIR": "./reports/prod",
        "KIWOOM_APP_KEY": "demo_key",
        "KIWOOM_APP_SECRET": "demo_secret",
        "KIWOOM_ACCOUNT_NO": "12345678",
        "M25_NOTIFY_PROVIDER": "slack_webhook",
    }
    out = validate_runtime_profile("prod", env, strict=True)
    assert out["ok"] is True
    assert out["required_missing"] == []
    assert out["violations"] == []


def test_m28_1_check_runtime_profile_fails_when_prod_secret_missing(tmp_path: Path, capsys):
    env_path = tmp_path / "prod.env"
    _write_env(
        env_path,
        {
            "KIWOOM_MODE": "real",
            "DRY_RUN": "0",
            "EXECUTION_ENABLED": "true",
            "ALLOW_REAL_EXECUTION": "true",
            "EVENT_LOG_PATH": "./data/logs/prod_events.jsonl",
            "REPORT_DIR": "./reports/prod",
            "KIWOOM_APP_KEY": "demo_key",
            "KIWOOM_ACCOUNT_NO": "12345678",
            "M25_NOTIFY_PROVIDER": "slack_webhook",
        },
    )
    rc = check_main(["--profile", "prod", "--env-path", str(env_path), "--strict", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert "KIWOOM_APP_SECRET" in obj["required_missing"]


def test_m28_1_runtime_profile_scaffold_check_passes_default(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    rc = scaffold_main(["--work-dir", str(work_dir), "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["profiles"]["dev"]["ok"] is True
    assert obj["profiles"]["staging"]["ok"] is True
    assert obj["profiles"]["prod"]["ok"] is True


def test_m28_1_runtime_profile_scaffold_check_fails_injected(tmp_path: Path, capsys):
    work_dir = tmp_path / "state"
    rc = scaffold_main(["--work-dir", str(work_dir), "--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["profiles"]["prod"]["rc"] == 3
    assert "KIWOOM_APP_SECRET" in (obj["profiles"]["prod"]["required_missing"] or [])


def test_m28_1_scaffold_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_runtime_profile_scaffold_check.py"
    work_dir = tmp_path / "state"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--work-dir",
            str(work_dir),
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
