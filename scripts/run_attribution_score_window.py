from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.attribution_score_window import write_attribution_score_window


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Q13 attribution score window aggregate.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--window-id", default="q9_q10_q11_q12_5d_20260629")
    args = parser.parse_args()
    result = write_attribution_score_window(
        reports_root=Path(args.reports_root),
        window_id=str(args.window_id),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
