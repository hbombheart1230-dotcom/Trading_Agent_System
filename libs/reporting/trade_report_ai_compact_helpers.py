from __future__ import annotations

from typing import Any, Callable, Dict, List

from libs.reporting.trade_report_common import compact_scalar_dict, listify, report_clip

def tail_list(values: Any, *, max_items: int = 6, max_len: int = 220) -> List[str]:
    if not isinstance(values, list):
        return []
    return listify(values[-max(1, max_items) :], max_items=max_items, max_len=max_len)


def compact_event_row(row: Any) -> Dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    description = (
        item.get("description")
        or item.get("summary")
        or item.get("reason_human")
        or item.get("reason")
        or item.get("monitor_reason")
        or item.get("event_name")
        or item.get("event")
        or ""
    )
    out: Dict[str, Any] = {
        "ts": report_clip(item.get("ts"), max_len=40),
        "event": report_clip(item.get("event") or item.get("event_name"), max_len=80),
        "stage": report_clip(item.get("stage") or item.get("agent"), max_len=48),
        "action": report_clip(item.get("action") or item.get("side"), max_len=32),
        "description": report_clip(description, max_len=220),
    }
    return {key: value for key, value in out.items() if value not in {"", None}}


def compact_timeline_rows(values: Any, *, head: int = 3, tail: int = 9) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    picked: List[Any] = []
    picked.extend(values[: max(0, head)])
    if len(values) > head:
        picked.extend(values[-max(0, tail) :])
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in picked:
        compact = compact_event_row(row)
        marker = (
            str(compact.get("ts") or ""),
            str(compact.get("event") or ""),
            str(compact.get("description") or ""),
        )
        if not compact or marker in seen:
            continue
        seen.add(marker)
        out.append(compact)
    return out[:12]


