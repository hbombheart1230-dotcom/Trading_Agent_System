from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.scanner_alignment_root_cause import (
    write_scanner_alignment_root_cause_range,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Q14 scanner alignment root-cause range report.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    result = write_scanner_alignment_root_cause_range(
        reports_root=Path(args.reports_root),
        start=str(args.start),
        end=str(args.end),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
