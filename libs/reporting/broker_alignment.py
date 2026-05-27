from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from libs.read.kiwoom_order_fill_reader import KiwoomOrderFillReader
from libs.read.kiwoom_account_snapshot_collector import save_kiwoom_account_snapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def render_broker_alignment_markdown(report: Dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Broker Trade Reconciliation",
        "",
        f"- Day: {report.get('day')}",
        f"- Event log: `{report.get('event_log_path')}`",
        f"- Generated at: {report.get('generated_at')}",
        f"- Status: {report.get('status')}",
        "",
        "## Summary",
        "",
        f"- Local executions: {int(summary.get('local_total') or 0)}",
        f"- Broker rows: {int(summary.get('broker_total') or 0)}",
        f"- Matched by ord_no: {int(summary.get('matched_by_ord_no') or 0)}",
        f"- Missing in local: {int(summary.get('missing_in_local_total') or 0)}",
        f"- Missing in broker: {int(summary.get('missing_in_broker_total') or 0)}",
    ]
    if report.get("error"):
        lines.append(f"- Error: `{report.get('error')}`")
    snapshot = report.get("account_snapshot") if isinstance(report.get("account_snapshot"), dict) else {}
    if snapshot:
        lines.extend(
            [
                "",
                "## Account Snapshot",
                "",
                f"- Status: {snapshot.get('status')}",
                f"- Path: `{snapshot.get('path') or '-'}`",
                f"- Calls: {snapshot.get('ok_count') or 0}/{snapshot.get('api_call_count') or 0} ok",
            ]
        )
        if snapshot.get("error"):
            lines.append(f"- Error: `{snapshot.get('error')}`")
    return "\n".join(lines).rstrip() + "\n"


def build_broker_alignment_report(events_path: Path, reports_root: Path, day: str) -> Dict[str, Any]:
    snapshot_summary: Dict[str, Any] = {}
    try:
        snapshot = save_kiwoom_account_snapshot(day=day, trigger="report_generation")
        snapshot_summary = {
            "status": "ok",
            "path": snapshot.get("path"),
            "latest_path": snapshot.get("latest_path"),
            "api_call_count": (snapshot.get("summary") or {}).get("api_call_count"),
            "ok_count": (snapshot.get("summary") or {}).get("ok_count"),
            "error_count": (snapshot.get("summary") or {}).get("error_count"),
        }
    except Exception as exc:
        snapshot_summary = {"status": "error", "error": str(exc)}
    try:
        reader = KiwoomOrderFillReader.from_env()
        report = reader.get_daily_reconciliation_report(day=day, event_log_path=events_path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        ok = int(summary.get("missing_in_local_total") or 0) == 0 and int(summary.get("missing_in_broker_total") or 0) == 0
        report["status"] = "ok" if ok else "mismatch"
    except Exception as exc:
        report = {
            "day": day,
            "generated_at": _utc_now_iso(),
            "event_log_path": str(events_path),
            "status": "unavailable",
            "error": str(exc),
            "summary": {
                "local_total": 0,
                "broker_total": 0,
                "matched_by_ord_no": 0,
                "missing_in_local_total": 0,
                "missing_in_broker_total": 0,
                "missing_in_local": [],
                "missing_in_broker": [],
            },
        }
    report["account_snapshot"] = snapshot_summary
    report_dir = reports_root / "reconciliation"
    json_path = report_dir / f"broker_trade_reconciliation_{day}.json"
    md_path = report_dir / f"broker_trade_reconciliation_{day}.md"
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_broker_alignment_markdown(report), encoding="utf-8")
        report["report_json_path"] = str(json_path)
        report["report_md_path"] = str(md_path)
    except Exception as exc:
        report["write_error"] = str(exc)
    return report
