from __future__ import annotations

from typing import Any, Dict, List


TRACE_SCHEMA_VERSION = "commander_memory_application_trace.v1"


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, *, max_len: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _list_text(value: Any, *, limit: int = 8, max_len: int = 80) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in _list(value):
        text = _text(row, max_len=max_len)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _normalize_adjustments(rows: Any, *, limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _list(rows):
        if not isinstance(row, dict):
            continue
        item: Dict[str, Any] = {}
        for key in ("kind", "source", "symbol", "field", "reason"):
            text = _text(row.get(key), max_len=120)
            if text:
                item[key] = text
        for key in ("delta", "from", "to"):
            if row.get(key) not in (None, ""):
                item[key] = row.get(key)
        if item:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _delta_keys(mapping: Any, *, limit: int = 8) -> List[str]:
    return [
        _text(key, max_len=80)
        for key in list(_dict(mapping).keys())[:limit]
        if _text(key, max_len=80)
    ]


def _reason(memory_bias: Dict[str, Any], summary: Dict[str, Any]) -> List[str]:
    return _list_text(memory_bias.get("reason") or summary.get("reason"), limit=6, max_len=120)


def build_scanner_commander_memory_application_trace(
    *,
    scanner_memory_bias: Dict[str, Any],
    selected_symbol: str,
    candidate_sources: List[str] | None = None,
    selected_memory_bias_result: Dict[str, Any] | None = None,
    candidate_memory_bias_adjustments: List[Dict[str, Any]] | None = None,
    scanner_memory_bias_summary: Dict[str, Any] | None = None,
    scanner_memory_bias_applied: bool | None = None,
) -> Dict[str, Any]:
    bias = _dict(scanner_memory_bias)
    summary = _dict(scanner_memory_bias_summary)
    result = _dict(selected_memory_bias_result)
    selected_symbol_text = _text(selected_symbol, max_len=24)
    selected_row: Dict[str, Any] = {}
    for row in _list(candidate_memory_bias_adjustments):
        if not isinstance(row, dict):
            continue
        if _text(row.get("symbol"), max_len=24) == selected_symbol_text:
            selected_row = dict(row)
            break

    selected_adjustment = _safe_float(
        result.get("bias_adjustment")
        if result.get("bias_adjustment") not in (None, "")
        else selected_row.get("memory_bias_adjustment"),
        0.0,
    )
    source_delta = _safe_float(
        result.get("source_delta")
        if result.get("source_delta") not in (None, "")
        else selected_row.get("memory_bias_source_delta"),
        0.0,
    )
    symbol_delta = _safe_float(
        result.get("symbol_delta")
        if result.get("symbol_delta") not in (None, "")
        else selected_row.get("memory_bias_symbol_delta"),
        0.0,
    )
    selected_adjustments = _normalize_adjustments(
        result.get("adjustments") or selected_row.get("memory_bias_adjustments"),
        limit=8,
    )
    result_meaningful = bool(
        selected_adjustments
        or abs(selected_adjustment) > 1e-9
        or abs(source_delta) > 1e-9
        or abs(symbol_delta) > 1e-9
    )
    captured = bool(bias or summary or selected_row or result_meaningful)
    enabled = bool(bias.get("enabled") if bias else summary.get("enabled"))
    applied = (
        bool(scanner_memory_bias_applied)
        if scanner_memory_bias_applied is not None
        else bool(abs(selected_adjustment) > 1e-9 or selected_adjustments)
    )
    source_delta_keys = _delta_keys(bias.get("source_weight_delta") or summary.get("source_delta_keys"), limit=8)
    if not source_delta_keys:
        source_delta_keys = _list_text(summary.get("source_delta_keys"), limit=8, max_len=80)
    symbol_adjustments = _dict(bias.get("symbol_adjustments"))
    candidate_source_texts = _list_text(candidate_sources or [], limit=8, max_len=80)
    matching_sources = [source for source in candidate_source_texts if source in source_delta_keys]
    has_symbol_rule = bool(selected_symbol_text and selected_symbol_text in symbol_adjustments)

    not_applied_reason = ""
    if not applied:
        if not captured:
            not_applied_reason = "no_bias_payload"
        elif not enabled:
            not_applied_reason = "bias_disabled"
        elif not source_delta_keys and not symbol_adjustments:
            not_applied_reason = "no_configured_delta"
        elif not matching_sources and not has_symbol_rule:
            not_applied_reason = "no_matching_source_or_symbol_delta"
        else:
            not_applied_reason = "configured_delta_zero_or_clamped"

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "agent": "scanner",
        "captured": bool(captured),
        "enabled": bool(enabled),
        "applied": bool(applied),
        "not_applied_reason": not_applied_reason,
        "bias_source": _text(summary.get("bias_source") or bias.get("bias_source"), max_len=80),
        "active_layers": _list_text(bias.get("active_layers") or summary.get("active_layers"), limit=6, max_len=40),
        "selected_symbol": selected_symbol_text,
        "candidate_sources": candidate_source_texts,
        "source_delta_keys": source_delta_keys,
        "matching_source_delta_keys": matching_sources,
        "symbol_adjustment_count": int(len(symbol_adjustments) or int(summary.get("symbol_adjustment_count") or 0)),
        "selected_symbol_rule_present": bool(has_symbol_rule),
        "selected_bias_adjustment": float(selected_adjustment),
        "selected_source_delta": float(source_delta),
        "selected_symbol_delta": float(symbol_delta),
        "selected_bias_adjustments": selected_adjustments,
        "reason": _reason(bias, summary),
    }


