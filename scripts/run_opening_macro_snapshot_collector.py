from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.market.opening_macro_snapshot_collector import run_collector


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect fixed opening-only macro snapshots.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--poll-sec", type=float, default=1.0)
    args = parser.parse_args()
    os.chdir(ROOT)
    day = str(args.day)[:10]
    manifest = ROOT / "data" / "logs" / "macro_indicators" / day / "opening_capture_manifest.json"
    result = run_collector(day=day, manifest_path=manifest, poll_sec=args.poll_sec)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
