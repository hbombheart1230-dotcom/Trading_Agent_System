"""Scheduler-agnostic daily post-market evaluation entry point (P1.2).

The ONLY thing a scheduler (current Windows Task, future Docker/Linux) may
do is invoke this script and check its exit code -- no Alpha Board or UEF
semantics belong in the scheduling layer itself.

  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29
  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29 --allow-stale-sources

Exit code 0 only if the full Alpha Board -> UEF-7 -> UEF-8 -> UEF-9 chain
succeeded and UEF-9's authority_status is VALID. Any other outcome exits
non-zero and leaves reports/evaluation/alpha_research_board/latest.json
and .md untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.daily_uef_pipeline import run_daily_uef_evaluation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-day", default=date.today().isoformat())
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--allow-stale-sources",
        action="store_true",
        help="Bypass the freshness guard (diagnostic/testing only -- never use for a real daily run).",
    )
    args = parser.parse_args()

    result = run_daily_uef_evaluation(
        repo_root=Path(args.repo_root),
        through_day=str(args.through_day)[:10],
        require_fresh_sources=not bool(args.allow_stale_sources),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