def compact_monitor_snapshot(
    section: Any,
    *,
    compact_entry_candidate_cascade: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    policy_ref = data.get("policy_ref") if isinstance(data.get("policy_ref"), dict) else {}
    stop_trace = data.get("monitor_stop_policy_trace") if isinstance(data.get("monitor_stop_policy_trace"), dict) else {}
    out: Dict[str, Any] = {
        "posture": report_clip(data.get("posture"), max_len=32),
        "trigger_type": report_clip(data.get("trigger_type"), max_len=48),
        "summary": report_clip(data.get("summary"), max_len=320),
        "bullets": listify(data.get("bullets"), max_items=6, max_len=220),
        "position_age_seconds": data.get("position_age_seconds"),
        "hard_stop_pct": data.get("hard_stop_pct") or stop_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": data.get("adaptive_stop_loss_pct") or stop_trace.get("adaptive_stop_loss_pct"),
        "stop_loss_pct": data.get("stop_loss_pct") or stop_trace.get("stop_loss_pct"),
        "effective_stop_loss_pct": data.get("effective_stop_loss_pct") or stop_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": report_clip(data.get("effective_stop_reason"), max_len=80),
        "trailing_stop_pct": data.get("trailing_stop_pct") or stop_trace.get("trailing_stop_pct"),
        "take_profit_pct": data.get("take_profit_pct") or stop_trace.get("take_profit_pct"),
        "strategist_baseline_stop_loss_pct": data.get("strategist_baseline_stop_loss_pct")
        or stop_trace.get("strategist_baseline_stop_loss_pct"),
        "strategist_baseline_take_profit_pct": data.get("strategist_baseline_take_profit_pct")
        or stop_trace.get("strategist_baseline_take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": data.get("strategist_baseline_trailing_stop_pct")
        or stop_trace.get("strategist_baseline_trailing_stop_pct"),
        "exit_triggered": data.get("exit_triggered"),
        "current_price": data.get("current_price"),
        "average_price": data.get("average_price"),
        "peak_price": data.get("peak_price"),
        "current_drawdown": data.get("current_drawdown"),
        "peak_drawdown": data.get("peak_drawdown"),
        "vwap_distance": data.get("vwap_distance"),
        "active_exit_axis": report_clip(data.get("active_exit_axis"), max_len=48),
        "watch_axes": listify(data.get("watch_axes"), max_items=5, max_len=80),
        "confirm_required": data.get("confirm_required"),
        "confirm_count": data.get("confirm_count"),
        "guard_blocked": data.get("guard_blocked"),
        "guard_reason": report_clip(data.get("guard_reason"), max_len=120),
        "decision_reason_chain": listify(data.get("decision_reason_chain"), max_items=5, max_len=120),
        "entry_check_summary": report_clip(data.get("entry_check_summary"), max_len=240),
        "entry_blockers": listify(data.get("entry_blockers"), max_items=6, max_len=120),
        "threshold_shortfalls": listify(data.get("threshold_shortfalls"), max_items=4, max_len=160),
        "entry_metrics": compact_scalar_dict(data.get("entry_metrics"), max_items=10, max_len=120),
        "entry_thresholds": compact_scalar_dict(data.get("entry_thresholds"), max_items=8, max_len=120),
        "policy_ref": compact_scalar_dict(policy_ref, max_items=8, max_len=120),
        "timing_assessment": compact_scalar_dict(data.get("timing_assessment"), max_items=8, max_len=120),
        "thresholds_guards_used": compact_scalar_dict(data.get("thresholds_guards_used"), max_items=8, max_len=120),
        "received_policy": compact_scalar_dict(data.get("received_policy"), max_items=12, max_len=120),
        "received_policy_source": report_clip(data.get("received_policy_source"), max_len=80),
        "effective_policy": compact_scalar_dict(data.get("effective_policy"), max_items=12, max_len=120),
        "effective_policy_source": report_clip(data.get("effective_policy_source"), max_len=80),
        "effective_policy_source_chain": listify(
            data.get("effective_policy_source_chain"), max_items=6, max_len=80
        ),
        "policy_adjustments": compact_scalar_dict(data.get("policy_adjustments"), max_items=8, max_len=120),
        "policy_adjustment_summary": report_clip(data.get("policy_adjustment_summary"), max_len=220),
        "policy_adjustment_reasoning": report_clip(data.get("policy_adjustment_reasoning"), max_len=220),
        "effective_policy_deltas": [
            report_clip(
                f"{(row or {}).get('field')}: {(row or {}).get('from')} -> {(row or {}).get('to')}",
                max_len=120,
            )
            for row in list(data.get("effective_policy_deltas") or [])[:8]
            if isinstance(row, dict)
        ],
        "applied_policy": compact_scalar_dict(
            data.get("applied_policy") if isinstance(data.get("applied_policy"), dict) else policy_ref.get("applied_policy"),
            max_items=12,
            max_len=120,
        ),
        "policy_source": report_clip(data.get("policy_source") or policy_ref.get("policy_source"), max_len=80),
        "policy_validation_status": report_clip(
            data.get("policy_validation_status") or policy_ref.get("policy_validation_status"),
            max_len=80,
        ),
        "policy_fallback_used": (
            data.get("policy_fallback_used")
            if data.get("policy_fallback_used") is not None
            else policy_ref.get("policy_fallback_used")
        ),
        "policy_fallback_reason": report_clip(
            data.get("policy_fallback_reason") or policy_ref.get("policy_fallback_reason"),
            max_len=220,
        ),
        "policy_partial_normalized": (
            data.get("policy_partial_normalized")
            if data.get("policy_partial_normalized") is not None
            else policy_ref.get("policy_partial_normalized")
        ),
        "policy_default_filled_fields": listify(
            data.get("policy_default_filled_fields") or policy_ref.get("policy_default_filled_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_missing_fields": listify(
            data.get("policy_validation_missing_fields") or policy_ref.get("policy_validation_missing_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_invalid_fields": listify(
            data.get("policy_validation_invalid_fields") or policy_ref.get("policy_validation_invalid_fields"),
            max_items=12,
            max_len=80,
        ),
        "override_reason": report_clip(data.get("override_reason") or policy_ref.get("override_reason"), max_len=160),
        "applied_policy_source_chain": listify(
            data.get("applied_policy_source_chain") or policy_ref.get("applied_policy_source_chain"),
            max_items=6,
            max_len=80,
        ),
        "price_source": report_clip(data.get("price_source"), max_len=80),
        "feature_source": report_clip(data.get("feature_source"), max_len=80),
        "monitor_stop_policy_trace": compact_scalar_dict(data.get("monitor_stop_policy_trace"), max_items=8, max_len=120),
        "entry_candidate_cascade": compact_entry_candidate_cascade(data.get("entry_candidate_cascade")),
    }
    return {key: value for key, value in out.items() if value not in ("", None, [])}
