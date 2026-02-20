from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m27_portfolio_guard_metrics_check import main as metrics_check_main


def test_m27_5_portfolio_guard_metrics_check_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = metrics_check_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-20",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["portfolio_guard"]["applied_total"] >= 1
    assert obj["portfolio_guard"]["blocked_total_sum"] >= 1
    assert any(x["reason"] == "strategy_budget_exceeded" for x in obj["portfolio_guard"]["blocked_reason_topN"])


def test_m27_5_portfolio_guard_metrics_check_fails_with_injected_case(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    rc = metrics_check_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
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
    assert obj["failure_total"] >= 1


def test_m27_5_metrics_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_portfolio_guard_metrics_check.py"
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
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
