from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.quant_trade_diagnosis import (
    write_quant_trade_diagnoses_for_day,
)


def _days(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    if final < current:
        raise ValueError("end must be on or after start")
    values = []
    while current <= final:
        values.append(current.isoformat())
        current += timedelta(days=1)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic per-trade quant diagnosis artifacts."
    )
    parser.add_argument("--reports-root", default=str(ROOT / "reports"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--day")
    group.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.day:
        days = [args.day]
    else:
        days = _days(args.start, args.end or args.start)
    results = [
        write_quant_trade_diagnoses_for_day(
            reports_root=Path(args.reports_root),
            day=day,
        )
        for day in days
    ]
    payload = {
        "schema_version": "quant_trade_diagnosis_range.v1",
        "behavior_effect": "diagnostic_only",
        "start": days[0],
        "end": days[-1],
        "day_count": len(days),
        "trade_count": sum(int(row.get("trade_count") or 0) for row in results),
        "written_count": sum(int(row.get("written_count") or 0) for row in results),
        "days": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"quant diagnosis: {payload['written_count']}/{payload['trade_count']} "
            f"trades written for {payload['start']}..{payload['end']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
