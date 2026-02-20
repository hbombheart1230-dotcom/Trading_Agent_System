from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.check_alert_policy_v1 import main as alert_main
from scripts.run_m27_portfolio_guard_alert_policy_check import main as check_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_m27_6_alert_policy_warns_on_portfolio_guard_blocked_ratio(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-20T00:00:00+00:00",
                "run_id": "r1",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
            {
                "ts": "2026-02-20T00:00:01+00:00",
                "run_id": "r1",
                "stage": "commander_router",
                "event": "end",
                "payload": {
                    "status": "ok",
                    "path": "graph_spine",
                    "portfolio_guard": {
                        "applied": True,
                        "approved_total": 1,
                        "blocked_total": 9,
                        "blocked_reason_counts": {"strategy_budget_exceeded": 9},
                    },
                },
            },
        ],
    )

    rc = alert_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-20",
            "--portfolio-guard-blocked-ratio-max",
            "0.50",
            "--portfolio-guard-strategy-budget-exceeded-max",
            "100",
            "--fail-on",
            "warning",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    codes = {str(x.get("code") or "") for x in obj.get("alerts", []) if isinstance(x, dict)}

    assert rc == 3
    assert obj["ok"] is False
    assert "portfolio_guard_blocked_ratio_high" in codes
    assert "portfolio_guard_strategy_budget_exceeded_high" not in codes


def test_m27_6_alert_policy_warns_on_strategy_budget_exceeded_spike(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    _write_jsonl(
        events,
        [
            {
                "ts": "2026-02-20T00:00:00+00:00",
                "run_id": "r1",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
            {
                "ts": "2026-02-20T00:00:01+00:00",
                "run_id": "r1",
                "stage": "commander_router",
                "event": "end",
                "payload": {
                    "status": "ok",
                    "path": "graph_spine",
                    "portfolio_guard": {
                        "applied": True,
                        "approved_total": 95,
                        "blocked_total": 5,
                        "blocked_reason_counts": {"strategy_budget_exceeded": 5},
                    },
                },
            },
        ],
    )

    rc = alert_main(
        [
            "--event-log-path",
            str(events),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-20",
            "--portfolio-guard-blocked-ratio-max",
            "0.90",
            "--portfolio-guard-strategy-budget-exceeded-max",
            "3",
            "--fail-on",
            "warning",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    codes = {str(x.get("code") or "") for x in obj.get("alerts", []) if isinstance(x, dict)}

    assert rc == 3
    assert obj["ok"] is False
    assert "portfolio_guard_strategy_budget_exceeded_high" in codes


def test_m27_6_portfolio_guard_alert_policy_check_script_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    rc = check_main(
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
    assert obj["alert_policy_rc"] == 0


def test_m27_6_portfolio_guard_alert_policy_check_script_fails_injected(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    rc = check_main(
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
    assert rc == 0
    assert obj["ok"] is True
    assert obj["alert_policy_rc"] == 3
    assert "portfolio_guard_blocked_ratio_high" in obj["alert_codes"]
    assert "portfolio_guard_strategy_budget_exceeded_high" in obj["alert_codes"]


def test_m27_6_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_portfolio_guard_alert_policy_check.py"
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
