from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.horizon_revision_backtest import run_horizon_revision_backtest


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare historical exits with horizon-extension checkpoints.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--live-cost-pct", type=float, default=0.28)
    parser.add_argument("--mock-cost-pct", type=float, default=1.086849)
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else (
        Path(args.reports_root) / "evaluation" / "horizon_revision" / args.end[:10]
    )
    result = run_horizon_revision_backtest(
        reports_root=Path(args.reports_root),
        start_day=args.start[:10],
        end_day=args.end[:10],
        output_dir=output_dir,
        live_cost_pct=args.live_cost_pct,
        mock_cost_pct=args.mock_cost_pct,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
