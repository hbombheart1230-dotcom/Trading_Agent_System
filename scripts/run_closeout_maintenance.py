from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.closeout_maintenance import (
    run_closeout_maintenance,
    write_closeout_maintenance_report,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run end-of-day closeout maintenance artifacts.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--post-exit-report-dir", default="reports/dev/analysis/post_exit_shadow_recap")
    parser.add_argument("--state-path", default="")
    parser.add_argument("--trigger", default="manual_closeout_maintenance")
    parser.add_argument("--skip-account-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    reports_root = Path(str(args.reports_root))
    payload = run_closeout_maintenance(
        day=str(args.day)[:10],
        reports_root=reports_root,
        event_log_path=Path(str(args.event_log_path)),
        post_exit_report_dir=Path(str(args.post_exit_report_dir)),
        state_path=Path(str(args.state_path)) if str(args.state_path or "").strip() else None,
        trigger=str(args.trigger),
        collect_account_snapshot=not bool(args.skip_account_snapshot),
    )
    paths = write_closeout_maintenance_report(payload, reports_root=reports_root)
    payload["report_paths"] = dict(paths)
    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ok={bool(payload.get('ok'))} report_json={paths.get('report_json_path')} report_md={paths.get('report_md_path')}")
        for name, step in (payload.get("steps") or {}).items():
            if isinstance(step, dict):
                print(f"{name}={'ok' if step.get('ok') else 'failed'}")
    return 0 if bool(payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
