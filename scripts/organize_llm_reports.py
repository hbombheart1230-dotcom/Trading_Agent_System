from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.llm_report_classifier import organize_llm_day


def main() -> int:
    parser = argparse.ArgumentParser(description="Group per-run LLM reports by execution result.")
    parser.add_argument("--date", required=True, help="Report date, e.g. 2026-05-11")
    parser.add_argument("--reports-root", default="reports", help="Reports root directory")
    parser.add_argument(
        "--active-grace-sec",
        type=int,
        default=180,
        help="Do not move run folders modified within this many seconds.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show classification without moving folders")
    args = parser.parse_args()

    rows = organize_llm_day(
        reports_root=Path(args.reports_root),
        day=args.date,
        active_grace_sec=args.active_grace_sec,
        dry_run=args.dry_run,
    )

    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("category") or row.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    payload: Dict[str, Any] = {"date": args.date, "dry_run": args.dry_run, "counts": counts}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
