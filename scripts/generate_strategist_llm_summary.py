from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.strategist_llm_summary import generate_strategist_llm_summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an operator-facing summary from strategist LLM response.json.")
    parser.add_argument("--response-json", required=True, help="Path to reports/llm/<day>/<run_id>/strategist/response.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    md_path, json_path, payload = generate_strategist_llm_summary(Path(args.response_json))
    result = {
        "summary_md_path": str(md_path),
        "summary_json_path": str(json_path),
        "headline": (payload.get("operator_readout") or {}).get("headline"),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"summary_md={md_path} summary_json={json_path} headline={result['headline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
