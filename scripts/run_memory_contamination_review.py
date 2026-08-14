from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.memory_review import build_memory_contamination_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reclassify Q9 Stage-2 decisions by memory integrity.")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--evidence-path", default="data/evidence_ledger/events.jsonl")
    args = parser.parse_args(argv)
    result = build_memory_contamination_review(
        reports_root=Path(args.reports_root),
        evidence_path=Path(args.evidence_path),
        start_day=args.start,
        end_day=args.end,
    )
    print(json.dumps(result.get("artifact_paths") or {}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
