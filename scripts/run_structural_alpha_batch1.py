from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.structural_alpha import run_structural_alpha_batch1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run structural alpha batch 1 offline."
    )
    parser.add_argument("--start", default="2026-06-24")
    parser.add_argument("--end", default="2026-07-30")
    parser.add_argument("--max-pages", type=int, default=18)
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()

    def progress(index: int, total: int, symbol: str) -> None:
        if index == 1 or index == total or index % 10 == 0:
            print(f"history {index}/{total}: {symbol}", flush=True)

    result = run_structural_alpha_batch1(
        start=args.start,
        end=args.end,
        allow_fetch=not args.no_fetch,
        max_pages=max(1, args.max_pages),
        progress=progress,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
