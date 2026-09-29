"""Diagnostic/read-only Alpha Research Board snapshot -- NOT a canonical
publisher. This CLI used to call write_alpha_research_board() directly,
which persisted the canonical dated Board and unconditionally advanced
reports/evaluation/alpha_research_board/latest.json/.md with no UEF-7/8/9
involvement at all -- a second, independent canonical-write path. That is
removed: this CLI now only ever calls build_alpha_research_board()
(read-only, nothing persisted by the Board builder itself) and writes its
result to an explicitly non-canonical diagnostic location.

The ONLY code path anywhere in this repository permitted to publish
canonical Alpha Board authority (a verified COMPLETE generation, current.
json, or the global latest.json) is
libs.reporting.evaluation.daily_uef_pipeline.run_daily_uef_evaluation --
see scripts/run_daily_uef_evaluation.py for the canonical entry point.

  python scripts/run_alpha_research_board.py --through-day 2026-09-29
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.alpha_research_board import build_alpha_research_board


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a diagnostic, non-canonical Alpha Research Board snapshot. "
                    "Never publishes canonical authority -- use scripts/run_daily_uef_evaluation.py for that."
    )
    parser.add_argument("--through-day", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument(
        "--output-dir",
        default="",
        help="If set, also write the diagnostic snapshot to this directory "
             "(json+md). Never the canonical reports/evaluation/alpha_research_board/<day>/ path.",
    )
    args = parser.parse_args()
    through_day = args.through_day[:10]

    board = build_alpha_research_board(reports_root=Path(args.reports_root), through_day=through_day)

    if args.output_dir:
        from libs.reporting.alpha_research_board.report import render_alpha_research_board

        canonical_dir = (Path(args.reports_root) / "evaluation" / "alpha_research_board" / through_day).resolve()
        output_dir = Path(args.output_dir).resolve()
        if output_dir == canonical_dir:
            raise SystemExit(
                f"--output-dir must not be the canonical path ({canonical_dir}); this CLI is diagnostic-only. "
                "Use scripts/run_daily_uef_evaluation.py to publish canonical Alpha Board authority."
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "alpha_research_board_diagnostic.json").write_text(
            json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output_dir / "alpha_research_board_diagnostic.md").write_text(
            render_alpha_research_board(board), encoding="utf-8"
        )

    print(json.dumps(board, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
