from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.integrated_trade_diagnosis import run_integrated_trade_diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild integrated offline trade diagnosis.")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--validation-start", default="2026-08-03")
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/evaluation/offline_alpha/integrated_trade_diagnosis"),
    )
    args = parser.parse_args()
    result = run_integrated_trade_diagnosis(
        reports_root=args.reports_root,
        output_root=args.output_root,
        start_day=args.start,
        end_day=args.end,
        validation_start_day=args.validation_start,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
