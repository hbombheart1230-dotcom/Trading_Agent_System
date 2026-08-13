from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.research.rank1_feature_mart.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline canonical Rank-1 feature mart.")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--refresh-from", default="2026-08-01")
    parser.add_argument("--base-day", default="2026-08-11")
    args = parser.parse_args()
    result = run(
        project_root=PROJECT_ROOT,
        output_root=args.output_root,
        refresh_sources=bool(args.refresh_sources),
        refresh_from_day=str(args.refresh_from),
        base_day=str(args.base_day),
    )
    print(json.dumps({"output_root": result["output_root"], "episode_count": result["episode_count"], "integrity_status": result["integrity"]["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
