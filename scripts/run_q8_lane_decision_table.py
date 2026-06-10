from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.q8_lane_decision_table import write_q8_lane_decision_table


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Q8 lane decision table for one trading day.")
    parser.add_argument("--day", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--docs-root", default="docs/tactics")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = write_q8_lane_decision_table(
        reports_root=Path(str(args.reports_root)),
        docs_root=Path(str(args.docs_root)),
        day=str(args.day)[:10],
    )
    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        print(f"ok={bool(result.get('ok'))} md={result.get('md_path')} json={result.get('json_path')}")
        print(
            f"candidates={payload.get('candidate_count')} "
            f"observed={payload.get('forward_outcome_available_count')} "
            f"coverage={float(payload.get('forward_outcome_coverage') or 0.0):.1%}"
        )
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
