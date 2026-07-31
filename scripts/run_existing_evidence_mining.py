from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.existing_evidence_mining import run_existing_evidence_mining


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine existing Q9-Q18 evidence offline.")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--allow-fetch", action="store_true")
    parser.add_argument("--max-pages", type=int, default=18)
    args = parser.parse_args()

    def progress(index: int, total: int, symbol: str) -> None:
        if index == 1 or index == total or index % 20 == 0:
            print(f"history {index}/{total}: {symbol}", flush=True)

    result = run_existing_evidence_mining(
        start=args.start,
        end=args.end,
        allow_fetch=bool(args.allow_fetch),
        max_pages=max(1, args.max_pages),
        progress=progress,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
