from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_metrics_report import generate_metrics_report


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-5 portfolio guard metrics report check.")
    p.add_argument("--event-log-path", default="data/logs/m27_portfolio_guard_events.jsonl")
    p.add_argument("--report-dir", default="reports/m27_portfolio_guard")
    p.add_argument("--day", default="2026-02-20")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _seed_events(path: Path, *, day: str, inject_fail: bool) -> None:
    if inject_fail:
        rows: List[Dict[str, Any]] = [
            {
                "ts": f"{day}T00:00:00+00:00",
                "run_id": "r1",
                "stage": "commander_router",
                "event": "end",
                "payload": {"status": "ok", "path": "graph_spine"},
            }
        ]
        _write_jsonl(path, rows)
        return

    rows = [
        {
            "ts": f"{day}T00:00:00+00:00",
            "run_id": "r1",
            "stage": "commander_router",
            "event": "end",
            "payload": {
                "status": "ok",
                "path": "graph_spine",
                "portfolio_guard": {
                    "applied": True,
                    "approved_total": 2,
                    "blocked_total": 3,
                    "blocked_reason_counts": {"strategy_budget_exceeded": 2, "opposite_side_conflict": 1},
                },
            },
        },
        {
            "ts": f"{day}T00:00:05+00:00",
            "run_id": "r2",
            "stage": "commander_router",
            "event": "end",
            "payload": {
                "status": "ok",
                "path": "graph_spine",
                "portfolio_guard": {
                    "applied": True,
                    "approved_total": 1,
                    "blocked_total": 2,
                    "blocked_reason_counts": {"strategy_budget_exceeded": 1, "symbol_notional_cap_exceeded": 1},
                },
            },
        },
    ]
    _write_jsonl(path, rows)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-20").strip()

    _seed_events(events_path, day=day, inject_fail=bool(args.inject_fail))

    _, js_path = generate_metrics_report(events_path, report_dir, day=day)
    obj = json.loads(js_path.read_text(encoding="utf-8"))

    failures: List[str] = []
    pg = obj.get("portfolio_guard") if isinstance(obj.get("portfolio_guard"), dict) else {}
    topn = pg.get("blocked_reason_topN") if isinstance(pg.get("blocked_reason_topN"), list) else []

    if not pg:
        failures.append("portfolio_guard block missing")
    if int(pg.get("applied_total") or 0) < 1:
        failures.append("portfolio_guard.applied_total < 1")
    if int(pg.get("blocked_total_sum") or 0) < 1:
        failures.append("portfolio_guard.blocked_total_sum < 1")
    if len(topn) < 1:
        failures.append("portfolio_guard.blocked_reason_topN empty")
    if not any(str(x.get("reason") or "") == "strategy_budget_exceeded" for x in topn if isinstance(x, dict)):
        failures.append("strategy_budget_exceeded missing in blocked_reason_topN")

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "event_log_path": str(events_path),
        "metrics_json_path": str(js_path),
        "inject_fail": bool(args.inject_fail),
        "portfolio_guard": {
            "total": int(pg.get("total") or 0),
            "applied_total": int(pg.get("applied_total") or 0),
            "approved_total_sum": int(pg.get("approved_total_sum") or 0),
            "blocked_total_sum": int(pg.get("blocked_total_sum") or 0),
            "blocked_reason_topN": topn,
        },
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} applied_total={out['portfolio_guard']['applied_total']} "
            f"blocked_total_sum={out['portfolio_guard']['blocked_total_sum']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
