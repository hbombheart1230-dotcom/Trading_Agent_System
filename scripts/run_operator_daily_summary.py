from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.operator_visibility import generate_operator_daily_summary


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate operator-friendly daily summary from existing observability artifacts.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--metrics-report-dir", default="reports/metrics")
    p.add_argument("--m30-post-golive-dir", default="reports/milestones/m30_post_golive")
    p.add_argument("--m30-golive-dir", default="reports/milestones/m30_golive")
    p.add_argument("--m31-slo-incident-dir", default="reports/milestones/m31_slo_incident")
    p.add_argument("--report-dir", default="reports/operator_summary")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    metrics_dir = Path(str(args.metrics_report_dir).strip())
    m30_post_dir = Path(str(args.m30_post_golive_dir).strip())
    m30_go_dir = Path(str(args.m30_golive_dir).strip())
    m31_dir = Path(str(args.m31_slo_incident_dir).strip())
    day = str(args.day).strip() if args.day else None

    md_path, js_path = generate_operator_daily_summary(
        events_path,
        report_dir,
        day=day,
        metrics_report_dir=metrics_dir,
        m30_post_golive_dir=m30_post_dir,
        m30_golive_dir=m30_go_dir,
        m31_slo_incident_dir=m31_dir,
    )
    out: Dict[str, Any] = {}
    try:
        out = json.loads(js_path.read_text(encoding="utf-8"))
    except Exception:
        out = {}

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        health = (
            out.get("system_health_status", {}).get("system_health_level")
            if isinstance(out.get("system_health_status"), dict)
            else "UNKNOWN"
        )
        tas = out.get("trading_activity_summary") if isinstance(out.get("trading_activity_summary"), dict) else {}
        print(
            f"day={out.get('day')} health={health} run_total={int(tas.get('run_total') or 0)} "
            f"executions_total={int(tas.get('executions_total') or 0)} blocked_total={int(tas.get('blocked_total') or 0)} "
            f"report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

