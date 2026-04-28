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
    if any(
        canonical_scanner.get(key) not in (None, "", [], {})
        for key in (
            "scanner_memory_bias_applied",
            "scanner_memory_bias_summary",
            "scanner_memory_bias",
            "candidate_memory_bias_adjustments",
            "commander_memory_application_trace",
            "scanner_memory_application_trace",
        )
    ):
        return dict(canonical_scanner)
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


def _walk_dicts(value: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def _walk(item: Any) -> None:
        if isinstance(item, dict):
            rows.append(item)
            for child in item.values():
                _walk(child)
            return
        if isinstance(item, list):
            for child in item:
                _walk(child)

    _walk(value)
    return rows


def _is_application_trace(value: Dict[str, Any], *, agent: str) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    if _text(value.get("agent"), max_len=24) and _text(value.get("agent"), max_len=24) != agent:
        return False
    if _text(value.get("schema_version"), max_len=64) == "commander_memory_application_trace.v1":
        return True
    agent_keys = {
        "scanner": ("applied", "selected_bias_adjustment", "symbol_adjustment_count"),
        "monitor": ("entry_applied", "hold_applied", "exit_applied", "applied"),
    }.get(agent, ())
    return any(key in value for key in agent_keys) and (
        "active_layers" in value
        or "enabled" in value
        or "not_applied_reason" in value
        or "bias_source" in value
    )


def _application_trace_score(value: Dict[str, Any], *, agent: str) -> tuple[int, int, int, int, int, int]:
    if agent == "monitor":
        applied = bool(
            value.get("applied")
            or value.get("entry_applied")
            or value.get("hold_applied")
            or value.get("exit_applied")
        )
        delta_count = (
            len(_list(value.get("entry_deltas")))
            + len(_list(value.get("hold_deltas")))
            + len(_list(value.get("exit_deltas")))
        )
    else:
        applied = bool(value.get("applied"))
        delta_count = len(_list(value.get("selected_bias_adjustments")))
    return (
        1 if applied else 0,
        1 if bool(value.get("enabled")) else 0,
        len(_list(value.get("active_layers"))),
        delta_count,
        1 if not _text(value.get("not_applied_reason"), max_len=80) else 0,
        1 if _text(value.get("bias_source"), max_len=80) else 0,
    )


def _select_application_trace(*values: Any, agent: str) -> Dict[str, Any]:
    traces: List[Dict[str, Any]] = []
    for value in values:
        for row in _walk_dicts(value):
            if _is_application_trace(row, agent=agent):
                traces.append(dict(row))
            for key in (
                "commander_memory_application_trace",
                "scanner_memory_application_trace",
                "monitor_memory_application_trace",
            ):
                nested = row.get(key)
                if isinstance(nested, dict) and _is_application_trace(nested, agent=agent):
                    traces.append(dict(nested))
    if not traces:
        return {}
    return max(traces, key=lambda row: _application_trace_score(row, agent=agent))


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
    scanner_trace = _select_application_trace(
        scanner_carrier.get("commander_memory_application_trace"),
        scanner_carrier.get("scanner_memory_application_trace"),
        canonical_scanner.get("commander_memory_application_trace"),
        canonical_scanner.get("scanner_memory_application_trace"),
        canonical_scanner,
        agent="scanner",
    )
    monitor_trace = _select_application_trace(
        monitor_carrier.get("commander_memory_application_trace"),
        monitor_carrier.get("monitor_memory_application_trace"),
        canonical_monitor.get("commander_memory_application_trace"),
        canonical_monitor.get("monitor_memory_application_trace"),
        canonical_monitor,
        agent="monitor",
    )
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
        or scanner_trace.get("selected_bias_adjustments")
        or scanner_carrier.get("selected_bias_adjustments")
        or scanner_carrier.get("candidate_memory_bias_adjustments")
    )
    scanner_selected_bias_adjustment = _safe_float(
        scanner_selected_adjustment_row.get("memory_bias_adjustment")
        if scanner_selected_adjustment_row
        else scanner_trace.get("selected_bias_adjustment")
        if scanner_trace
        else scanner_carrier.get("scanner_memory_bias_adjustment")
    )
    scanner_present = bool(
        scanner_summary
        or scanner_bias
        or scanner_trace
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
        monitor_trace.get("entry_deltas")
        or monitor_carrier.get("monitor_memory_bias_deltas")
        or canonical_monitor.get("monitor_memory_bias_deltas")
    )
    monitor_hold_deltas = _normalize_adjustments(
        monitor_trace.get("hold_deltas")
        or canonical_monitor.get("monitor_memory_bias_hold_deltas")
        or monitor_carrier.get("monitor_memory_bias_hold_deltas")
    )
    monitor_exit_deltas = _normalize_adjustments(
        monitor_trace.get("exit_deltas")
        or canonical_monitor.get("monitor_memory_bias_exit_deltas")
        or monitor_carrier.get("monitor_memory_bias_exit_deltas")
    )
    monitor_present = bool(
        monitor_summary
        or monitor_bias
        or monitor_trace
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
            "applied": bool(scanner_carrier.get("scanner_memory_bias_applied") or scanner_trace.get("applied")),
            "source": scanner_source,
            "enabled": bool(
                scanner_trace.get("enabled")
                if scanner_trace
                else scanner_summary.get("enabled")
                if scanner_summary
                else scanner_bias.get("enabled")
            ),
            "active_layers": [str(x or "") for x in _list((scanner_trace.get("active_layers") or scanner_bias.get("active_layers") or scanner_summary.get("active_layers")))[:4] if str(x or "").strip()],
            "source_weight_delta": dict(scanner_bias.get("source_weight_delta") or {}),
            "symbol_adjustment_count": int(
                len(_dict(scanner_bias.get("symbol_adjustments")))
                or int(scanner_summary.get("symbol_adjustment_count") or scanner_trace.get("symbol_adjustment_count") or 0)
            ),
            "selected_symbol": selected_symbol or _text(scanner_trace.get("selected_symbol"), max_len=24),
            "selected_bias_adjustment": scanner_selected_bias_adjustment,
            "selected_bias_adjustments": scanner_adjustments,
            "reason": [str(x or "") for x in _list((scanner_bias.get("reason") or scanner_summary.get("reason") or scanner_trace.get("reason")))[:4] if str(x or "").strip()],
            "bias_source": _first_non_empty_text(scanner_summary.get("bias_source"), scanner_bias.get("bias_source"), scanner_trace.get("bias_source"), max_len=48),
            "not_applied_reason": _text(scanner_trace.get("not_applied_reason"), max_len=80),
            "application_trace": scanner_trace,
        },
        "monitor_memory_bias": {
            "present": bool(monitor_present),
            "captured": bool(monitor_present),
            "applied": bool(
                monitor_trace.get("entry_applied")
                if monitor_trace
                else monitor_carrier.get("monitor_memory_bias_applied")
            ),
            "source": monitor_source,
            "enabled": bool(
                monitor_trace.get("enabled")
                if monitor_trace
                else monitor_summary.get("enabled")
                if monitor_summary
                else monitor_bias.get("enabled")
            ),
            "active_layers": [str(x or "") for x in _list((monitor_trace.get("active_layers") or monitor_bias.get("active_layers") or monitor_summary.get("active_layers")))[:4] if str(x or "").strip()],
            "entry_delta_keys": [str(x or "") for x in _list((monitor_trace.get("entry_delta_keys") or monitor_summary.get("entry_delta_keys") or _dict(monitor_bias.get("entry_policy_delta")).keys()))[:6] if str(x or "").strip()],
            "entry_policy_delta": dict(monitor_bias.get("entry_policy_delta") or {}),
            "applied_deltas": monitor_deltas,
            "hold_applied": bool(
                monitor_trace.get("hold_applied")
                if monitor_trace
                else canonical_monitor.get("monitor_memory_bias_hold_applied")
            ),
            "hold_deltas": monitor_hold_deltas,
            "exit_applied": bool(
                monitor_trace.get("exit_applied")
                if monitor_trace
                else canonical_monitor.get("monitor_memory_bias_exit_applied")
            ),
            "exit_deltas": monitor_exit_deltas,
            "risk_posture": _first_non_empty_text(monitor_summary.get("risk_posture"), monitor_bias.get("risk_posture"), monitor_trace.get("risk_posture"), max_len=24),
            "reason": [str(x or "") for x in _list((monitor_bias.get("reason") or monitor_summary.get("reason") or monitor_trace.get("reason")))[:4] if str(x or "").strip()],
            "bias_source": _first_non_empty_text(monitor_summary.get("bias_source"), monitor_bias.get("bias_source"), monitor_trace.get("bias_source"), max_len=48),
            "not_applied_reason": _text(monitor_trace.get("not_applied_reason"), max_len=80),
            "effective_policy_source": _first_non_empty_text(
                monitor_trace.get("effective_policy_source"),
                monitor_carrier.get("effective_policy_source"),
                canonical_monitor.get("effective_policy_source"),
                max_len=48,
            ),
            "application_trace": monitor_trace,
        },
    }


__all__ = ["build_trade_memory_application_surface"]
