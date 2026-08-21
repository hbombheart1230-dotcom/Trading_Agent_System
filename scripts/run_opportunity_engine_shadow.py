from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.opportunity_engine import build_opportunity_engine_artifacts
from libs.runtime.shadow_loop_session import should_stop_shadow_loop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the isolated market-transition and surge opportunity shadow engine."
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--symbols", default="005930,000660,009150")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--state-path", default="data/state.json")
    parser.add_argument("--macro-root", default="data/logs/macro_indicators")
    parser.add_argument("--cost-profile", default="")
    parser.add_argument("--no-fresh-fetch", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-sec", type=int, default=300)
    args = parser.parse_args()
    while True:
        result = build_opportunity_engine_artifacts(
            day=args.day,
            symbols=tuple(part.strip() for part in args.symbols.split(",") if part.strip()),
            reports_root=Path(args.reports_root),
            state_path=Path(args.state_path),
            macro_root=Path(args.macro_root),
            cost_profile_path=Path(args.cost_profile) if args.cost_profile else None,
            allow_fresh_fetch=not args.no_fresh_fetch,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if not args.loop:
            return 0
        if should_stop_shadow_loop(day=args.day):
            print(json.dumps({"event": "shadow_loop_stopped", "day": args.day, "reason": "session_complete"}), flush=True)
            return 0
        time.sleep(max(30, int(args.interval_sec)))


if __name__ == "__main__":
    raise SystemExit(main())
