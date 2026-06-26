from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.trade_symbol_integrity import repair_all_trade_symbol_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair executed-symbol Scanner context in trade artifacts."
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--day", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = repair_all_trade_symbol_artifacts(
        Path(args.reports_root),
        day=args.day,
        write=not args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
