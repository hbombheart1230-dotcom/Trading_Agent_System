from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.entry_blocker_read_model import (  # noqa: E402
    build_entry_blocker_day_summary,
    render_entry_blocker_summary_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize entry blocker distribution from canonical monitor artifacts.")
    parser.add_argument("--date", required=True, help="Target day in YYYY-MM-DD format")
    parser.add_argument("--symbol", default="", help="Optional symbol filter")
    parser.add_argument("--family", default="", help="Optional blocker family filter")
    parser.add_argument("--limit", type=int, default=0, help="Keep only the latest N rows after filtering")
    parser.add_argument("--canonical-root", default=str(ROOT / "reports" / "canonical"))
    parser.add_argument("--json-out", default="", help="Optional path to save JSON summary")
    parser.add_argument("--md-out", default="", help="Optional path to save markdown summary")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout instead of markdown")
    args = parser.parse_args()

    summary = build_entry_blocker_day_summary(
        args.canonical_root,
        day=str(args.date),
        symbol=str(args.symbol or ""),
        family=str(args.family or ""),
        limit=int(args.limit or 0) or None,
    )
    markdown = render_entry_blocker_summary_markdown(summary)
    json_payload = json.dumps(summary, ensure_ascii=False, indent=2)

    if args.json_out:
        Path(args.json_out).write_text(json_payload, encoding="utf-8")
    if args.md_out:
        Path(args.md_out).write_text(markdown, encoding="utf-8")

    if args.json:
        print(json_payload)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
