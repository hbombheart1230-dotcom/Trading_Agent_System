from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.research.conditional_alpha_diagnosis import run_conditional_alpha_diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild conditional alpha diagnosis.")
    parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/evaluation/offline_alpha/conditional_alpha_diagnosis"),
    )
    args = parser.parse_args()
    result = run_conditional_alpha_diagnosis(
        reports_root=args.reports_root, output_root=args.output_root
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
