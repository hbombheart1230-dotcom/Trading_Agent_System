from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.evaluation_lens_report import write_evaluation_lens_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an evaluation-only lens report over Q8/Q9/trade artifacts."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)

    result = write_evaluation_lens_report(
        reports_root=Path(args.reports_root),
        start=args.start,
        end=args.end,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
