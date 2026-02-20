from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from scripts.generate_metrics_report import generate_metrics_report

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return float(default)
    return _to_float(raw, float(default))


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return int(default)
    return _to_int(raw, int(default))


def _env_fail_on(default: str = "critical") -> str:
    raw = str(os.getenv("ALERT_POLICY_FAIL_ON", "") or "").strip().lower()
    if raw in ("none", "warning", "critical"):
        return raw
    return str(default)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check alert policy threshold gates from metrics schema v1.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/metrics")
    p.add_argument("--day", default=None)
    p.add_argument("--metrics-json-path", default="")

    p.add_argument(
        "--llm-success-rate-min",
        type=float,
        default=_env_float("ALERT_POLICY_LLM_SUCCESS_RATE_MIN", 0.70),
    )
    p.add_argument(
        "--llm-circuit-open-rate-max",
        type=float,
        default=_env_float("ALERT_POLICY_LLM_CIRCUIT_OPEN_RATE_MAX", 0.30),
    )
    p.add_argument(
        "--execution-blocked-rate-max",
        type=float,
        default=_env_float("ALERT_POLICY_EXECUTION_BLOCKED_RATE_MAX", 0.60),
    )
    p.add_argument(
        "--execution-approved-executed-gap-max",
        type=int,
        default=_env_int("ALERT_POLICY_EXECUTION_APPROVED_EXECUTED_GAP_MAX", 0),
    )
    p.add_argument(
        "--api-429-rate-max",
        type=float,
        default=_env_float("ALERT_POLICY_API_429_RATE_MAX", 0.20),
    )
    p.add_argument(
        "--portfolio-guard-blocked-ratio-max",
        type=float,
        default=_env_float("ALERT_POLICY_PORTFOLIO_GUARD_BLOCKED_RATIO_MAX", 0.70),
    )
    p.add_argument(
        "--portfolio-guard-strategy-budget-exceeded-max",
        type=int,
        default=_env_int("ALERT_POLICY_PORTFOLIO_GUARD_STRATEGY_BUDGET_EXCEEDED_MAX", 20),
    )

    p.add_argument("--fail-on", choices=["none", "warning", "critical"], default=_env_fail_on("critical"))
    p.add_argument("--json", action="store_true")
    return p


def _load_metrics(args: argparse.Namespace) -> tuple[int, Dict[str, Any], str]:
    raw_metrics_path = str(args.metrics_json_path or "").strip()
    if raw_metrics_path:
        path = Path(raw_metrics_path)
        if not path.exists():
            return 2, {}, str(path)
        try:
            return 0, json.loads(path.read_text(encoding="utf-8")), str(path)
        except Exception:
            return 2, {}, str(path)

    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)
    _, js = generate_metrics_report(events_path, report_dir, day=args.day)
    try:
        return 0, json.loads(js.read_text(encoding="utf-8")), str(js)
    except Exception:
        return 2, {}, str(js)


