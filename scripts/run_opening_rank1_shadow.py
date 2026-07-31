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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the prospective opening Rank-1 observation report."
    )
    parser.add_argument(
        "--day",
        default=datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
    )
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--state-path", default="data/state.json")
    parser.add_argument("--no-fresh-fetch", action="store_true")
    args = parser.parse_args()
    result = build_opening_rank1_shadow(
        day=args.day,
        reports_root=Path(args.reports_root),
        state_path=Path(args.state_path),
        allow_fresh_fetch=not args.no_fresh_fetch,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
