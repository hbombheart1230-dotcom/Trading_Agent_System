from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.monitor_noop_attribution import (
    build_monitor_noop_attribution,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build independent Monitor NOOP forward attribution.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--state-path", default="data/state.json")
    parser.add_argument("--output-dir", default="reports/evaluation/offline_alpha/monitor_noop_attribution")
    parser.add_argument("--no-fresh-fetch", action="store_true")
    args = parser.parse_args()
    result = build_monitor_noop_attribution(
        reports_root=Path(args.reports_root), state_path=Path(args.state_path),
        start=args.start, end=args.end, output_dir=Path(args.output_dir),
        allow_fresh_fetch=not args.no_fresh_fetch,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "payload"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
