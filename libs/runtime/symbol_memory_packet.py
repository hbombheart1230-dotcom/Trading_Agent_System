from __future__ import annotations

from datetime import date
from typing import Any, Dict


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_day(value: Any) -> date | None:
    text = _text(value)
    if len(text) != 10:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _resolve_reference_day(state: Dict[str, Any]) -> str:
    for key in ("runtime_day", "session_day", "trade_day", "day"):
        text = _text(state.get(key))
        if _parse_day(text):
            return text
    return ""


def _pattern_signal_count(row: Dict[str, Any]) -> int:
    count = 0
    if _text(row.get("dominant_playbook")) and _text(row.get("dominant_playbook")).lower() != "unknown":
        count += 1
    if _text(row.get("dominant_monitor_blocker")) and _text(row.get("dominant_monitor_blocker")).lower() != "unknown":
        count += 1
    repeated_failure_pattern = row.get("repeated_failure_pattern") if isinstance(row.get("repeated_failure_pattern"), list) else []
    recent_success_pattern = row.get("recent_success_pattern") if isinstance(row.get("recent_success_pattern"), list) else []
    if repeated_failure_pattern:
        count += 1
    if recent_success_pattern:
        count += 1
    return count


def _resolve_override_gate_reason(
    *,
    symbol: str,
    trade_count: int,
    closed_trade_count: int,
    unknown_fields_ratio: float | None,
    pattern_signal_count: int,
    recency_days: int | None,
) -> str:
    if not symbol:
        return "no_symbol"
    if trade_count < 5 or closed_trade_count < 3:
        return "insufficient_trade_count"
    if recency_days is not None and recency_days > 20:
        return "stale_symbol_memory"
    if unknown_fields_ratio is not None and unknown_fields_ratio > 0.55:
        return "poor_data_quality"
    if pattern_signal_count <= 0:
        return "insufficient_pattern_quality"
    return ""


def _evidence_strength(
    *,
    trade_count: int,
    closed_trade_count: int,
    pattern_signal_count: int,
    unknown_fields_ratio: float | None,
) -> str:
    if trade_count >= 8 and closed_trade_count >= 5 and pattern_signal_count >= 2 and (unknown_fields_ratio is None or unknown_fields_ratio <= 0.2):
        return "strong"
    if trade_count >= 5 and closed_trade_count >= 3 and pattern_signal_count >= 1 and (unknown_fields_ratio is None or unknown_fields_ratio <= 0.55):
        return "moderate"
    if trade_count > 0:
        return "thin"
    return "none"


def _resolve_symbol_memory(state: Dict[str, Any]) -> tuple[str, Dict[str, Any], str]:
    candidates = [
        ("state.selected_symbol_memory", state.get("selected_symbol_memory")),
        ("state.commander_open_position_refresh_context.selected_symbol_memory", (state.get("commander_open_position_refresh_context") or {}).get("selected_symbol_memory")),
        ("state.commander_open_position_override.strategist_refresh_context.selected_symbol_memory", ((state.get("commander_open_position_override") or {}).get("strategist_refresh_context") or {}).get("selected_symbol_memory")),
        ("state.strategist_output.selected_symbol_memory", (state.get("strategist_output") or {}).get("selected_symbol_memory")),
    ]
    for source, value in candidates:
        if isinstance(value, dict) and value:
            symbol = str(
                value.get("symbol")
                or ((state.get("commander_open_position_refresh_context") or {}).get("selected_symbol"))
                or ((state.get("selected") or {}).get("symbol"))
                or ""
            ).strip()
            return symbol, dict(value), source
    symbol = str(
        ((state.get("commander_open_position_refresh_context") or {}).get("selected_symbol"))
        or ((state.get("selected") or {}).get("symbol"))
        or ((state.get("monitor") or {}).get("selected_symbol"))
        or ""
    ).strip()
    return symbol, {}, "unavailable"


def build_symbol_memory_packet(*, state: Dict[str, Any]) -> Dict[str, Any]:
    symbol, row, source = _resolve_symbol_memory(state)
    trade_count = _safe_int(row.get("trade_count"))
    closed_trade_count = _safe_int(row.get("closed_trade_count"))
    reference_day = _resolve_reference_day(state)
    last_trade_date = _text(row.get("last_trade_date"))
    reference_day_obj = _parse_day(reference_day)
    last_trade_day_obj = _parse_day(last_trade_date)
    recency_days = None
    if reference_day_obj and last_trade_day_obj:
        recency_days = max(0, (reference_day_obj - last_trade_day_obj).days)
    avg_pnl_pct = _safe_float(row.get("avg_pnl_pct"))
    avg_hold_duration_sec = _safe_float(row.get("avg_hold_duration_sec"))
    data_quality = dict(row.get("data_quality") or {})
    data_source = _text(data_quality.get("data_source"))
    unknown_fields_ratio = _safe_float(data_quality.get("unknown_fields_ratio"))
    pattern_signal_count = _pattern_signal_count(row)
    override_gate_reason = _resolve_override_gate_reason(
        symbol=symbol,
        trade_count=trade_count,
        closed_trade_count=closed_trade_count,
        unknown_fields_ratio=unknown_fields_ratio,
        pattern_signal_count=pattern_signal_count,
        recency_days=recency_days,
    )
    override_eligible = not bool(override_gate_reason)
    status = "ok" if row else ("empty" if symbol else "unavailable")
    return {
        "schema_version": "commander.memory_packet.v1",
        "layer": "symbol",
        "status": status,
        "source": source,
        "active": bool(symbol),
        "symbol": symbol,
        "trade_count": trade_count,
        "closed_trade_count": closed_trade_count,
        "win_rate": _safe_float(row.get("win_rate")),
        "avg_pnl_pct": avg_pnl_pct,
        "avg_hold_duration_sec": avg_hold_duration_sec,
        "last_trade_date": last_trade_date,
        "last_status": _text(row.get("last_status")),
        "reference_day": reference_day,
        "recency_days": recency_days,
        "dominant_playbook": str(row.get("dominant_playbook") or "").strip(),
        "dominant_monitor_blocker": str(row.get("dominant_monitor_blocker") or "").strip(),
        "repeated_failure_pattern": list(row.get("repeated_failure_pattern") or [])[:3],
        "recent_success_pattern": list(row.get("recent_success_pattern") or [])[:3],
        "pattern_signal_count": pattern_signal_count,
        "data_source": data_source,
        "unknown_fields_ratio": unknown_fields_ratio,
        "evidence_strength": _evidence_strength(
            trade_count=trade_count,
            closed_trade_count=closed_trade_count,
            pattern_signal_count=pattern_signal_count,
            unknown_fields_ratio=unknown_fields_ratio,
        ),
        "override_eligible": override_eligible,
        "override_gate_reason": override_gate_reason,
        "advisory_only": True,
    }
