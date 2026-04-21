from __future__ import annotations

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
    override_eligible = trade_count >= 5 and closed_trade_count >= 3
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
        "dominant_playbook": str(row.get("dominant_playbook") or "").strip(),
        "dominant_monitor_blocker": str(row.get("dominant_monitor_blocker") or "").strip(),
        "repeated_failure_pattern": list(row.get("repeated_failure_pattern") or [])[:3],
        "override_eligible": override_eligible,
        "override_gate_reason": "" if override_eligible else ("insufficient_trade_count" if symbol else "no_symbol"),
        "advisory_only": True,
    }
