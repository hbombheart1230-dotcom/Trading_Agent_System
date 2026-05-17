from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.phase_runtime_health import (  # noqa: E402
    build_phase_5_2_5_3_runtime_health,
    render_chart_structure_decision_hint_summary_text,
    render_phase_5_2_5_3_runtime_health_text,
    render_policy_surface_quality_summary_text,
)
from libs.reporting.phase_runtime_health import (  # noqa: E402
    _compact_run_view,
    _render_compact_run_table,
    _render_reclaim_table,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect phase 5-2 ~ 5-3 runtime surfaces from canonical monitor artifacts and monitor event payloads."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--date", default="", help="Canonical day (YYYY-MM-DD). Defaults to latest canonical day.")
    parser.add_argument("--run-id", action="append", default=[], help="Specific run_id(s) to inspect. May be repeated.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--only-buy", action="store_true", help="Print only recent BUY run table after aggregation.")
    parser.add_argument("--reason", default="", help="Filter compact run view by exact legacy/final reason.")
    parser.add_argument("--show-reclaim-near-ready", action="store_true", help="Print reclaim WAIT table with near-ready fields.")
    parser.add_argument("--show-policy-summary", action="store_true", help="Print only compact policy surface quality summary.")
    parser.add_argument("--show-chart-structure-summary", action="store_true", help="Print only compact chart structure decision hint summary.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    reports_root = Path(str(args.reports_root).strip())
    event_log_path = Path(str(args.event_log_path).strip())
    if not reports_root.is_absolute():
        reports_root = ROOT / reports_root
    if not event_log_path.is_absolute():
        event_log_path = ROOT / event_log_path

    try:
        out = build_phase_5_2_5_3_runtime_health(
            reports_root=reports_root,
            event_log_path=event_log_path,
            day=str(args.date).strip(),
            run_ids=list(args.run_id or []),
            limit=max(1, int(args.limit or 50)),
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if bool(args.only_buy):
        print(_render_compact_run_table(out.get("buy_runs") if isinstance(out.get("buy_runs"), list) else []))
        return 0
    if str(args.reason or "").strip():
        wanted = str(args.reason or "").strip()
        matched = [
            _compact_run_view(row)
            for row in list(out.get("runs") or [])
            if str(row.get("legacy_entry_reason") or row.get("reason") or "").strip() == wanted
        ]
        print(_render_compact_run_table(matched))
        return 0
    if bool(args.show_reclaim_near_ready):
        print(_render_reclaim_table(out.get("reclaim_wait_runs") if isinstance(out.get("reclaim_wait_runs"), list) else []))
        return 0
    if bool(args.show_policy_summary):
        print(
            render_policy_surface_quality_summary_text(
                str(out.get("day") or ""),
                out.get("policy_surface_quality_summary") if isinstance(out.get("policy_surface_quality_summary"), Mapping) else {},
            )
        )
        return 0
    if bool(args.show_chart_structure_summary):
        print(
            render_chart_structure_decision_hint_summary_text(
                str(out.get("day") or ""),
                out.get("chart_structure_decision_hint_summary") if isinstance(out.get("chart_structure_decision_hint_summary"), Mapping) else {},
            )
        )
        return 0

    print(render_phase_5_2_5_3_runtime_health_text(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
