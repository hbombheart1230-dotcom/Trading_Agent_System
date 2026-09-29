"""CLI entrypoint for UEF-7 Alpha Board Normalization.

Read-only against the live Alpha Research Board v2. Writes ONLY under
reports/evaluation/uef7_alpha_board/<UEF7_RUN_ID>/. Never modifies
libs/reporting/alpha_research_board/* or any UEF-1..UEF-6 file.

  python scripts/run_uef7_alpha_board_normalization.py --through-day 2026-09-25 [--repo-root DIR]
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
from libs.reporting.evaluation.uef7.reporter import write_uef7_normalization_outputs  # noqa: E402
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--through-day", required=True)
    ap.add_argument("--repo-root", default=str(ROOT))
    args = ap.parse_args()
    repo_root = Path(args.repo_root)

    board = build_alpha_research_board(reports_root=repo_root / "reports", through_day=args.through_day[:10])
    normalized = normalize_alpha_board(board, normalizer_implementation_digest_value=normalizer_implementation_digest())
    out_dir = write_uef7_normalization_outputs(normalized, repo_root=repo_root)

    print(json.dumps({
        "uef7_run_id": normalized.uef7_run_id,
        "candidate_row_count": normalized.candidate_row_count,
        "shared_source_group_count": normalized.normalization_summary.shared_source_group_count,
        "rows_with_shared_source_count": normalized.normalization_summary.rows_with_shared_source_count,
        "source_groups": [g.to_dict() for g in normalized.source_groups],
        "output_dir": str(out_dir),
    }, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
