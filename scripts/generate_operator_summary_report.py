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

from libs.reporting.operator_period_summary import (
    default_month_key,
    default_week_key,
    generate_operator_period_summary,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate operator-facing weekly/monthly summary reports.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--period-type", choices=["weekly", "monthly"], required=True)
    parser.add_argument("--period-key", default="", help="YYYY-Www for weekly, YYYY-MM for monthly. Defaults to today.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    period_key = str(args.period_key or "").strip()
    if not period_key:
        today = date.today()
        period_key = default_week_key(today) if args.period_type == "weekly" else default_month_key(today)
    md_path, json_path, payload = generate_operator_period_summary(
        reports_root=Path(str(args.reports_root).strip()),
        period_type=str(args.period_type).strip(),
        period_key=period_key,
    )
    if bool(args.json):
        print(json.dumps({"report_md_path": str(md_path), "report_json_path": str(json_path), "payload": payload}, ensure_ascii=False))
    else:
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        print(
            f"period={payload.get('period_type')} key={payload.get('period_key')} "
            f"trades={int(metrics.get('trade_count') or 0)} report_json={json_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
