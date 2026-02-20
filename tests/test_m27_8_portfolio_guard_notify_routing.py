from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m27_portfolio_guard_notify_routing_check import main as check_main


def test_m27_8_notify_routing_check_passes_default(capsys):
    rc = check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["selected_provider"] == "slack_webhook"
    assert obj["route_reason"] == "portfolio_guard_escalation"


def test_m27_8_notify_routing_check_fails_injected(capsys):
    rc = check_main(["--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1


def test_m27_8_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_portfolio_guard_notify_routing_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
