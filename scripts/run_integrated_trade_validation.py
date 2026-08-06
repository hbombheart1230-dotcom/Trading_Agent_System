from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.opening_rank1_shadow import build_opening_rank1_shadow
from libs.research.integrated_trade_diagnosis import run_integrated_trade_diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the daily opening artifact and refresh integrated validation."
    )
    parser.add_argument(
        "--day",
        default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
    )
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--validation-start", default="2026-08-03")
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument("--state-path", type=Path, default=Path("data/state.json"))
    parser.add_argument("--no-fresh-fetch", action="store_true")
    args = parser.parse_args()
    opening = build_opening_rank1_shadow(
        day=args.day,
        reports_root=args.reports_root,
        state_path=args.state_path,
        allow_fresh_fetch=not args.no_fresh_fetch,
    )
    integrated = run_integrated_trade_diagnosis(
        reports_root=args.reports_root,
        start_day=args.start,
        end_day=args.day,
        validation_start_day=args.validation_start,
    )
    print(
        json.dumps(
            {"opening_rank1_shadow": opening, "integrated": integrated},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
