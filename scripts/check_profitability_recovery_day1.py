from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.profitability_recovery_day1 import audit_profitability_recovery_day


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate profitability recovery Day1 diagnostics.")
    parser.add_argument("--date", required=True, help="Trading day in YYYY-MM-DD format")
    parser.add_argument("--reports-root", default="reports", help="Reports root directory")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args(argv)

    audit = audit_profitability_recovery_day(Path(args.reports_root), args.date)
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        print(f"[Profitability Recovery Day1 Check] {args.date}")
        print(f"- closed trade report generation regression: {audit['closed_trade_report_generation_regression_count']}")
        print(f"- closed trade decision_only misclassification count: {audit['closed_trade_decision_only_misclassification_count']}")
        print(f"- holding evidence thin count: {audit['holding_evidence_thin_count']}")
        print(f"- same-day linkage missing count: {audit['same_day_linkage_missing_count']}")
        print(f"- execution fields missing count: {audit['execution_fields_missing_count']}")
        print(f"- top recurring diagnostic weakness: {audit['top_recurring_diagnostic_weakness']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
