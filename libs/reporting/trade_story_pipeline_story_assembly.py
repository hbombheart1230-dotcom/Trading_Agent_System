from __future__ import annotations

from typing import Any, Dict, List

from libs.reporting.trade_report_common import clip_text as clip, utc_now_iso
from libs.reporting.trade_reporter_status_text import normalize_reporter_status_human


def build_timeline(
    *,
    commander: Dict[str, Any],
    market_context_human: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
    guard_reason_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_ts = str(commander.get("route_ts") or "")
    execution_ts = str(execution.get("ts") or "")
    return [
        {"step": "strategist_frame", "status": "ok", "ts": route_ts, "summary": market_context_human.get("summary") or ""},
        {"step": "scanner_ranking", "status": "ok", "ts": route_ts, "summary": scanner_reason_human.get("summary") or ""},
        {"step": "monitor_signal", "status": "ok", "ts": execution_ts, "summary": monitor_reason_human.get("summary") or ""},
        {"step": "supervisor_approval", "status": "ok", "ts": execution_ts, "summary": guard_reason_human.get("summary") or ""},
        {"step": "broker_result", "status": "ok", "ts": execution_ts, "summary": execution_outcome_human.get("summary") or ""},
        {"step": "reporter_output", "status": "ok", "ts": utc_now_iso(), "summary": reporter_status_human.get("summary") or ""},
    ]


def collect_story_warnings(
    *,
    story_contract: Dict[str, Any],
    market_context_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
) -> List[str]:
    warnings = [str(x or "") for x in list(story_contract.get("warnings") or []) if str(x or "").strip()]
    if market_context_human.get("defensive_mode"):
        warnings.append("Macro or volatility context was defensive for this run.")
    if reporter_status_human.get("status") == "pending":
        warnings.append("Reporter evaluation is pending because same-day run linkage was not available yet.")
    elif reporter_status_human.get("status") == "missing":
        warnings.append("Reporter evaluation is missing because the same-day analysis file was not generated yet.")
    for row in list(filters_human.get("checks") or []):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").upper()
        if status in {"FAIL", "PARTIAL", "NOT_AVAILABLE"}:
            warnings.append(f"{row.get('name')}: {status} ({row.get('detail') or ''})")
    if execution_outcome_human.get("outcome") == "failed":
        warnings.append("Execution did not complete successfully and needs operator review.")
    deduped: List[str] = []
    for item in warnings:
        text = clip(item, max_len=260)
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:10]


def normalize_trade_lifecycle_for_story_input(
    bundle_out: Dict[str, Any],
    *,
    trade_lifecycle: Dict[str, Any] | None = None,
    existing_story_input: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    lifecycle_src = (
        trade_lifecycle
        if isinstance(trade_lifecycle, dict)
        else bundle_out.get("lifecycle")
        if isinstance(bundle_out.get("lifecycle"), dict)
        else {}
    )
    if not lifecycle_src:
        return {}

    out = dict(lifecycle_src)
    entry_ctx = (
        lifecycle_src.get("entry")
        if isinstance(lifecycle_src.get("entry"), dict)
        else bundle_out.get("entry")
        if isinstance(bundle_out.get("entry"), dict)
        else {}
    )
    holding_ctx = (
        lifecycle_src.get("holding")
        if isinstance(lifecycle_src.get("holding"), dict)
        else lifecycle_src.get("hold")
        if isinstance(lifecycle_src.get("hold"), dict)
        else bundle_out.get("holding")
        if isinstance(bundle_out.get("holding"), dict)
        else bundle_out.get("hold")
        if isinstance(bundle_out.get("hold"), dict)
        else {}
    )
    exit_ctx = (
        lifecycle_src.get("exit")
        if isinstance(lifecycle_src.get("exit"), dict)
        else bundle_out.get("exit")
        if isinstance(bundle_out.get("exit"), dict)
        else {}
    )
    summary_ctx = (
        lifecycle_src.get("summary")
        if isinstance(lifecycle_src.get("summary"), dict)
        else bundle_out.get("trade_outcome")
        if isinstance(bundle_out.get("trade_outcome"), dict)
        else bundle_out.get("summary")
        if isinstance(bundle_out.get("summary"), dict)
        else {}
    )
    reporter_ctx = (
        lifecycle_src.get("reporter")
        if isinstance(lifecycle_src.get("reporter"), dict)
        else {}
    )
    if not reporter_ctx:
        reporter_status_human = normalize_reporter_status_human(
            bundle_out.get("reporter_status_human")
            if isinstance(bundle_out.get("reporter_status_human"), dict)
            else {}
        )
        if reporter_status_human:
            reporter_ctx = {
                "status_human": str(reporter_status_human.get("status") or ""),
                "summary": str(reporter_status_human.get("summary") or ""),
                "grade": str(reporter_status_human.get("grade") or ""),
                "improvement_points": list(reporter_status_human.get("bullets") or []),
            }

    out["entry"] = dict(entry_ctx)
    out["holding"] = dict(holding_ctx)
    out["exit"] = dict(exit_ctx)
    out["summary"] = dict(summary_ctx)
    out["reporter"] = dict(reporter_ctx)
    out["trade_id"] = str(
        out.get("trade_id")
        or bundle_out.get("trade_id")
        or (existing_story_input or {}).get("trade_id")
        or ""
    ).strip()
    out["symbol"] = str(
        out.get("symbol")
        or bundle_out.get("symbol")
        or (entry_ctx.get("symbol") if isinstance(entry_ctx, dict) else "")
        or (exit_ctx.get("symbol") if isinstance(exit_ctx, dict) else "")
        or (existing_story_input or {}).get("symbol")
        or ""
    ).strip()
    out["status"] = str(
        out.get("status")
        or bundle_out.get("trade_lifecycle_status")
        or (existing_story_input or {}).get("status")
        or ""
    ).strip()
    if not out.get("execution_details") and isinstance(bundle_out.get("execution_details"), dict):
        out["execution_details"] = dict(bundle_out.get("execution_details") or {})
    if (
        not out.get("same_day_reporter_linkage")
        and isinstance(bundle_out.get("same_day_reporter_linkage"), dict)
    ):
        out["same_day_reporter_linkage"] = dict(bundle_out.get("same_day_reporter_linkage") or {})
    if (
        not out.get("failure_classification")
        and isinstance(bundle_out.get("failure_classification"), dict)
    ):
        out["failure_classification"] = dict(bundle_out.get("failure_classification") or {})
    return out


def compact_canonical_monitor(canonical_monitor: Dict[str, Any] | None) -> Dict[str, Any]:
    monitor = canonical_monitor if isinstance(canonical_monitor, dict) else {}
    compact = {
        "decision_action": monitor.get("decision_action"),
        "exit_reason": monitor.get("exit_reason"),
        "current_price": monitor.get("current_price"),
        "avg_price": monitor.get("avg_price"),
        "account_pnl_ratio": monitor.get("account_pnl_ratio"),
        "effective_pnl_ratio": monitor.get("effective_pnl_ratio"),
        "price_source": monitor.get("price_source"),
    }
    if any(value not in (None, "", [], {}) for value in compact.values()):
        return compact
    return {}
