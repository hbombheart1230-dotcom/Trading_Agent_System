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

from libs.market.q10_index_observation_collector import run_due_slots
from libs.runtime.shadow_loop_session import should_stop_shadow_loop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Q10 Index (KOSPI/KOSDAQ) observations at fixed 09:30/10:00/CLOSE slots."
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--root", default="data/logs/q10_index_observations")
    parser.add_argument("--poll-sec", type=float, default=30.0)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    day = str(args.day)[:10]
    while True:
        rows = run_due_slots(day=day, root=Path(args.root))
        if rows:
            print(json.dumps({"day": day, "captured": rows}, ensure_ascii=False), flush=True)
        if not args.loop:
            break
        if should_stop_shadow_loop(day=day):
            print(json.dumps({"event": "shadow_loop_stopped", "day": day, "reason": "session_complete"}), flush=True)
            break
        time.sleep(max(5.0, float(args.poll_sec)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
