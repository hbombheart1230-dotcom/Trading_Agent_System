from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.alpha_competition import run_alpha_hypothesis_competition


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare three frozen alpha hypotheses offline."
    )
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-30")
    parser.add_argument("--max-pages", type=int, default=25)
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    result = run_alpha_hypothesis_competition(
        start=args.start,
        end=args.end,
        allow_fetch=not args.no_fetch,
        max_pages=max(1, args.max_pages),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
