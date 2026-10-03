"""CLI entrypoint for UEF-8 Fair Comparison Validation.

Read-only against the live Alpha Research Board v2, through the frozen
UEF-7 normalizer. Writes ONLY under
reports/evaluation/uef8_fair_comparison/<UEF8_RUN_ID>/. Never modifies
UEF-1..UEF-7 or Alpha Board v2.

  python scripts/run_uef8_fair_comparison_validation.py --through-day 2026-09-25 [--repo-root DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.alpha_research_board import build_alpha_research_board  # noqa: E402
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board  # noqa: E402
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest  # noqa: E402
from libs.reporting.evaluation.uef8.fair_comparison import analyze_fair_comparisons  # noqa: E402
from libs.reporting.evaluation.uef8.reporter import write_uef8_fair_comparison_outputs  # noqa: E402
from libs.reporting.evaluation.uef8.run_identity import uef8_implementation_digest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--through-day", required=True)
    ap.add_argument("--repo-root", default=str(ROOT))
    args = ap.parse_args()
    repo_root = Path(args.repo_root)

    board = build_alpha_research_board(reports_root=repo_root / "reports", through_day=args.through_day[:10])
    normalized = normalize_alpha_board(board, normalizer_implementation_digest_value=normalizer_implementation_digest())
    run = analyze_fair_comparisons(normalized.to_dict(), uef8_implementation_digest_value=uef8_implementation_digest())
    out_dir = write_uef8_fair_comparison_outputs(run, repo_root=repo_root)

    print(json.dumps({
        "uef8_run_id": run.uef8_run_id,
        "candidate_count": run.candidate_count,
        "pair_count": run.summary.pair_count,
        "comparable_count": run.summary.comparable_count,
        "conditional_count": run.summary.conditional_count,
        "not_comparable_count": run.summary.not_comparable_count,
        "reason_counts": run.summary.reason_counts,
        "output_dir": str(out_dir),
    }, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
