from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _load_json_artifact(path_value: Any) -> Dict[str, Any]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _first_non_empty_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _first_non_empty_text(*values: Any, max_len: int = 120) -> str:
    for value in values:
        text = _text(value, max_len=max_len)
        if text:
            return text
    return ""


def _normalize_adjustments(values: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in _list(values)[:8]:
        if not isinstance(row, dict):
            continue
        item = {
            "kind": _text(row.get("kind"), max_len=24),
            "source": _text(row.get("source"), max_len=32),
            "symbol": _text(row.get("symbol"), max_len=24),
            "field": _text(row.get("field"), max_len=48),
            "reason": _text(row.get("reason"), max_len=120),
            "delta": _safe_float(row.get("delta")),
            "from": _safe_float(row.get("from")),
            "to": _safe_float(row.get("to")),
        }
        rows.append({key: value for key, value in item.items() if value not in ("", None, [])})
    return rows


def _scanner_bias_carrier(canonical_scanner: Dict[str, Any]) -> Dict[str, Any]:
    return _first_non_empty_dict(
        canonical_scanner.get("candidate_selection_reason"),
        canonical_scanner.get("selection_reason_detail"),
        canonical_scanner,
    )


def _monitor_bias_carrier(canonical_monitor: Dict[str, Any]) -> Dict[str, Any]:
    return _first_non_empty_dict(
        canonical_monitor.get("threshold_snapshot"),
        canonical_monitor.get("policy_ref"),
        canonical_monitor,
    )


def _select_symbol_adjustment(rows: Any, symbol: str) -> Dict[str, Any]:
    symbol_text = _text(symbol, max_len=24)
    for row in _list(rows):
        if not isinstance(row, dict):
            continue
        if _text(row.get("symbol"), max_len=24) == symbol_text:
            return dict(row)
    return {}


def build_trade_memory_application_surface(story_input: Dict[str, Any] | None) -> Dict[str, Any]:
    source = dict(story_input) if isinstance(story_input, dict) else {}
    reasoning_trace = _dict(source.get("reasoning_trace"))
    commander_summary = _dict(reasoning_trace.get("commander_summary"))
    artifacts = _dict(source.get("artifacts"))

    canonical_scanner = _load_json_artifact(artifacts.get("canonical_scanner_json"))
    canonical_monitor = _load_json_artifact(artifacts.get("canonical_monitor_json"))
    scanner_carrier = _scanner_bias_carrier(canonical_scanner)
    monitor_carrier = _monitor_bias_carrier(canonical_monitor)
    selected_symbol = _first_non_empty_text(source.get("symbol"), max_len=24)

    scanner_summary = _first_non_empty_dict(
        source.get("scanner_memory_bias_summary"),
        commander_summary.get("scanner_memory_bias_summary"),
        scanner_carrier.get("scanner_memory_bias_summary"),
        canonical_scanner.get("scanner_memory_bias_summary"),
    )
    scanner_bias = _first_non_empty_dict(
        source.get("scanner_memory_bias"),
        commander_summary.get("scanner_memory_bias"),
        scanner_carrier.get("scanner_memory_bias"),
        canonical_scanner.get("scanner_memory_bias"),
    )
    scanner_selected_adjustment_row = _select_symbol_adjustment(
        scanner_carrier.get("candidate_memory_bias_adjustments"),
        selected_symbol,
    )
    scanner_adjustments = _normalize_adjustments(
        scanner_selected_adjustment_row.get("memory_bias_adjustments")
        or scanner_carrier.get("selected_bias_adjustments")
        or scanner_carrier.get("candidate_memory_bias_adjustments")
    )
    scanner_selected_bias_adjustment = _safe_float(
        scanner_selected_adjustment_row.get("memory_bias_adjustment")
        if scanner_selected_adjustment_row
        else scanner_carrier.get("scanner_memory_bias_adjustment")
    )
    scanner_present = bool(
        scanner_summary
        or scanner_bias
        or scanner_carrier.get("scanner_memory_bias_applied") is not None
        or scanner_adjustments
        or scanner_selected_bias_adjustment not in (None,)
    )
    scanner_source = _first_non_empty_text(
        "canonical_scanner" if canonical_scanner else "",
        "reasoning_trace" if commander_summary.get("scanner_memory_bias_summary") or commander_summary.get("scanner_memory_bias") else "",
        max_len=32,
    )

    monitor_summary = _first_non_empty_dict(
        source.get("monitor_memory_bias_summary"),
        commander_summary.get("monitor_memory_bias_summary"),
        monitor_carrier.get("monitor_memory_bias_summary"),
        canonical_monitor.get("monitor_memory_bias_summary"),
    )
    monitor_bias = _first_non_empty_dict(
        source.get("monitor_memory_bias"),
        commander_summary.get("monitor_memory_bias"),
        monitor_carrier.get("monitor_memory_bias"),
        canonical_monitor.get("monitor_memory_bias"),
    )
    monitor_deltas = _normalize_adjustments(
        monitor_carrier.get("monitor_memory_bias_deltas")
        or canonical_monitor.get("monitor_memory_bias_deltas")
    )
    monitor_hold_deltas = _normalize_adjustments(
        canonical_monitor.get("monitor_memory_bias_hold_deltas")
        or monitor_carrier.get("monitor_memory_bias_hold_deltas")
    )
    monitor_exit_deltas = _normalize_adjustments(
        canonical_monitor.get("monitor_memory_bias_exit_deltas")
        or monitor_carrier.get("monitor_memory_bias_exit_deltas")
    )
    monitor_present = bool(
        monitor_summary
        or monitor_bias
        or monitor_carrier.get("monitor_memory_bias_applied") is not None
        or monitor_deltas
        or canonical_monitor.get("monitor_memory_bias_hold_applied") is not None
        or canonical_monitor.get("monitor_memory_bias_exit_applied") is not None
        or monitor_hold_deltas
        or monitor_exit_deltas
    )
    monitor_source = _first_non_empty_text(
        "canonical_monitor" if canonical_monitor else "",
        "reasoning_trace" if commander_summary.get("monitor_memory_bias_summary") or commander_summary.get("monitor_memory_bias") else "",
        max_len=32,
    )

    return {
        "status": {
            "scanner_captured": bool(scanner_present),
            "monitor_captured": bool(monitor_present),
            "any_captured": bool(scanner_present or monitor_present),
        },
        "scanner_memory_bias": {
            "present": bool(scanner_present),
            "captured": bool(scanner_present),
            "applied": bool(scanner_carrier.get("scanner_memory_bias_applied")),
            "source": scanner_source,
            "enabled": bool(scanner_summary.get("enabled") if scanner_summary else scanner_bias.get("enabled")),
            "active_layers": [str(x or "") for x in _list((scanner_bias.get("active_layers") or scanner_summary.get("active_layers")))[:4] if str(x or "").strip()],
            "source_weight_delta": dict(scanner_bias.get("source_weight_delta") or {}),
            "symbol_adjustment_count": int(
                len(_dict(scanner_bias.get("symbol_adjustments")))
                or int(scanner_summary.get("symbol_adjustment_count") or 0)
            ),
            "selected_symbol": selected_symbol,
            "selected_bias_adjustment": scanner_selected_bias_adjustment,
            "selected_bias_adjustments": scanner_adjustments,
            "reason": [str(x or "") for x in _list((scanner_bias.get("reason") or scanner_summary.get("reason")))[:4] if str(x or "").strip()],
            "bias_source": _first_non_empty_text(scanner_summary.get("bias_source"), scanner_bias.get("bias_source"), max_len=48),
        },
        "monitor_memory_bias": {
            "present": bool(monitor_present),
            "captured": bool(monitor_present),
            "applied": bool(monitor_carrier.get("monitor_memory_bias_applied")),
            "source": monitor_source,
            "enabled": bool(monitor_summary.get("enabled") if monitor_summary else monitor_bias.get("enabled")),
            "active_layers": [str(x or "") for x in _list((monitor_bias.get("active_layers") or monitor_summary.get("active_layers")))[:4] if str(x or "").strip()],
            "entry_delta_keys": [str(x or "") for x in _list((monitor_summary.get("entry_delta_keys") or _dict(monitor_bias.get("entry_policy_delta")).keys()))[:6] if str(x or "").strip()],
            "entry_policy_delta": dict(monitor_bias.get("entry_policy_delta") or {}),
            "applied_deltas": monitor_deltas,
            "hold_applied": bool(canonical_monitor.get("monitor_memory_bias_hold_applied")),
            "hold_deltas": monitor_hold_deltas,
            "exit_applied": bool(canonical_monitor.get("monitor_memory_bias_exit_applied")),
            "exit_deltas": monitor_exit_deltas,
            "risk_posture": _first_non_empty_text(monitor_summary.get("risk_posture"), monitor_bias.get("risk_posture"), max_len=24),
            "reason": [str(x or "") for x in _list((monitor_bias.get("reason") or monitor_summary.get("reason")))[:4] if str(x or "").strip()],
            "bias_source": _first_non_empty_text(monitor_summary.get("bias_source"), monitor_bias.get("bias_source"), max_len=48),
            "effective_policy_source": _first_non_empty_text(
                monitor_carrier.get("effective_policy_source"),
                canonical_monitor.get("effective_policy_source"),
                max_len=48,
            ),
        },
    }


__all__ = ["build_trade_memory_application_surface"]
