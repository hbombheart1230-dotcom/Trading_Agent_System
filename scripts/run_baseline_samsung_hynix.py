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

from libs.reporting.baseline_samsung_hynix import build_baseline_artifacts
from libs.runtime.shadow_loop_session import should_stop_shadow_loop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the independent Samsung Electronics / SK Hynix shadow baseline."
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--state-path", default="data/state.json")
    parser.add_argument("--cost-profile", default="")
    parser.add_argument("--as-of-epoch", type=int, default=0)
    parser.add_argument("--no-fresh-fetch", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-sec", type=int, default=300)
    parser.add_argument("--reconstruct-intraday", action="store_true")
    args = parser.parse_args()
    while True:
        result = build_baseline_artifacts(
            day=args.day,
            reports_root=Path(args.reports_root),
            state_path=Path(args.state_path),
            cost_profile_path=Path(args.cost_profile) if args.cost_profile else None,
            as_of_epoch=args.as_of_epoch or None,
            allow_fresh_fetch=not args.no_fresh_fetch,
            reconstruct_intraday=bool(args.reconstruct_intraday),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if not args.loop:
            break
        if should_stop_shadow_loop(day=args.day):
            print(json.dumps({"event": "shadow_loop_stopped", "day": args.day, "reason": "session_complete"}), flush=True)
            break
        time.sleep(max(30, int(args.interval_sec)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
