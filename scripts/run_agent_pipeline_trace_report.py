from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.agent_pipeline_trace import generate_agent_pipeline_trace_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a single-run pipeline trace report (Commander/Strategist/Scanner/Monitor/Supervisor/Executor/Reporter)."
    )
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/events.jsonl")
    p.add_argument("--report-dir", default="reports/dev/analysis/agent_pipeline_trace")
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--run-id", default=None, help="If omitted, latest run for --day is selected.")
    p.add_argument("--day", default=None, help="UTC day (YYYY-MM-DD). Optional run picker filter.")
    p.add_argument("--max-news-titles", type=int, default=5)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    event_log_path = Path(str(args.event_log_path).strip())
    evidence_log_path = Path(str(args.evidence_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    reports_root = Path(str(args.reports_root).strip())
    run_id = str(args.run_id).strip() if args.run_id else None
    day = str(args.day).strip() if args.day else None

    try:
        md_path, js_path, out = generate_agent_pipeline_trace_report(
            event_log_path=event_log_path,
            evidence_log_path=evidence_log_path,
            report_dir=report_dir,
            run_id=run_id,
            day=day,
            reports_root=reports_root,
            max_news_titles=max(1, int(args.max_news_titles)),
        )
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 3

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"run_id={out.get('run_id')} day={out.get('day')} "
            f"report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

