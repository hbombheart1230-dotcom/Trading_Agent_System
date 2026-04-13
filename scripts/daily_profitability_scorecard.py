from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.profitability_recovery_day1 import build_daily_profitability_scorecard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a daily profitability diagnostic scorecard.")
    parser.add_argument("--date", required=True, help="Trading day in YYYY-MM-DD format")
    parser.add_argument("--reports-root", default="reports", help="Reports root directory")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown-like text")
    args = parser.parse_args(argv)

    reports_root = Path(args.reports_root)
    scorecard = build_daily_profitability_scorecard(reports_root, args.date)
    if args.json:
        print(json.dumps(scorecard, ensure_ascii=False, indent=2))
    else:
        print(f"[Daily Profitability Scorecard] {args.date}")
        print(f"- total trades: {scorecard['total_trades']}")
        print(f"- closed trades: {scorecard['closed_trades']}")
        print(f"- loss trades: {scorecard['loss_trades']}")
        print(f"- lifecycle linkage missing count: {scorecard['lifecycle_linkage_missing_count']}")
        print(f"- holding evidence thin count: {scorecard['holding_evidence_thin_count']}")
        print(f"- execution fields missing count: {scorecard['execution_fields_missing_count']}")
        print(f"- top recurring diagnostic weakness: {scorecard['top_recurring_diagnostic_weakness']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
