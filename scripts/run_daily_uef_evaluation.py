"""Scheduler-agnostic daily post-market evaluation entry point (P1.2).

The ONLY thing a scheduler (current Windows Task, future Docker/Linux) may
do is invoke this script and check its exit code -- no Alpha Board or UEF
semantics belong in the scheduling layer itself.

  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29
  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29 --diagnostic

Exit code 0 only if the full Alpha Board -> UEF-7 -> UEF-8 -> UEF-9 chain
succeeded and UEF-9's authority_status is VALID. Any other outcome exits
non-zero and leaves reports/evaluation/alpha_research_board/latest.json
and .md untouched.

--diagnostic runs the same chain WITHOUT enforcing the freshness contracts,
for inspecting a stale/incomplete input set -- but a diagnostic run can
NEVER write any canonical file (dated board, latest.json/.md, or UEF-7/8/9
run directories), regardless of outcome; this is enforced inside
libs.reporting.evaluation.daily_uef_pipeline.run_daily_uef_evaluation
itself, not just by this CLI's own flag handling. A scheduler must never
pass --diagnostic.
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
        "--diagnostic",
        action="store_true",
        help="Inspect the chain against current sources without the freshness contracts. "
             "Never writes any canonical file, whatever the outcome. Never use for a real daily run.",
    )
    args = parser.parse_args()

    result = run_daily_uef_evaluation(
        repo_root=Path(args.repo_root),
        through_day=str(args.through_day)[:10],
        canonical=not bool(args.diagnostic),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
