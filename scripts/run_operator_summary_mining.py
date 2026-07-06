from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.operator_summary_mining import write_operator_summary_mining


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build observation-only mining report for reports/operator_summary."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)
    result = write_operator_summary_mining(
        Path(args.reports_root),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
