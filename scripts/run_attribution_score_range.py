from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.attribution_score_range import write_attribution_score_range


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Q13 attribution score date-range aggregate.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--include-empty-days", action="store_true")
    args = parser.parse_args()
    result = write_attribution_score_range(
        reports_root=Path(args.reports_root),
        start=str(args.start),
        end=str(args.end),
        include_empty_days=bool(args.include_empty_days),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
