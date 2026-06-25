from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.baseline_samsung_hynix.unified_comparison import (
    write_unified_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the unified Q9 P/A/B/C versus Samsung/Hynix baseline report."
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    args = parser.parse_args()
    output_dir = (
        Path(args.reports_root)
        / "evaluation"
        / "baseline_samsung_hynix"
        / args.day
    )
    result = write_unified_comparison(
        forward_path=output_dir / "baseline_samsung_hynix_forward_returns.json",
        output_dir=output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
