from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import libs.reporting.alert_notifier as notifier
from scripts.run_m27_portfolio_guard_notify_check import main as check_main


def _batch_result(alert_codes: list[str]) -> dict:
    return {
        "ok": False,
        "rc": 3,
        "day": "2026-02-20",
        "closeout": {
            "metrics_schema": {"ok": True, "rc": 0, "failure_total": 0},
            "alert_policy": {
                "ok": False,
                "rc": 3,
                "alert_total": len(alert_codes),
                "severity_total": {"warning": len(alert_codes)},
                "alert_codes": list(alert_codes),
            },
            "daily_report": {"events": 10, "path_json": "reports/sample.json"},
        },
        "failures": ["alert_policy rc != 0"],
    }


def test_m27_7_batch_notification_payload_includes_portfolio_guard_alert_context():
    payload = notifier.build_batch_notification_payload(
        _batch_result(
            [
                "execution_blocked_rate_high",
                "portfolio_guard_blocked_ratio_high",
                "portfolio_guard_strategy_budget_exceeded_high",
            ]
        )
    )
    ap = payload["alert_policy"]
    assert ap["alert_total"] == 3
    assert ap["portfolio_guard_alert_total"] == 2
    assert set(ap["portfolio_guard_alert_codes"]) == {
        "portfolio_guard_blocked_ratio_high",
        "portfolio_guard_strategy_budget_exceeded_high",
    }


def test_m27_7_dedup_key_changes_with_portfolio_guard_alert_code_delta():
    payload_a = notifier.build_batch_notification_payload(
        _batch_result(
            [
                "execution_blocked_rate_high",
                "portfolio_guard_blocked_ratio_high",
                "portfolio_guard_strategy_budget_exceeded_high",
            ]
        )
    )
    payload_b = notifier.build_batch_notification_payload(
        _batch_result(
            [
                "execution_blocked_rate_high",
                "broker_api_429_rate_high",
                "strategist_circuit_open_rate_high",
            ]
        )
    )
    key_a = notifier._dedup_key_from_payload(payload_a)
    key_b = notifier._dedup_key_from_payload(payload_b)
    assert key_a != key_b


def test_m27_7_portfolio_guard_notify_check_script_passes_default(capsys):
    rc = check_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["alert_policy"]["portfolio_guard_alert_total"] == 2


def test_m27_7_portfolio_guard_notify_check_script_fails_injected(capsys):
    rc = check_main(["--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1


def test_m27_7_script_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m27_portfolio_guard_notify_check.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
