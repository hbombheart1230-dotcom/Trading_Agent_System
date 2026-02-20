from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.alert_notifier import build_batch_notification_payload
from libs.reporting.alert_notifier import _dedup_key_from_payload


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-7 portfolio guard notify context check.")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _batch_result(*, day: str, alert_codes: List[str], failures: Optional[List[str]] = None) -> Dict[str, Any]:
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
                "alert_total": len(alert_codes),
                "severity_total": {"warning": len(alert_codes)},
                "alert_codes": list(alert_codes),
            },
            "daily_report": {"events": 10, "path_json": "reports/m25_ops_batch/metrics_2026-02-20.json"},
        },
        "failures": list(failures or ["alert_policy rc != 0"]),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = "2026-02-20"

    primary_codes = (
        ["execution_blocked_rate_high", "broker_api_429_rate_high", "strategist_circuit_open_rate_high"]
        if bool(args.inject_fail)
        else [
            "execution_blocked_rate_high",
            "portfolio_guard_blocked_ratio_high",
            "portfolio_guard_strategy_budget_exceeded_high",
        ]
    )
    secondary_codes = ["execution_blocked_rate_high", "broker_api_429_rate_high", "strategist_circuit_open_rate_high"]

    primary_payload = build_batch_notification_payload(_batch_result(day=day, alert_codes=primary_codes))
    secondary_payload = build_batch_notification_payload(_batch_result(day=day, alert_codes=secondary_codes))
    primary_key = _dedup_key_from_payload(primary_payload)
    secondary_key = _dedup_key_from_payload(secondary_payload)

    ap = primary_payload.get("alert_policy") if isinstance(primary_payload.get("alert_policy"), dict) else {}
    pg_codes = ap.get("portfolio_guard_alert_codes") if isinstance(ap.get("portfolio_guard_alert_codes"), list) else []
    failures: List[str] = []

    if int(ap.get("portfolio_guard_alert_total") or 0) < 2:
        failures.append("portfolio_guard_alert_total < 2")
    if "portfolio_guard_blocked_ratio_high" not in pg_codes:
        failures.append("portfolio_guard_blocked_ratio_high missing")
    if "portfolio_guard_strategy_budget_exceeded_high" not in pg_codes:
        failures.append("portfolio_guard_strategy_budget_exceeded_high missing")
    if primary_key == secondary_key:
        failures.append("dedup_key unchanged across different alert codes")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": bool(args.inject_fail),
        "alert_policy": {
            "alert_total": int(ap.get("alert_total") or 0),
            "alert_codes": ap.get("alert_codes") if isinstance(ap.get("alert_codes"), list) else [],
            "portfolio_guard_alert_total": int(ap.get("portfolio_guard_alert_total") or 0),
            "portfolio_guard_alert_codes": pg_codes,
        },
        "dedup_key_changed": primary_key != secondary_key,
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} inject_fail={out['inject_fail']} "
            f"portfolio_guard_alert_total={out['alert_policy']['portfolio_guard_alert_total']} "
            f"dedup_key_changed={out['dedup_key_changed']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
