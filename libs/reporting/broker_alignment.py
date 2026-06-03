from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol
from libs.read.kiwoom_order_fill_reader import KiwoomOrderFillReader
from libs.read.kiwoom_account_snapshot_collector import save_kiwoom_account_snapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _first_call_payload(snapshot: Dict[str, Any], api_id: str) -> Dict[str, Any]:
    calls = snapshot.get("calls") if isinstance(snapshot.get("calls"), list) else []
    for call in calls:
        if not isinstance(call, dict):
            continue
        if str(call.get("api_id") or "").strip() != api_id:
            continue
        payload = call.get("payload")
        return payload if isinstance(payload, dict) else {}
    return {}


def _extract_day_trade_diary_rows(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = _first_call_payload(snapshot, "ka10170")
    rows = payload.get("tdy_trde_diary") if isinstance(payload.get("tdy_trde_diary"), list) else []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("stk_cd") or row.get("stk_cd_1"), allow_test_symbols=True)
        if not symbol:
            continue
        buy_qty = _safe_int(row.get("buy_qty"))
        sell_qty = _safe_int(row.get("sell_qty"))
        out.append(
            {
                "symbol": symbol,
                "symbol_name": str(row.get("stk_nm") or "").strip(),
                "buy_qty": buy_qty,
                "sell_qty": sell_qty,
                "buy_avg_price": _safe_float(row.get("buy_avg_pric") or row.get("buy_avg_price")),
                "sell_avg_price": _safe_float(row.get("sel_avg_pric") or row.get("sell_avg_price")),
                "buy_amount": _safe_float(row.get("buy_amt")),
                "sell_amount": _safe_float(row.get("sell_amt")),
                "realized_pnl": _safe_float(row.get("pl_amt") or row.get("realized_pnl")),
                "pnl_pct": _safe_float(row.get("prft_rt") or row.get("pnl_ratio")),
                "commission_tax": _safe_float(row.get("cmsn_alm_tax") or row.get("fee_tax")),
                "closed_by_day_trade_diary": buy_qty > 0 and sell_qty >= buy_qty,
                "source": "kiwoom.ka10170",
            }
        )
    return out


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
        closed_symbols = snapshot.get("day_trade_closed_symbols") if isinstance(snapshot.get("day_trade_closed_symbols"), list) else []
        lines.extend(
            [
                "",
                "## Account Snapshot",
                "",
                f"- Status: {snapshot.get('status')}",
                f"- Path: `{snapshot.get('path') or '-'}`",
                f"- Calls: {snapshot.get('ok_count') or 0}/{snapshot.get('api_call_count') or 0} ok",
                f"- Day trade diary rows: {int(snapshot.get('day_trade_diary_count') or 0)}",
                f"- Day trade closed symbols: {', '.join(str(x) for x in closed_symbols) if closed_symbols else '-'}",
            ]
        )
        if snapshot.get("error"):
            lines.append(f"- Error: `{snapshot.get('error')}`")
    return "\n".join(lines).rstrip() + "\n"


def build_broker_alignment_report(events_path: Path, reports_root: Path, day: str) -> Dict[str, Any]:
    snapshot_summary: Dict[str, Any] = {}
    try:
        snapshot = save_kiwoom_account_snapshot(day=day, trigger="report_generation")
        day_trade_diary_rows = _extract_day_trade_diary_rows(snapshot)
        day_trade_closed_symbols = sorted(
            {
                str(row.get("symbol") or "").strip()
                for row in day_trade_diary_rows
                if isinstance(row, dict) and bool(row.get("closed_by_day_trade_diary"))
            }
        )
        snapshot_summary = {
            "status": "ok",
            "path": snapshot.get("path"),
            "latest_path": snapshot.get("latest_path"),
            "api_call_count": (snapshot.get("summary") or {}).get("api_call_count"),
            "ok_count": (snapshot.get("summary") or {}).get("ok_count"),
            "error_count": (snapshot.get("summary") or {}).get("error_count"),
            "day_trade_diary_count": len(day_trade_diary_rows),
            "day_trade_closed_symbols": day_trade_closed_symbols,
            "day_trade_diary_rows": day_trade_diary_rows,
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
