from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.trade_explain import generate_trade_explain_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate trade explain report (buy/sell pair, hold-time, PnL estimate, reason chain)."
    )
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/trade_explain")
    p.add_argument("--day", default=None, help="UTC day (YYYY-MM-DD). If omitted, latest day in event log is used.")
    p.add_argument("--max-executions", type=int, default=120)
    p.add_argument("--max-sell-pairs", type=int, default=120)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    event_log_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day).strip() if args.day else None

    md_path, js_path, out = generate_trade_explain_report(
        event_log_path,
        report_dir,
        day=day,
        max_executions=max(1, int(args.max_executions)),
        max_sell_pairs=max(1, int(args.max_sell_pairs)),
    )
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        exe = out.get("execution_summary") if isinstance(out.get("execution_summary"), dict) else {}
        print(
            f"day={out.get('day')} executions_total={int(exe.get('executions_total') or 0)} "
            f"sell_pairs_total={int(exe.get('sell_pairs_total') or 0)} "
            f"report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

