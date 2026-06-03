from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.q8_shadow_blocker_review import generate_q8_shadow_blocker_review


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate read-only Q8 shadow blocker forward-outcome review.",
    )
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate_q8_shadow_blocker_review(
        reports_root=Path(str(args.reports_root)),
        day=str(args.day)[:10],
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote: {result.get('report_md_path')}")
        print(f"Wrote: {result.get('report_json_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
