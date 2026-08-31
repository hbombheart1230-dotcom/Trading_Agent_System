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

from libs.core.settings import load_env_file
from libs.reporting.baseline_btc_woori_tech.point_in_time_capture import (
    capture_q12_btc_0855_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture immutable Q12 BTC evidence at 08:55 KST.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--root", default="data/logs/q12_btc_0855")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--retry-sec", type=float, default=15.0)
    args = parser.parse_args()
    load_env_file(Path(args.env_path))
    result = {}
    for attempt in range(max(1, int(args.attempts))):
        result = capture_q12_btc_0855_snapshot(
            day=str(args.day)[:10],
            root=Path(args.root),
        )
        if result.get("capture_status") in {"CAPTURED", "MISSED"}:
            break
        if attempt + 1 < max(1, int(args.attempts)):
            time.sleep(max(0.0, float(args.retry_sec)))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.get("capture_status") == "CAPTURED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