def _evaluate_alerts(metrics: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    strategist = metrics.get("strategist_llm") if isinstance(metrics.get("strategist_llm"), dict) else {}
    execution = metrics.get("execution") if isinstance(metrics.get("execution"), dict) else {}
    broker_api = metrics.get("broker_api") if isinstance(metrics.get("broker_api"), dict) else {}
    portfolio_guard = metrics.get("portfolio_guard") if isinstance(metrics.get("portfolio_guard"), dict) else {}

    llm_success_rate = _to_float(strategist.get("success_rate"), 0.0)
    llm_circuit_open_rate = _to_float(strategist.get("circuit_open_rate"), 0.0)

    created = _to_int(execution.get("intents_created"), _to_int(metrics.get("intents_created_total"), 0))
    approved = _to_int(execution.get("intents_approved"), _to_int(metrics.get("intents_approved_total"), 0))
    blocked = _to_int(execution.get("intents_blocked"), _to_int(metrics.get("intents_blocked_total"), 0))
    executed = _to_int(execution.get("intents_executed"), _to_int(metrics.get("intents_executed_total"), 0))

    denom = max(1, created)
    blocked_rate = float(blocked) / float(denom)
    approved_executed_gap = max(0, approved - executed)
    api_429_rate = _to_float(broker_api.get("api_429_rate"), 0.0)
    portfolio_guard_applied_total = _to_int(portfolio_guard.get("applied_total"), 0)
    portfolio_guard_approved_total_sum = _to_int(portfolio_guard.get("approved_total_sum"), 0)
    portfolio_guard_blocked_total_sum = _to_int(portfolio_guard.get("blocked_total_sum"), 0)
    portfolio_guard_den = portfolio_guard_approved_total_sum + portfolio_guard_blocked_total_sum
    portfolio_guard_blocked_ratio = (
        float(portfolio_guard_blocked_total_sum) / float(portfolio_guard_den) if portfolio_guard_den > 0 else 0.0
    )
    portfolio_guard_reason_total = (
        portfolio_guard.get("blocked_reason_total") if isinstance(portfolio_guard.get("blocked_reason_total"), dict) else {}
    )
    portfolio_guard_strategy_budget_exceeded = _to_int(portfolio_guard_reason_total.get("strategy_budget_exceeded"), 0)

    alerts: List[Dict[str, Any]] = []

    if llm_success_rate < float(args.llm_success_rate_min):
        alerts.append(
            {
                "severity": "critical",
                "code": "strategist_success_rate_low",
                "value": llm_success_rate,
                "threshold": float(args.llm_success_rate_min),
            }
        )

    if llm_circuit_open_rate > float(args.llm_circuit_open_rate_max):
        alerts.append(
            {
                "severity": "critical",
                "code": "strategist_circuit_open_rate_high",
                "value": llm_circuit_open_rate,
                "threshold": float(args.llm_circuit_open_rate_max),
            }
        )

    if blocked_rate > float(args.execution_blocked_rate_max):
        alerts.append(
            {
                "severity": "warning",
                "code": "execution_blocked_rate_high",
                "value": blocked_rate,
                "threshold": float(args.execution_blocked_rate_max),
                "created": int(created),
                "blocked": int(blocked),
            }
        )

    if approved_executed_gap > int(args.execution_approved_executed_gap_max):
        alerts.append(
            {
                "severity": "critical",
                "code": "execution_approved_executed_gap_high",
                "value": int(approved_executed_gap),
                "threshold": int(args.execution_approved_executed_gap_max),
                "approved": int(approved),
                "executed": int(executed),
            }
        )

    if api_429_rate > float(args.api_429_rate_max):
        alerts.append(
            {
                "severity": "warning",
                "code": "broker_api_429_rate_high",
                "value": api_429_rate,
                "threshold": float(args.api_429_rate_max),
            }
        )

    if portfolio_guard_applied_total > 0 and portfolio_guard_blocked_ratio > float(args.portfolio_guard_blocked_ratio_max):
        alerts.append(
            {
                "severity": "warning",
                "code": "portfolio_guard_blocked_ratio_high",
                "value": float(portfolio_guard_blocked_ratio),
                "threshold": float(args.portfolio_guard_blocked_ratio_max),
                "portfolio_guard_applied_total": int(portfolio_guard_applied_total),
                "portfolio_guard_approved_total_sum": int(portfolio_guard_approved_total_sum),
                "portfolio_guard_blocked_total_sum": int(portfolio_guard_blocked_total_sum),
            }
        )

    if portfolio_guard_strategy_budget_exceeded > int(args.portfolio_guard_strategy_budget_exceeded_max):
        alerts.append(
            {
                "severity": "warning",
                "code": "portfolio_guard_strategy_budget_exceeded_high",
                "value": int(portfolio_guard_strategy_budget_exceeded),
                "threshold": int(args.portfolio_guard_strategy_budget_exceeded_max),
                "portfolio_guard_applied_total": int(portfolio_guard_applied_total),
            }
        )

    fail_on = str(args.fail_on or "critical").strip().lower()
    fail_rank = _SEVERITY_RANK.get(fail_on, _SEVERITY_RANK["critical"])
    should_fail = any(_SEVERITY_RANK.get(str(a.get("severity") or ""), -1) >= fail_rank for a in alerts)
    if fail_on == "none":
        should_fail = False

    severity_total: Dict[str, int] = {}
    for a in alerts:
        sev = str(a.get("severity") or "unknown")
        severity_total[sev] = int(severity_total.get(sev, 0)) + 1

    return {
        "ok": not should_fail,
        "fail_on": fail_on,
        "alert_total": len(alerts),
        "severity_total": severity_total,
        "alerts": alerts,
        "values": {
            "llm_success_rate": llm_success_rate,
            "llm_circuit_open_rate": llm_circuit_open_rate,
            "execution_blocked_rate": blocked_rate,
            "execution_approved_executed_gap": int(approved_executed_gap),
            "api_429_rate": api_429_rate,
            "portfolio_guard_blocked_ratio": float(portfolio_guard_blocked_ratio),
            "portfolio_guard_strategy_budget_exceeded_total": int(portfolio_guard_strategy_budget_exceeded),
        },
        "thresholds": {
            "llm_success_rate_min": float(args.llm_success_rate_min),
            "llm_circuit_open_rate_max": float(args.llm_circuit_open_rate_max),
            "execution_blocked_rate_max": float(args.execution_blocked_rate_max),
            "execution_approved_executed_gap_max": int(args.execution_approved_executed_gap_max),
            "api_429_rate_max": float(args.api_429_rate_max),
            "portfolio_guard_blocked_ratio_max": float(args.portfolio_guard_blocked_ratio_max),
            "portfolio_guard_strategy_budget_exceeded_max": int(args.portfolio_guard_strategy_budget_exceeded_max),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    # Load default .env profile before argument defaults are resolved.
    load_env_file(".env")
    args = _build_parser().parse_args(argv)
    rc, metrics, metrics_path = _load_metrics(args)
    if rc != 0:
        print(f"ERROR: failed to load metrics json: {metrics_path}")
        return rc

    out = _evaluate_alerts(metrics, args)
    out["schema_version"] = str(metrics.get("schema_version") or "")
    out["metrics_json_path"] = str(metrics_path)

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} fail_on={out['fail_on']} alert_total={out['alert_total']} "
            f"warning_total={out['severity_total'].get('warning', 0)} "
            f"critical_total={out['severity_total'].get('critical', 0)}"
        )
        for a in out["alerts"]:
            print(
                f"{a.get('severity')} code={a.get('code')} "
                f"value={a.get('value')} threshold={a.get('threshold')}"
            )

    return 0 if bool(out["ok"]) else 3


if __name__ == "__main__":
    raise SystemExit(main())
