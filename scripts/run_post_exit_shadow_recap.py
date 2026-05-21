from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.post_exit_shadow_recap import generate_post_exit_shadow_recap, resolve_post_exit_state_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate end-of-day post-exit shadow recap artifacts.")
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--report-dir", default="reports/dev/analysis/post_exit_shadow_recap")
    parser.add_argument("--state-path", default="")
    parser.add_argument("--day", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    reports_root = Path(args.reports_root)
    raw_state_path = Path(args.state_path) if str(args.state_path or "").strip() else None
    state_path = resolve_post_exit_state_path(reports_root, raw_state_path)
    out = generate_post_exit_shadow_recap(
        reports_root=reports_root,
        report_dir=Path(args.report_dir),
        day=str(args.day),
        state_path=state_path,
    )
    if args.json:
        print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Wrote: {out.get('report_md_path')}")
        print(f"Wrote: {out.get('report_json_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
