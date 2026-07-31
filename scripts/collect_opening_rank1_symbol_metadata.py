from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.opening_rank1_deep_dive.loaders import load_opening_episodes
from libs.research.opening_rank1_deep_dive.metadata import collect_current_symbol_metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect current Kiwoom metadata for opening Rank-1 research.")
    parser.add_argument(
        "--evidence-path",
        type=Path,
        default=Path(
            "reports/evaluation/offline_alpha/existing_evidence_mining/"
            "2026-06-01_2026-07-30/existing_evidence_mining.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/research/opening_rank1_deep_dive/symbol_metadata_2026-07-31.json"),
    )
    parser.add_argument("--theme-group-limit", type=int, default=100)
    parser.add_argument("--request-interval-sec", type=float, default=1.05)
    parser.add_argument("--skip-themes", action="store_true")
    args = parser.parse_args()
    episodes = load_opening_episodes(args.evidence_path)
    result = collect_current_symbol_metadata(
        [str(row.get("symbol") or "") for row in episodes],
        output_path=args.output,
        theme_group_limit=max(1, args.theme_group_limit),
        request_interval_sec=max(0.0, args.request_interval_sec),
        collect_themes=not args.skip_themes,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "symbols": result["requested_symbol_count"],
                "theme_groups": result["theme_group_count"],
                "name_errors": len(result["name_errors"]),
                "theme_errors": len(result["theme_errors"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
