from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.rank1_feature_mart.pipeline import run
from libs.research.rank1_feature_mart.prospective import build_prospective_shadow
from libs.research.rank1_feature_mart.activation_shadow import (
    build_fresh_change_activation_shadow,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fixed Rank-1 candidate shadow artifacts.")
    parser.add_argument("--day", default=datetime.now(timezone(timedelta(hours=9))).date().isoformat())
    parser.add_argument("--no-rebuild-mart", action="store_true")
    args = parser.parse_args()
    if not args.no_rebuild_mart:
        run(project_root=ROOT)
    result = {
        "frozen_candidates": build_prospective_shadow(
            day=args.day, reports_root=ROOT / "reports"
        ),
        "fresh_change_activation": build_fresh_change_activation_shadow(
            day=args.day, reports_root=ROOT / "reports"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
