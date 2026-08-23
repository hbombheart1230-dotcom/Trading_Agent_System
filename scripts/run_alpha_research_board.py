from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.alpha_research_board import write_alpha_research_board


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the read-only consolidated Alpha Research Board."
    )
    parser.add_argument("--through-day", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.reports_root)
        / "evaluation"
        / "alpha_research_board"
        / args.through_day[:10]
    )
    result = write_alpha_research_board(
        reports_root=Path(args.reports_root),
        through_day=args.through_day[:10],
        output_dir=output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
