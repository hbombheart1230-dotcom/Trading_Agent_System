from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.cumulative_improvement_review import (
    write_cumulative_improvement_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Q8-Q17 cumulative improvement review."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    result = write_cumulative_improvement_review(
        reports_root=Path(args.reports_root),
        start=args.start,
        end=args.end,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
