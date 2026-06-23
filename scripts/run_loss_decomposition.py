from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.loss_decomposition import write_loss_decomposition


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only full-chain loss decomposition.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.reports_root) / "evaluation" / "decomposition" / args.end[:10]
    )
    result = write_loss_decomposition(
        reports_root=Path(args.reports_root),
        start=args.start,
        end=args.end,
        output_dir=output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