def build_monitor_commander_memory_application_trace(
    *,
    monitor_memory_bias: Dict[str, Any],
    entry_result: Dict[str, Any] | None = None,
    hold_result: Dict[str, Any] | None = None,
    exit_result: Dict[str, Any] | None = None,
    monitor_memory_bias_summary: Dict[str, Any] | None = None,
    effective_policy_source: str = "",
    effective_policy_source_chain: List[str] | None = None,
) -> Dict[str, Any]:
    bias = _dict(monitor_memory_bias)
    summary = _dict(monitor_memory_bias_summary)
    entry = _dict(entry_result)
    hold = _dict(hold_result)
    exit_policy = _dict(exit_result)
    entry_deltas = _normalize_adjustments(entry.get("deltas"), limit=8)
    hold_deltas = _normalize_adjustments(hold.get("deltas"), limit=8)
    exit_deltas = _normalize_adjustments(exit_policy.get("deltas"), limit=8)
    entry_applied = bool(entry.get("applied") or entry_deltas)
    hold_applied = bool(hold.get("applied") or hold_deltas)
    exit_applied = bool(exit_policy.get("applied") or exit_deltas)
    applied = bool(entry_applied or hold_applied or exit_applied)
    captured = bool(
        bias
        or summary
        or entry_applied
        or hold_applied
        or exit_applied
        or entry_deltas
        or hold_deltas
        or exit_deltas
    )
    enabled = bool(bias.get("enabled") if bias else summary.get("enabled"))
    entry_delta_keys = _delta_keys(bias.get("entry_policy_delta"), limit=8) or _list_text(
        summary.get("entry_delta_keys"), limit=8, max_len=80
    )
    hold_delta_keys = _delta_keys(bias.get("hold_policy_delta"), limit=8) or _list_text(
        summary.get("hold_delta_keys"), limit=8, max_len=80
    )
    exit_delta_keys = _delta_keys(bias.get("exit_policy_delta"), limit=8) or _list_text(
        summary.get("exit_delta_keys"), limit=8, max_len=80
    )

    not_applied_reason = ""
    if not applied:
        if not captured:
            not_applied_reason = "no_bias_payload"
        elif not enabled:
            not_applied_reason = "bias_disabled"
        elif not entry_delta_keys and not hold_delta_keys and not exit_delta_keys:
            not_applied_reason = "no_configured_delta"
        else:
            not_applied_reason = "configured_delta_zero_or_not_applicable"

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "agent": "monitor",
        "captured": bool(captured),
        "enabled": bool(enabled),
        "applied": bool(applied),
        "entry_applied": bool(entry_applied),
        "hold_applied": bool(hold_applied),
        "exit_applied": bool(exit_applied),
        "not_applied_reason": not_applied_reason,
        "bias_source": _text(summary.get("bias_source") or bias.get("bias_source"), max_len=80),
        "active_layers": _list_text(bias.get("active_layers") or summary.get("active_layers"), limit=6, max_len=40),
        "risk_posture": _text(summary.get("risk_posture") or bias.get("risk_posture"), max_len=40),
        "entry_delta_keys": entry_delta_keys,
        "hold_delta_keys": hold_delta_keys,
        "exit_delta_keys": exit_delta_keys,
        "entry_deltas": entry_deltas,
        "hold_deltas": hold_deltas,
        "exit_deltas": exit_deltas,
        "effective_policy_source": _text(effective_policy_source, max_len=80),
        "effective_policy_source_chain": _list_text(effective_policy_source_chain or [], limit=8, max_len=80),
        "reason": _reason(bias, summary),
    }


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "build_monitor_commander_memory_application_trace",
    "build_scanner_commander_memory_application_trace",
]
