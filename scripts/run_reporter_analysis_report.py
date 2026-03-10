from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.reporter_analysis import generate_reporter_analysis_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate enhanced Reporter analysis report from event logs.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--intents-path", default="data/logs/intents.jsonl")
    p.add_argument("--report-dir", default="reports/reporter_analysis")
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--day", default=None, help="UTC day (YYYY-MM-DD). If omitted, latest day in event log is used.")
    p.add_argument("--rapid-cycle-threshold-sec", type=int, default=120)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    event_log_path = Path(str(args.event_log_path).strip())
    intents_path = Path(str(args.intents_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    reports_root = Path(str(args.reports_root).strip())
    day = str(args.day).strip() if args.day else None

    md_path, js_path, out = generate_reporter_analysis_report(
        event_log_path,
        report_dir,
        day=day,
        intents_path=intents_path if intents_path.exists() else None,
        reports_root=reports_root,
        rapid_cycle_threshold_sec=max(1, int(args.rapid_cycle_threshold_sec)),
    )

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        flow = out.get("intent_flow_analysis") if isinstance(out.get("intent_flow_analysis"), dict) else {}
        incidents = out.get("incident_postmortem") if isinstance(out.get("incident_postmortem"), dict) else {}
        print(
            f"day={out.get('day')} intents_created={int(flow.get('intents_created') or 0)} "
            f"intents_blocked={int(flow.get('intents_blocked') or 0)} incidents={int(incidents.get('incident_total') or 0)} "
            f"report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

