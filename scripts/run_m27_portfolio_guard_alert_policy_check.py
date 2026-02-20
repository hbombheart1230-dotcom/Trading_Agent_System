from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_alert_policy_v1 import main as alert_policy_main


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _seed_events(path: Path, *, day: str, inject_fail: bool) -> None:
    if inject_fail:
        rows = [
            {
                "ts": f"{day}T00:00:00+00:00",
                "run_id": "r1",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
            },
            {
                "ts": f"{day}T00:00:01+00:00",
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
        ]
        _write_jsonl(path, rows)
        return

    rows = [
        {
            "ts": f"{day}T00:00:00+00:00",
            "run_id": "r1",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": True, "latency_ms": 100, "attempts": 1, "circuit_state": "closed"},
        },
        {
            "ts": f"{day}T00:00:01+00:00",
            "run_id": "r1",
            "stage": "commander_router",
            "event": "end",
            "payload": {
                "status": "ok",
                "path": "graph_spine",
                "portfolio_guard": {
                    "applied": True,
                    "approved_total": 8,
                    "blocked_total": 2,
                    "blocked_reason_counts": {"strategy_budget_exceeded": 2},
                },
            },
        },
    ]
    _write_jsonl(path, rows)


def _run_alert_json(argv: List[str]) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = alert_policy_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-6 portfolio guard alert policy check.")
    p.add_argument("--event-log-path", default="data/logs/m27_portfolio_guard_alert_events.jsonl")
    p.add_argument("--report-dir", default="reports/m27_portfolio_guard_alert")
    p.add_argument("--day", default="2026-02-20")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-20").strip()

    _seed_events(events_path, day=day, inject_fail=bool(args.inject_fail))

    rc, obj = _run_alert_json(
        [
            "--event-log-path",
            str(events_path),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--portfolio-guard-blocked-ratio-max",
            "0.50",
            "--portfolio-guard-strategy-budget-exceeded-max",
            "3",
            "--fail-on",
            "warning",
            "--json",
        ]
    )

    failures: List[str] = []
    alerts = obj.get("alerts") if isinstance(obj.get("alerts"), list) else []
    codes = {str(x.get("code") or "") for x in alerts if isinstance(x, dict)}

    if bool(args.inject_fail):
        if int(rc) != 3:
            failures.append("expected rc=3 on inject-fail")
        if "portfolio_guard_blocked_ratio_high" not in codes:
            failures.append("portfolio_guard_blocked_ratio_high missing")
        if "portfolio_guard_strategy_budget_exceeded_high" not in codes:
            failures.append("portfolio_guard_strategy_budget_exceeded_high missing")
    else:
        if int(rc) != 0:
            failures.append("expected rc=0 on pass case")
        if "portfolio_guard_blocked_ratio_high" in codes:
            failures.append("unexpected portfolio_guard_blocked_ratio_high")
        if "portfolio_guard_strategy_budget_exceeded_high" in codes:
            failures.append("unexpected portfolio_guard_strategy_budget_exceeded_high")

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "event_log_path": str(events_path),
        "report_dir": str(report_dir),
        "inject_fail": bool(args.inject_fail),
        "alert_policy_rc": int(rc),
        "alert_total": int(obj.get("alert_total") or 0) if isinstance(obj, dict) else 0,
        "severity_total": obj.get("severity_total") if isinstance(obj.get("severity_total"), dict) else {},
        "alert_codes": sorted(codes),
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} alert_policy_rc={out['alert_policy_rc']} "
            f"alert_total={out['alert_total']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
