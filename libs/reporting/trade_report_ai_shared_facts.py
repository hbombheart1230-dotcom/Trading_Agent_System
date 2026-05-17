from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional

from libs.reporting.trade_pnl_estimate import infer_exit_fill_pnl_pct_from_account_snapshot
from libs.reporting.trade_report_common import report_clip

logger = logging.getLogger(__name__)


def first_nonempty_text(*values: Any, max_len: int = 240) -> str:
    for value in values:
        text = report_clip(value, max_len=max_len)
        if text:
            return text
    return ""


def as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def as_action(value: Any) -> str:
    text = report_clip(value, max_len=24).upper()
    if text in {"NOOP", "NONE"}:
        return "WAIT"
    return text


def as_status(value: Any) -> str:
    text = report_clip(value, max_len=32).lower()
    if text == "opened":
        return "open"
    if text == "closed_out":
        return "closed"
    return text


def action_from_exit_reason(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "sell" in text or "매도" in text or "청산" in text:
        return "SELL"
    return ""


def is_open_position_placeholder_reason(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    markers = (
        "no_position",
        "no position",
        "position is still open",
        "monitor is watching for exit",
        "still open",
        "포지션이 아직",
    )
    return any(token in text for token in markers)


def is_hold_placeholder_exit_reason(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = re.sub(r"^sell\s+was\s+triggered\s+because\s*", "", text, flags=re.IGNORECASE)
    normalized = normalized.strip().strip(".").strip().lower()
    return normalized in {"hold", "hold_position", "holding", "보유", "보유 유지"} or "because hold" in text.lower()


def num_opt(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None

def present_fact(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.lower() != "unavailable"
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def set_fact_if_missing(
    *,
    resolved: Dict[str, Any],
    data_source: Dict[str, str],
    field: str,
    value: Any,
    source: str,
) -> None:
    if not present_fact(value):
        return
    if field == "exit_reason" and (
        is_open_position_placeholder_reason(value) or is_hold_placeholder_exit_reason(value)
    ):
        return
    if present_fact(resolved.get(field)):
        if str(resolved.get(field)) != str(value):
            logger.debug(
                "trade_fact_conflict field=%s kept_source=%s kept_value=%r ignored_source=%s ignored_value=%r",
                field,
                data_source.get(field),
                resolved.get(field),
                source,
                value,
            )
        return
    resolved[field] = value
    data_source[field] = source


def resolve_trade_facts_with_precedence(
    story_input: Dict[str, Any],
    *,
    load_trade_read_model_hint: Callable[[Dict[str, Any]], Dict[str, Any]],
    humanize_duration_text: Callable[..., str],
    actual_lifecycle_action: Callable[[Dict[str, Any]], str],
) -> Dict[str, Any]:
    lifecycle = as_dict(story_input.get("trade_lifecycle"))
    lifecycle_summary = as_dict(story_input.get("lifecycle_summary"))
    lifecycle_bundle = as_dict(story_input.get("lifecycle_bundle"))
    lifecycle_bundle_outcome = as_dict(lifecycle_bundle.get("trade_outcome"))
    lifecycle_summary_obj = as_dict(lifecycle.get("summary"))
    lifecycle_entry = as_dict(lifecycle.get("entry"))
    lifecycle_exit = as_dict(lifecycle.get("exit"))

    canonical = as_dict(story_input.get("canonical_agent_artifacts"))
    canonical_monitor = as_dict(canonical.get("monitor"))
    entry_summary = as_dict(story_input.get("entry_summary"))
    hold_summary = as_dict(story_input.get("holding_summary"))
    exit_summary = as_dict(story_input.get("exit_summary"))
    exit_monitor_context = as_dict(exit_summary.get("monitor_context"))
    execution_outcome = as_dict(story_input.get("execution_outcome_human"))
    execution_details = as_dict(story_input.get("exit_execution_details")) or as_dict(story_input.get("execution_details"))
    monitor_reason = as_dict(story_input.get("monitor_reason_human"))
    trade_read_model = load_trade_read_model_hint(story_input)
    trade_read_model_context = trade_read_model.get("context") if isinstance(trade_read_model.get("context"), dict) else {}

    def _monitor_mark_pnl_pct() -> Optional[float]:
        position_snapshot = as_dict(canonical_monitor.get("position_snapshot"))
        for candidate in (
            monitor_reason.get("pnl_pct"),
            monitor_reason.get("gross_pnl_ratio"),
            monitor_reason.get("technical_pnl_ratio"),
            monitor_reason.get("raw_pnl_ratio"),
            monitor_reason.get("stop_pnl_ratio"),
        ):
            value = num_opt(candidate)
            if value is not None:
                return value
        current = num_opt(
            monitor_reason.get("current_price")
            or canonical_monitor.get("current_price")
            or position_snapshot.get("current_price")
        )
        average = num_opt(
            monitor_reason.get("average_price")
            or monitor_reason.get("avg_price")
            or canonical_monitor.get("average_price")
            or canonical_monitor.get("avg_price")
            or position_snapshot.get("avg_price")
        )
        if current is None or average is None or average <= 0:
            return None
        return (current - average) / average

    fields = ["action", "status", "holding_duration", "exit_reason", "pnl", "pnl_pct"]
    resolved: Dict[str, Any] = {key: "unavailable" for key in fields}
    data_source: Dict[str, str] = {key: "unavailable" for key in fields}

    broker_pnl_source = first_nonempty_text(
        execution_details.get("pnl_truth_source"),
        execution_details.get("broker_day_truth_source"),
        max_len=80,
    )
    if execution_details.get("broker_realized_pnl") not in (None, ""):
        resolved["pnl"] = execution_details.get("broker_realized_pnl")
        data_source["pnl"] = broker_pnl_source or "kiwoom_day_trade"
    if execution_details.get("broker_realized_pnl_pct") not in (None, ""):
        resolved["pnl_pct"] = execution_details.get("broker_realized_pnl_pct")
        data_source["pnl_pct"] = broker_pnl_source or "kiwoom_day_trade"
    inferred_pnl = infer_exit_fill_pnl_pct_from_account_snapshot(story_input)
    if resolved.get("pnl_pct") in (None, "", "unavailable") and inferred_pnl.get("pnl_pct") not in (None, ""):
        resolved["pnl_pct"] = inferred_pnl.get("pnl_pct")
        resolved["pnl_truth_source"] = inferred_pnl.get("pnl_truth_source")
        data_source["pnl_pct"] = inferred_pnl.get("pnl_truth_source") or "estimate"

    # 1) lifecycle / trade_lifecycle.json
    for candidate in (
        as_action(lifecycle.get("action")),
        as_action(lifecycle.get("final_action")),
        as_action(lifecycle_summary_obj.get("action")),
        as_action(lifecycle_summary_obj.get("final_action")),
        as_action(lifecycle_entry.get("action")),
        as_action(lifecycle_exit.get("action")),
        as_action(lifecycle_summary.get("action")),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="lifecycle")
    for candidate in (
        as_status(lifecycle.get("status")),
        as_status(lifecycle.get("trade_status")),
        as_status(lifecycle.get("lifecycle_status")),
        as_status(lifecycle_summary_obj.get("status")),
        as_status(lifecycle_bundle.get("status")),
        as_status(story_input.get("trade_lifecycle_status")),
        as_status(lifecycle_summary.get("status")),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="status", value=candidate, source="lifecycle")
    for candidate in (
        report_clip(lifecycle.get("holding_duration"), max_len=80),
        report_clip(lifecycle_summary_obj.get("holding_duration"), max_len=80),
        report_clip(lifecycle_bundle_outcome.get("holding_time"), max_len=80),
        report_clip(lifecycle_summary.get("holding_duration"), max_len=80),
    ):
        set_fact_if_missing(
            resolved=resolved,
            data_source=data_source,
            field="holding_duration",
            value=candidate,
            source="lifecycle",
        )
    for candidate in (
        report_clip(lifecycle.get("exit_reason"), max_len=280),
        report_clip(lifecycle_summary_obj.get("exit_reason_human"), max_len=280),
        report_clip(lifecycle_summary_obj.get("exit_reason"), max_len=280),
        report_clip(lifecycle_bundle_outcome.get("exit_reason"), max_len=280),
        report_clip(lifecycle_exit.get("reason_human"), max_len=280),
        report_clip(lifecycle_summary.get("exit_reason_human"), max_len=280),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="lifecycle")

    for candidate in (
        report_clip(monitor_reason.get("trigger_type"), max_len=280),
        report_clip(monitor_reason.get("active_exit_axis"), max_len=280),
        report_clip(monitor_reason.get("exit_reason"), max_len=280),
        report_clip(monitor_reason.get("summary"), max_len=280),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="monitor")
    for candidate in (
        lifecycle.get("pnl"),
        lifecycle_summary_obj.get("pnl"),
        lifecycle_bundle_outcome.get("pnl"),
        lifecycle_summary.get("pnl"),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl", value=candidate, source="lifecycle")
    for candidate in (
        lifecycle.get("pnl_pct"),
        lifecycle.get("return_pct"),
        lifecycle_summary_obj.get("pnl_pct"),
        lifecycle_summary_obj.get("return_pct"),
        lifecycle_bundle_outcome.get("return_pct"),
        lifecycle_summary.get("pnl_pct"),
        lifecycle_summary.get("return_pct"),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="lifecycle")

    # 2) canonical monitor decision artifact
    for candidate in (
        as_action(canonical_monitor.get("decision_action")),
        as_action(canonical_monitor.get("decision")),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="monitor")
    for candidate in (
        report_clip(canonical_monitor.get("exit_reason"), max_len=280),
        report_clip(canonical_monitor.get("primary_reason_text"), max_len=280),
        report_clip(canonical_monitor.get("primary_reason_code"), max_len=280),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="monitor")
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="pnl",
        value=canonical_monitor.get("pnl"),
        source="monitor",
    )
    for candidate in (canonical_monitor.get("pnl_pct"), canonical_monitor.get("return_pct")):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="monitor")
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="holding_duration",
        value=report_clip(canonical_monitor.get("holding_duration"), max_len=80),
        source="monitor",
    )

    # 3) entry.json / hold.json / exit.json
    for candidate in (
        as_action(exit_summary.get("action")),
        as_action(entry_summary.get("action")),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="trade_artifact")
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="status",
        value=as_status(story_input.get("status")),
        source="trade_artifact",
    )
    for candidate in (
        report_clip(hold_summary.get("holding_duration"), max_len=80),
        report_clip(hold_summary.get("holding_time"), max_len=80),
        report_clip(hold_summary.get("hold_duration"), max_len=80),
        humanize_duration_text("", fallback_seconds=hold_summary.get("hold_duration_sec")),
    ):
        set_fact_if_missing(
            resolved=resolved,
            data_source=data_source,
            field="holding_duration",
            value=candidate,
            source="trade_artifact",
        )
    for candidate in (
        report_clip(exit_summary.get("reason_human"), max_len=280),
        report_clip(exit_monitor_context.get("exit_reason"), max_len=280),
        report_clip(exit_monitor_context.get("reason"), max_len=280),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="trade_artifact")
    for candidate in (
        execution_outcome.get("pnl"),
        as_dict(exit_summary.get("execution_context")).get("pnl"),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl", value=candidate, source="trade_artifact")
    for candidate in (
        execution_outcome.get("pnl_pct"),
        execution_outcome.get("return_pct"),
        as_dict(exit_summary.get("execution_context")).get("pnl_pct"),
        as_dict(exit_summary.get("execution_context")).get("return_pct"),
    ):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="trade_artifact")

    # 4) evidence (strategist / scanner)
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="exit_reason",
        value=report_clip(as_dict(story_input.get("monitor_timeline")).get("summary"), max_len=280),
        source="evidence",
    )

    # 5) fallback / inference (last resort only)
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="action",
        value=as_action(actual_lifecycle_action(story_input)),
        source="fallback",
    )
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="status",
        value=as_status(story_input.get("status")),
        source="fallback",
    )
    set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="pnl",
        value=monitor_reason.get("pnl"),
        source="fallback",
    )
    for candidate in (monitor_reason.get("pnl_pct"), _monitor_mark_pnl_pct()):
        set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="fallback")

    # Closed-lifecycle reconciliation:
    # If monitor entry decision(BUY) was captured first but lifecycle is closed, prefer
    # explicit exit-side action evidence to prevent BUY+closed inconsistencies.
    resolved_status = as_status(resolved.get("status"))
    resolved_action = as_action(resolved.get("action"))
    if resolved_status == "closed" and resolved_action not in {"SELL", "EXIT"}:
        reconciled_action = ""
        for candidate in (
            as_action(exit_summary.get("action")),
            as_action(lifecycle_exit.get("action")),
            as_action(as_dict(story_input.get("execution")).get("action")),
            as_action(story_input.get("action")),
            action_from_exit_reason(resolved.get("exit_reason")),
            action_from_exit_reason(exit_summary.get("reason_human")),
            action_from_exit_reason(lifecycle.get("exit_reason")),
        ):
            if candidate in {"SELL", "EXIT"}:
                reconciled_action = candidate
                break
        if reconciled_action:
            resolved["action"] = reconciled_action
            data_source["action"] = "closed_lifecycle_reconcile"

    existing_exit_reason_text = str(resolved.get("exit_reason") or "").strip().lower()
    if (
        resolved_status == "closed"
        and as_action(resolved.get("action")) in {"SELL", "EXIT"}
        and (
            "sell 실행 및 잔여수량" in existing_exit_reason_text
            or "sell_execution_confirmed" in existing_exit_reason_text
            or "full_sell_quantity_reconciled" in existing_exit_reason_text
        )
    ):
        resolved["exit_reason"] = "exit_trigger_not_captured"
        resolved["exit_execution_status"] = "sell_execution_full_close_confirmed"
        data_source["exit_reason"] = "closed_lifecycle_reconcile"
        data_source["exit_execution_status"] = "closed_lifecycle_reconcile"
    if (
        resolved_status == "closed"
        and as_action(resolved.get("action")) in {"SELL", "EXIT"}
        and (
            resolved.get("exit_reason") in (None, "", "unavailable")
            or is_hold_placeholder_exit_reason(resolved.get("exit_reason"))
        )
    ):
        resolved["exit_reason"] = "exit_trigger_not_captured"
        resolved["exit_execution_status"] = "sell_execution_full_close_confirmed"
        data_source["exit_reason"] = "closed_lifecycle_reconcile"
        data_source["exit_execution_status"] = "closed_lifecycle_reconcile"

    monitor_decision = {
        "phase": report_clip(canonical_monitor.get("decision_phase"), max_len=32) or "unavailable",
        "action": report_clip(canonical_monitor.get("decision_action"), max_len=32) or "unavailable",
        "status": report_clip(canonical_monitor.get("decision_status"), max_len=32) or "unavailable",
        "reason_code": report_clip(
            canonical_monitor.get("primary_reason_text") or canonical_monitor.get("primary_reason_code"),
            max_len=220,
        )
        or "unavailable",
        "thresholds": as_dict(canonical_monitor.get("threshold_snapshot")),
    }
    trade_model_monitor = trade_read_model_context.get("monitor") if isinstance(trade_read_model_context.get("monitor"), dict) else {}
    if monitor_decision.get("reason_code") in {"", "unavailable"}:
        trade_monitor_reason = report_clip(
            trade_model_monitor.get("exit_trigger") or trade_model_monitor.get("primary_blocker"),
            max_len=220,
        )
        if trade_monitor_reason:
            monitor_decision["reason_code"] = trade_monitor_reason
    if not monitor_decision.get("thresholds") and isinstance(trade_model_monitor.get("thresholds_snapshot"), dict):
        monitor_decision["thresholds"] = as_dict(trade_model_monitor.get("thresholds_snapshot"))
    return {
        **resolved,
        "broker_fee": execution_details.get("broker_fee"),
        "broker_tax": execution_details.get("broker_tax"),
        "pnl_truth_source": resolved.get("pnl_truth_source") or broker_pnl_source or "unavailable",
        "broker_day_truth_source": resolved.get("broker_day_truth_source")
        if resolved.get("broker_day_truth_source") not in (None, "")
        else execution_details.get("broker_day_truth_source"),
        "broker_day_match_mode": resolved.get("broker_day_match_mode")
        if resolved.get("broker_day_match_mode") not in (None, "")
        else execution_details.get("broker_day_match_mode"),
        "broker_day_authoritative": bool(
            resolved.get("broker_day_authoritative")
            if resolved.get("broker_day_authoritative") not in (None, "")
            else execution_details.get("broker_day_authoritative")
        ),
        "broker_day_row_count": resolved.get("broker_day_row_count")
        if resolved.get("broker_day_row_count") not in (None, "")
        else execution_details.get("broker_day_row_count"),
        "broker_truth_attempted": bool(execution_details.get("broker_truth_attempted")),
        "broker_truth_error": execution_details.get("broker_truth_error"),
        "broker_day_truth_attempted": bool(execution_details.get("broker_day_truth_attempted")),
        "broker_day_truth_error": execution_details.get("broker_day_truth_error"),
        "data_source": data_source,
        "monitor_decision": monitor_decision,
    }
