from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m27_allocation_policy_check import main as m27_1_main
from scripts.run_m27_conflict_resolution_check import main as m27_2_main
from scripts.run_m27_portfolio_budget_boundary_check import main as m27_3_main
from scripts.run_m27_runtime_portfolio_guard_check import main as m27_4_main
from scripts.run_m27_portfolio_guard_metrics_check import main as m27_5_main
from scripts.run_m27_portfolio_guard_alert_policy_check import main as m27_6_main
from scripts.run_m27_portfolio_guard_notify_check import main as m27_7_main
from scripts.run_m27_portfolio_guard_notify_routing_check import main as m27_8_main
from scripts.run_m27_portfolio_guard_notify_query_check import main as m27_9_main


def _run_json(main_fn, argv: List[str]) -> Tuple[int, Dict[str, Any]]:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main_fn(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27 closeout check (allocation/conflict/guard/metrics/notify).")
    p.add_argument("--event-log-dir", default="data/logs/m27_closeout")
    p.add_argument("--report-dir", default="reports/m27_closeout")
    p.add_argument("--day", default="2026-02-20")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    event_log_dir = Path(str(args.event_log_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-20").strip()

    if not bool(args.no_clear):
        if event_log_dir.exists():
            shutil.rmtree(event_log_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)

    event_log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    m27_1_rc, m27_1 = _run_json(m27_1_main, ["--json"])
    m27_2_rc, m27_2 = _run_json(m27_2_main, ["--json"])
    m27_3_rc, m27_3 = _run_json(m27_3_main, ["--json"])
    m27_4_rc, m27_4 = _run_json(m27_4_main, ["--json"])
    m27_5_rc, m27_5 = _run_json(
        m27_5_main,
        [
            "--event-log-path",
            str(event_log_dir / "m27_5_events.jsonl"),
            "--report-dir",
            str(report_dir / "m27_5_metrics"),
            "--day",
            day,
            "--json",
        ],
    )
    m27_6_rc, m27_6 = _run_json(
        m27_6_main,
        [
            "--event-log-path",
            str(event_log_dir / "m27_6_events.jsonl"),
            "--report-dir",
            str(report_dir / "m27_6_alert"),
            "--day",
            day,
            "--json",
        ],
    )
    m27_7_rc, m27_7 = _run_json(m27_7_main, ["--json"])
    m27_8_rc, m27_8 = _run_json(m27_8_main, ["--json"])
    m27_9_argv: List[str] = [
        "--event-log-path",
        str(event_log_dir / "m27_9_notify_events.jsonl"),
        "--day",
        day,
        "--json",
    ]
    if bool(args.inject_fail):
        m27_9_argv.insert(-1, "--inject-fail")
    m27_9_rc, m27_9 = _run_json(m27_9_main, m27_9_argv)

    failures: List[str] = []
    checks = [
        ("m27_1", m27_1_rc, m27_1),
        ("m27_2", m27_2_rc, m27_2),
        ("m27_3", m27_3_rc, m27_3),
        ("m27_4", m27_4_rc, m27_4),
        ("m27_5", m27_5_rc, m27_5),
        ("m27_6", m27_6_rc, m27_6),
        ("m27_7", m27_7_rc, m27_7),
        ("m27_8", m27_8_rc, m27_8),
        ("m27_9", m27_9_rc, m27_9),
    ]
    for name, rc, obj in checks:
        if int(rc) != 0:
            failures.append(f"{name} rc != 0")
        if obj and not bool(obj.get("ok")):
            failures.append(f"{name} ok != true")

    if int(((m27_5.get("portfolio_guard") or {}).get("applied_total") or 0)) < 1:
        failures.append("m27_5 portfolio_guard.applied_total < 1")
    if int(m27_6.get("alert_policy_rc") or 0) != 0:
        failures.append("m27_6 alert_policy_rc != 0")
    if str(m27_8.get("selected_provider") or "") != "slack_webhook":
        failures.append("m27_8 selected_provider != slack_webhook")
    if int(m27_9.get("escalated_total") or 0) < 1:
        failures.append("m27_9 escalated_total < 1")

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "inject_fail": bool(args.inject_fail),
        "event_log_dir": str(event_log_dir),
        "report_dir": str(report_dir),
        "m27_1": {
            "rc": int(m27_1_rc),
            "ok": bool(m27_1.get("ok")) if isinstance(m27_1, dict) else False,
            "active_strategy_total": int(m27_1.get("active_strategy_total") or 0) if isinstance(m27_1, dict) else 0,
        },
        "m27_2": {
            "rc": int(m27_2_rc),
            "ok": bool(m27_2.get("ok")) if isinstance(m27_2, dict) else False,
            "approved_total": int(m27_2.get("approved_total") or 0) if isinstance(m27_2, dict) else 0,
            "blocked_total": int(m27_2.get("blocked_total") or 0) if isinstance(m27_2, dict) else 0,
        },
        "m27_3": {
            "rc": int(m27_3_rc),
            "ok": bool(m27_3.get("ok")) if isinstance(m27_3, dict) else False,
            "approved_total": int(((m27_3.get("guard") or {}).get("approved_total") or 0)) if isinstance(m27_3, dict) else 0,
        },
        "m27_4": {
            "rc": int(m27_4_rc),
            "ok": bool(m27_4.get("ok")) if isinstance(m27_4, dict) else False,
            "approved_intent_total": int(m27_4.get("approved_intent_total") or 0) if isinstance(m27_4, dict) else 0,
        },
        "m27_5": {
            "rc": int(m27_5_rc),
            "ok": bool(m27_5.get("ok")) if isinstance(m27_5, dict) else False,
            "applied_total": int(((m27_5.get("portfolio_guard") or {}).get("applied_total") or 0))
            if isinstance(m27_5, dict)
            else 0,
        },
        "m27_6": {
            "rc": int(m27_6_rc),
            "ok": bool(m27_6.get("ok")) if isinstance(m27_6, dict) else False,
            "alert_policy_rc": int(m27_6.get("alert_policy_rc") or 0) if isinstance(m27_6, dict) else 0,
        },
        "m27_7": {
            "rc": int(m27_7_rc),
            "ok": bool(m27_7.get("ok")) if isinstance(m27_7, dict) else False,
            "portfolio_guard_alert_total": int(((m27_7.get("alert_policy") or {}).get("portfolio_guard_alert_total") or 0))
            if isinstance(m27_7, dict)
            else 0,
        },
        "m27_8": {
            "rc": int(m27_8_rc),
            "ok": bool(m27_8.get("ok")) if isinstance(m27_8, dict) else False,
            "selected_provider": str(m27_8.get("selected_provider") or "") if isinstance(m27_8, dict) else "",
            "route_reason": str(m27_8.get("route_reason") or "") if isinstance(m27_8, dict) else "",
        },
        "m27_9": {
            "rc": int(m27_9_rc),
            "ok": bool(m27_9.get("ok")) if isinstance(m27_9, dict) else False,
            "query_total": int(m27_9.get("query_total") or 0) if isinstance(m27_9, dict) else 0,
            "escalated_total": int(m27_9.get("escalated_total") or 0) if isinstance(m27_9, dict) else 0,
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} "
            f"allocation_active={out['m27_1']['active_strategy_total']} "
            f"guard_applied={out['m27_5']['applied_total']} "
            f"notify_provider={out['m27_8']['selected_provider'] or 'n/a'} "
            f"escalated_total={out['m27_9']['escalated_total']} "
            f"failure_total={len(failures)}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
