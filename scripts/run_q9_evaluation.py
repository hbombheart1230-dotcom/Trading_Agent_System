from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation import build_q9_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only Q9 evaluation outputs.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    args = parser.parse_args(argv)
    result = build_q9_evaluation(Path(args.reports_root), args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
