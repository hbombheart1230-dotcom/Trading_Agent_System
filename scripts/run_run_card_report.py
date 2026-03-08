from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.operator_visibility import generate_run_card_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate short run cards for each run cycle.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/run_cards")
    p.add_argument("--day", default=None)
    p.add_argument("--max-runs", type=int, default=120)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day).strip() if args.day else None

    md_path, out = generate_run_card_report(
        events_path,
        report_dir,
        day=day,
        max_runs=max(0, int(args.max_runs)),
    )
    out = dict(out or {})
    out["report_md_path"] = str(md_path)

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"day={out.get('day')} card_total={int(out.get('card_total') or 0)} report_md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
