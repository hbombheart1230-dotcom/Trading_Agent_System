from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.frozen_window_closeout import (
    run_frozen_window_closeout,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and verify all reports for the frozen Q9/baseline window."
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--state-path", default="data/state.json")
    args = parser.parse_args()
    result = run_frozen_window_closeout(
        day=args.day,
        reports_root=Path(args.reports_root),
        state_path=Path(args.state_path),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
