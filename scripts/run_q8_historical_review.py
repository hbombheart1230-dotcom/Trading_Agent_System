from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.q8_historical_review import write_q8_historical_review


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Q8 historical review from daily summaries and trade reports.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--docs-root", default="docs/tactics")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = write_q8_historical_review(
        reports_root=Path(str(args.reports_root)),
        docs_root=Path(str(args.docs_root)),
        start=str(args.start)[:10],
        end=str(args.end)[:10],
    )
    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        trade = payload.get("trade_summary") if isinstance(payload.get("trade_summary"), dict) else {}
        print(f"ok={bool(result.get('ok'))} md={result.get('md_path')} json={result.get('json_path')}")
        print(
            "trade_samples="
            f"{trade.get('return_sample_count')} avg={trade.get('avg_return_pct')} "
            f"q_shadow_days={payload.get('q_shadow_day_count')} q8_group_days={payload.get('q8_group_day_count')}"
        )
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
