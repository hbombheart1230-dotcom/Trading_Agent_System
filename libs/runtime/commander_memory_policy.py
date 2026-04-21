from __future__ import annotations

from typing import Any, Dict, List


def build_commander_memory_policy(
    *,
    session_bias: str,
    memory_packets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    daily = dict(memory_packets.get("daily_strategy_memory") or {})
    weekly = dict(memory_packets.get("weekly_strategy_memory") or {})
    monthly = dict(memory_packets.get("monthly_strategy_memory") or {})
    symbol = dict(memory_packets.get("symbol_memory_packet") or {})

    priority_order: List[str] = ["daily", "weekly", "monthly", "symbol"]
    active_layers = [name for name, packet in [
        ("daily", daily),
        ("weekly", weekly),
        ("monthly", monthly),
        ("symbol", symbol),
    ] if bool(packet.get("active"))]
    symbol_override_enabled = bool(symbol.get("override_eligible")) and session_bias in {
        "active_selection",
        "position_management",
        "context_reuse",
    }
    if symbol_override_enabled:
        priority_order = ["daily", "symbol", "weekly", "monthly"]
        if "symbol" not in active_layers:
            active_layers.append("symbol")
    rationale: List[str] = []
    if daily.get("status") == "ok":
        rationale.append("daily_memory_available")
    if symbol_override_enabled:
        rationale.append("symbol_memory_override_eligible")
    if not rationale:
        rationale.append("surface_only_no_memory_override")
    return {
        "schema_version": "commander.memory_policy.v1",
        "owner": "commander",
        "application_mode": "surface_only",
        "active_layers": active_layers,
        "priority_order": priority_order,
        "symbol_memory_override_enabled": symbol_override_enabled,
        "symbol_memory_min_trade_count": 5,
        "symbol_memory_min_closed_trade_count": 3,
        "symbol_memory_max_age_days": 20,
        "scanner_bias_enabled": bool(active_layers),
        "scanner_bias_application_mode": "active" if active_layers else "planned",
        "monitor_bias_enabled": bool(active_layers),
        "monitor_bias_application_mode": "active" if active_layers else "planned",
        "layer_status": {
            "daily": str(daily.get("status") or ""),
            "weekly": str(weekly.get("status") or ""),
            "monthly": str(monthly.get("status") or ""),
            "symbol": str(symbol.get("status") or ""),
        },
        "rationale": rationale,
    }
