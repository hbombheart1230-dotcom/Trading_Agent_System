from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.opening_rank1_longitudinal import (
    run_opening_rank1_longitudinal,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze opening Rank-1 stage fate and delayed outcomes."
    )
    parser.add_argument(
        "--deep-dive-path",
        type=Path,
        default=Path(
            "reports/evaluation/offline_alpha/opening_rank1_deep_dive/"
            "opening_rank1_deep_dive.json"
        ),
    )
    parser.add_argument(
        "--daily-cache-root",
        type=Path,
        default=Path(
            "data/research/opening_rank1_longitudinal/daily_cache"
        ),
    )
    parser.add_argument("--refresh-daily", action="store_true")
    parser.add_argument("--base-day", default="2026-07-31")
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=Path("reports"),
    )
    parser.add_argument(
        "--minute-cache-root",
        type=Path,
        default=Path(
            "data/research/post_reclaim_alpha/minute_cache"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "reports/evaluation/offline_alpha/opening_rank1_longitudinal"
        ),
    )
    args = parser.parse_args()
    result = run_opening_rank1_longitudinal(
        deep_dive_path=args.deep_dive_path,
        reports_root=args.reports_root,
        minute_cache_root=args.minute_cache_root,
        output_root=args.output_root,
        daily_cache_root=args.daily_cache_root,
        refresh_daily=bool(args.refresh_daily),
        base_day=str(args.base_day),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
