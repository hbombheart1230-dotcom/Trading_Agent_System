from __future__ import annotations

from typing import Any, Dict, List, Mapping

from libs.core.symbols import normalize_symbol
from libs.reporting.trade_story_pipeline import build_monitor_reason_human


def latest_exit_monitor_context_from_timeline(
    monitor_timeline: Mapping[str, Any] | None,
    *,
    exit_run_id: str,
    symbol: str,
) -> Dict[str, Any]:
    if not exit_run_id:
        return {}
    timeline = dict(monitor_timeline or {})
    rows_by_ts: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    collection_order = (
        "threshold_snapshots",
        "exit_decision_details",
        "cycle_summaries",
        "state_transitions",
    )
    for collection_name in collection_order:
        for row in list(timeline.get(collection_name) or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("run_id") or "").strip() != exit_run_id:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if not payload:
                continue
            ts = str(row.get("ts") or "").strip()
            if not ts:
                continue
            rows_by_ts.setdefault(ts, []).append((collection_name, dict(payload)))
    if not rows_by_ts:
        return {}

    latest_ts = sorted(rows_by_ts.keys())[-1]
    merged: Dict[str, Any] = {}
    for collection_name in collection_order:
        for row_collection, payload in rows_by_ts.get(latest_ts, []):
            if row_collection == collection_name:
                merged.update(payload)

    final_thresholds = merged.get("final_exit_thresholds")
    if isinstance(final_thresholds, dict) and not isinstance(merged.get("thresholds"), dict):
        merged["thresholds"] = dict(final_thresholds)
    triggered_rule = str(merged.get("triggered_rule") or "").strip()
    if triggered_rule:
        merged.setdefault("exit_reason", triggered_rule)
        merged.setdefault("trigger_type", triggered_rule)
        merged.setdefault("reason", triggered_rule)
    if bool(merged.get("exit_triggered")) and not str(merged.get("monitor_reason") or "").strip():
        merged["monitor_reason"] = "confirmed_exit_signal"
    if str(merged.get("intent_side") or "").strip().upper() == "SELL":
        merged.setdefault("posture", "SELL")
    if str(merged.get("current_posture") or "").strip().upper() == "SELL":
        merged.setdefault("posture", "SELL")
    merged.setdefault("run_id", exit_run_id)
    merged.setdefault("ts", latest_ts)
    if symbol:
        merged.setdefault("symbol", symbol)
        merged.setdefault("selected_symbol", symbol)
        merged.setdefault("monitor_symbol", symbol)
    merged["source"] = "monitor_timeline.latest_exit_run"
    return merged


def apply_latest_exit_monitor_context_from_timeline(
    lifecycle_bundle: Mapping[str, Any] | None,
    monitor_timeline: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    out = dict(lifecycle_bundle or {})
    exit_obj = out.get("exit") if isinstance(out.get("exit"), dict) else {}
    if not exit_obj:
        return out
    exit_run_id = str(exit_obj.get("run_id") or "").strip()
    symbol = normalize_symbol(
        out.get("symbol") or exit_obj.get("symbol") or "",
        allow_test_symbols=True,
    )
    latest_exit_monitor_context = latest_exit_monitor_context_from_timeline(
        monitor_timeline,
        exit_run_id=exit_run_id,
        symbol=symbol,
    )
    if not latest_exit_monitor_context:
        return out

    exit_obj = dict(exit_obj)
    monitor_context = (
        dict(exit_obj.get("monitor_context") or {})
        if isinstance(exit_obj.get("monitor_context"), dict)
        else {}
    )
    monitor_context = {**monitor_context, **latest_exit_monitor_context}
    exit_obj["monitor_context"] = monitor_context
    out["monitor"] = {
        **(out.get("monitor") if isinstance(out.get("monitor"), dict) else {}),
        **latest_exit_monitor_context,
    }
    monitor_reason_human = build_monitor_reason_human(
        monitor_context,
        {"action": str(exit_obj.get("action") or "SELL").strip().upper() or "SELL"},
    )
    out["monitor_reason_human"] = monitor_reason_human
    summary = str(monitor_reason_human.get("summary") or "").strip()
    if summary:
        exit_obj["reason_human"] = summary
        exit_obj["summary"] = summary
        trade_outcome = out.get("trade_outcome") if isinstance(out.get("trade_outcome"), dict) else {}
        if trade_outcome:
            trade_outcome = dict(trade_outcome)
            trade_outcome["exit_reason"] = summary
            out["trade_outcome"] = trade_outcome
    out["exit"] = exit_obj
    lifecycle_obj = out.get("lifecycle") if isinstance(out.get("lifecycle"), dict) else {}
    if lifecycle_obj:
        lifecycle_obj = dict(lifecycle_obj)
        lifecycle_obj["exit"] = exit_obj
        out["lifecycle"] = lifecycle_obj
    return out
