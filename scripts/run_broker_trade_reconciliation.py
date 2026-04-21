from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.read.kiwoom_order_fill_reader import (
    KiwoomOrderFillReader,
    load_local_execution_rows,
    reconcile_rows,
)


def _render_md(report: Dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Broker Trade Reconciliation",
        "",
        f"- Day: {report.get('day')}",
        f"- Event log: `{report.get('event_log_path')}`",
        f"- Generated at: {report.get('generated_at')}",
        "",
        "## Summary",
        "",
        f"- Local executions: {int(summary.get('local_total') or 0)}",
        f"- Broker rows: {int(summary.get('broker_total') or 0)}",
        f"- Matched by ord_no: {int(summary.get('matched_by_ord_no') or 0)}",
        f"- Broker window limited: {bool(summary.get('broker_window_limited'))}",
        f"- Missing in local: {int(summary.get('missing_in_local_total') or 0)}",
        f"- Missing in broker: {int(summary.get('missing_in_broker_total') or 0)}",
        "",
        "## Local Counts",
    ]
    local_counts = summary.get("local_counts") if isinstance(summary.get("local_counts"), dict) else {}
    if local_counts:
        lines.extend([f"- `{k}`: {v}" for k, v in local_counts.items()])
    else:
        lines.append("- none")
    lines.extend(["", "## Broker Counts"])
    broker_counts = summary.get("broker_counts") if isinstance(summary.get("broker_counts"), dict) else {}
    if broker_counts:
        lines.extend([f"- `{k}`: {v}" for k, v in broker_counts.items()])
    else:
        lines.append("- none")
    for title, key in (("Missing In Local", "missing_in_local"), ("Missing In Broker", "missing_in_broker")):
        lines.extend(["", f"## {title}"])
        rows = summary.get(key) if isinstance(summary.get(key), list) else []
        if not rows:
            lines.append("- none")
            continue
        for row in rows:
            lines.append(
                f"- ord_no={row.get('ord_no')} symbol={row.get('symbol')} side={row.get('side')} "
                f"qty={row.get('filled_qty') or row.get('qty') or row.get('order_qty')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Compare Kiwoom broker fill history with local execution events.")
    p.add_argument("--day", default=datetime.now(UTC).astimezone().date().isoformat())
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/reconciliation")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    day = str(args.day).strip()
    event_log_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    reader = KiwoomOrderFillReader.from_env()
    local_rows = load_local_execution_rows(event_log_path, day=day)
    broker_rows = reader.get_filled_rows_for_day(day=day)
    summary = reconcile_rows(local_rows, broker_rows)
    report = {
        "day": day,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "event_log_path": str(event_log_path),
        "summary": summary,
    }

    json_path = report_dir / f"broker_trade_reconciliation_{day}.json"
    md_path = report_dir / f"broker_trade_reconciliation_{day}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            f"day={day} matched={summary['matched_by_ord_no']} "
            f"missing_local={summary['missing_in_local_total']} "
            f"missing_broker={summary['missing_in_broker_total']} "
            f"report_json={json_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
