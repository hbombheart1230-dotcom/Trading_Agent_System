from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.same_symbol_sequences import build_same_symbol_sequence_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build same-symbol sequence provenance artifacts.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    args = parser.parse_args()
    current = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    result = {}
    while current <= end:
        day = current.isoformat()
        reports_root = Path(args.reports_root)
        if (reports_root / "evaluation" / "trades" / day).exists():
            result = build_same_symbol_sequence_artifacts(reports_root=reports_root, day=day)
        current += timedelta(days=1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
