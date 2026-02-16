from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.trading_graph import run_trading_graph
from libs.core.event_logger import EventLogger
from scripts.generate_metrics_report import generate_metrics_report


class _DemoRunner:
    def __init__(self, *, fail: bool = False):
        self.fail = bool(fail)

    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail:
            if skill == "market.quote":
                return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
            if skill == "account.orders":
                return {"result": {"action": "ask", "question": "account required"}}
            if skill == "order.status":
                return {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
            return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}

        if skill == "market.quote":
            sym = str(args.get("symbol") or "")
            px = {"005930": 70500, "000660": 129000, "035420": 198000}.get(sym, 10000)
            return {"result": {"action": "ready", "data": {"symbol": sym, "cur": px}}}
        if skill == "account.orders":
            return {"result": {"action": "ready", "data": {"rows": [{"symbol": "005930", "order_id": "ord-1"}]}}}
        if skill == "order.status":
            return {
                "result": {
                    "action": "ready",
                    "data": {
                        "ord_no": str(args.get("ord_no") or ""),
                        "symbol": str(args.get("symbol") or ""),
                        "status": "PARTIAL",
                        "filled_qty": 1,
                        "order_qty": 2,
                        "filled_price": 70400,
                        "order_price": 70500,
                    },
                }
            }
        return {"result": {"action": "error", "meta": {"error_type": "unknown_skill"}}}


def _strategist_passthrough(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _run_once(*, run_id: str, fail: bool, logger: EventLogger) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": run_id,
        "event_logger": logger,
        "skill_runner": _DemoRunner(fail=fail),
        "candidates": [{"symbol": "005930"}, {"symbol": "000660"}, {"symbol": "035420"}],
        "mock_scan_results": {
            "005930": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "000660": {"score": 0.60, "risk_score": 0.20, "confidence": 0.82},
            "035420": {"score": 0.55, "risk_score": 0.25, "confidence": 0.78},
        },
        "plan": {"thesis": "m22_closeout"},
        "order_ref": {"ord_no": "ord-2", "symbol": "005930", "ord_dt": "20260216", "qry_tp": "3"},
    }
    return run_trading_graph(state, strategist=_strategist_passthrough)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M22 closeout check (hydration + fallback + metrics)")
    p.add_argument("--event-log-path", default="data/logs/m22_closeout_events.jsonl")
    p.add_argument("--report-dir", default="reports/m22_closeout")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--skip-timeout-case", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    events_path = Path(args.event_log_path)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    if (not args.no_clear) and events_path.exists():
        events_path.unlink()

    logger = EventLogger(log_path=events_path)
    _run_once(run_id="m22-closeout-ok", fail=False, logger=logger)
    if not bool(args.skip_timeout_case):
        _run_once(run_id="m22-closeout-timeout", fail=True, logger=logger)

    day = str(args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    _, js = generate_metrics_report(events_path, report_dir, day=day)
    metrics = json.loads(js.read_text(encoding="utf-8"))

    sh = metrics.get("skill_hydration") if isinstance(metrics.get("skill_hydration"), dict) else {}
    total = int(sh.get("total") or 0)
    fallback_total = int(sh.get("fallback_hint_total") or 0)
    used_runner_total = int(sh.get("used_runner_total") or 0)
    runner_sources = sh.get("runner_source_total") if isinstance(sh.get("runner_source_total"), dict) else {}

    ok = True
    failures: List[str] = []
    if total < 1:
        ok = False
        failures.append("skill_hydration.total < 1")
    if used_runner_total < 1:
        ok = False
        failures.append("skill_hydration.used_runner_total < 1")
    if not bool(args.skip_timeout_case) and fallback_total < 1:
        ok = False
        failures.append("skill_hydration.fallback_hint_total < 1")
    if int(runner_sources.get("state.skill_runner") or 0) < 1:
        ok = False
        failures.append("runner_source_total.state.skill_runner < 1")

    summary = {
        "ok": bool(ok),
        "day": day,
        "events_path": str(events_path),
        "metrics_json_path": str(js),
        "skill_hydration": {
            "total": total,
            "used_runner_total": used_runner_total,
            "fallback_hint_total": fallback_total,
            "runner_source_total": runner_sources,
        },
        "failures": failures,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"ok={summary['ok']} day={day} hydration_total={total} "
            f"used_runner_total={used_runner_total} fallback_hint_total={fallback_total}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
