from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.baseline_btc_woori_tech.historical_review import build_historical_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay stored Q12 evidence under v1 and v2 policies.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    result = build_historical_review(
        reports_root=Path(args.reports_root),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
