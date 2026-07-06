from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.historical_prior import DEFAULT_BEFORE_DAY, build_historical_q9_prior


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize pre-freeze historical trade artifacts into read-only Q9 prior evidence."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--from-day", default="")
    parser.add_argument("--before-day", default=DEFAULT_BEFORE_DAY)
    args = parser.parse_args(argv)
    result = build_historical_q9_prior(
        Path(args.reports_root),
        from_day=str(args.from_day or ""),
        before_day=str(args.before_day or DEFAULT_BEFORE_DAY),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
