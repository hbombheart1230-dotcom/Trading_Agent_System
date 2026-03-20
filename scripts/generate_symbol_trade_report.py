from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.symbol_trade_report import generate_symbol_trade_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a symbol-level aggregate trade report from operational truth.")
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    out = generate_symbol_trade_report(
        events_path=Path(str(args.event_log_path).strip()),
        reports_root=Path(str(args.reports_root).strip()),
        symbol=str(args.symbol).strip(),
    )
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"symbol={out.get('symbol')} report_json={out.get('report_json_path')} "
            f"report_md={out.get('report_md_path')} trade_count={int((out.get('summary') or {}).get('trade_count') or 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
