from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.stage2_authority import write_stage2_authority_review_sharded


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the evaluation-only cumulative Stage-2 authority review.")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--rebuild-daily", action="store_true")
    args = parser.parse_args()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.reports_root)
        / "evaluation"
        / "agent_effectiveness"
        / f"cumulative_{args.start[:10].replace('-', '')}_{args.end[:10].replace('-', '')}"
    )
    result = write_stage2_authority_review_sharded(
        reports_root=Path(args.reports_root),
        start=args.start[:10],
        end=args.end[:10],
        output_dir=output_dir,
        rebuild_daily=args.rebuild_daily,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
