from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.q13_q14_validation import write_q13_q14_validation_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build frozen Q13/Q14 5-trading-day validation report.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--validation-id", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--days", nargs="*")
    args = parser.parse_args()
    result = write_q13_q14_validation_report(
        reports_root=Path(args.reports_root),
        validation_id=str(args.validation_id),
        days=args.days if args.days else None,
        start=args.start,
        end=args.end,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
