from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.alert_notifier import notify_batch_result


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-8 portfolio guard notify routing check.")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _batch_result(*, day: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "rc": 3,
        "day": day,
        "started_ts": f"{day}T00:00:00+00:00",
        "finished_ts": f"{day}T00:00:10+00:00",
        "duration_sec": 10,
        "closeout": {
            "metrics_schema": {"ok": True, "rc": 0, "failure_total": 0},
            "alert_policy": {
                "ok": False,
                "rc": 3,
                "alert_total": 3,
                "severity_total": {"warning": 3},
                "alert_codes": [
                    "execution_blocked_rate_high",
                    "portfolio_guard_blocked_ratio_high",
                    "portfolio_guard_strategy_budget_exceeded_high",
                ],
            },
            "daily_report": {"events": 12, "path_json": "reports/m25_ops_batch/metrics_2026-02-20.json"},
        },
        "failures": ["alert_policy rc != 0"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    inject_fail = bool(args.inject_fail)

    out = notify_batch_result(
        batch_result=_batch_result(day="2026-02-20"),
        provider="webhook",
        webhook_url="https://example.invalid/default",
        notify_on="always",
        timeout_sec=5,
        dry_run=True,
        portfolio_guard_escalation_min=99 if inject_fail else 1,
        portfolio_guard_provider="slack_webhook",
        portfolio_guard_webhook_url="https://example.invalid/portfolio-guard",
    )

    failures: List[str] = []
    if str(out.get("selected_provider") or "") != "slack_webhook":
        failures.append("selected_provider != slack_webhook")
    if str(out.get("route_reason") or "") != "portfolio_guard_escalation":
        failures.append("route_reason != portfolio_guard_escalation")
    if bool(out.get("escalated")) is not True:
        failures.append("escalated != true")
    if str(out.get("reason") or "") != "dry_run":
        failures.append("reason != dry_run")

    result = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "selected_provider": str(out.get("selected_provider") or ""),
        "route_reason": str(out.get("route_reason") or ""),
        "portfolio_guard_alert_total": int(out.get("portfolio_guard_alert_total") or 0),
        "escalated": bool(out.get("escalated")),
        "notify_reason": str(out.get("reason") or ""),
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            f"ok={result['ok']} inject_fail={result['inject_fail']} "
            f"selected_provider={result['selected_provider']} route_reason={result['route_reason']} "
            f"portfolio_guard_alert_total={result['portfolio_guard_alert_total']} "
            f"failure_total={result['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
