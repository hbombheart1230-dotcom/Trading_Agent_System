from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list_text(values: Any, *, limit: int) -> List[str]:
    out: List[str] = []
    for item in list(values or []):
        text = _text(item)
        if not text:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _packet_quality(packet: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(packet or {})
    sample_quality = dict(row.get("sample_quality") or {})
    execution_risk = dict(row.get("execution_risk") or {})
    source_context = dict(row.get("source_context") or {})
    regime_stats = dict(row.get("regime_stats") or {})
    regime_observation_total = sum(
        _safe_int((payload or {}).get("observation_count"))
        for payload in regime_stats.values()
        if isinstance(payload, dict)
    )
    return {
        "status": str(row.get("status") or ""),
        "active": bool(row.get("active")),
        "sample_day_count": int(float(row.get("sample_day_count") or 0)),
        "trade_count": int(float(sample_quality.get("trade_count") or 0)),
        "usable": bool(sample_quality.get("usable")),
        "confidence": round(_safe_float(sample_quality.get("confidence")), 4),
        "max_age_days": int(float(sample_quality.get("max_age_days") or 0)),
        "route_source": _text(source_context.get("route_source") or execution_risk.get("route_source")),
        "system_health": _text(execution_risk.get("system_health")),
        "preferred_risk_posture": _text(execution_risk.get("preferred_risk_posture")),
        "monitor_only_ratio": round(_safe_float(execution_risk.get("avg_monitor_only_ratio")), 4),
        "full_cycle_ratio": round(_safe_float(execution_risk.get("avg_full_cycle_ratio")), 4),
        "report_focus_targets": _list_text(
            source_context.get("report_focus_targets") or execution_risk.get("report_focus_targets"),
            limit=4,
        ),
        "scanner_status": _text(source_context.get("scanner_status") or execution_risk.get("scanner_status")),
        "monitor_status": _text(source_context.get("monitor_status") or execution_risk.get("monitor_status")),
        "regime_observation_total": regime_observation_total,
        "avg_pnl_pct": round(_safe_float(row.get("avg_pnl_pct")), 4) if row.get("avg_pnl_pct") is not None else 0.0,
        "data_source": _text(row.get("data_source")),
        "unknown_fields_ratio": round(_safe_float(row.get("unknown_fields_ratio")), 4) if row.get("unknown_fields_ratio") is not None else 0.0,
        "pattern_signal_count": _safe_int(row.get("pattern_signal_count")),
        "evidence_strength": _text(row.get("evidence_strength")),
        "preferred_regimes": [
            name
            for name, payload in sorted(
                (
                    (str(name or "").strip(), payload)
                    for name, payload in regime_stats.items()
                    if isinstance(payload, dict) and str(name or "").strip()
                ),
                key=lambda item: (
                    -_safe_float((item[1] or {}).get("avg_return_pct")),
                    -_safe_int((item[1] or {}).get("observation_count")),
                    item[0],
                ),
            )[:2]
            if _safe_float((payload or {}).get("avg_return_pct")) >= 0.0
        ],
    }


def _layer_context_ready(packet: Dict[str, Any], quality: Dict[str, Any]) -> bool:
    if not bool(packet.get("active")):
        return False
    if _text(quality.get("route_source")):
        return True
    if _list_text(quality.get("report_focus_targets"), limit=1):
        return True
    if _safe_int(quality.get("regime_observation_total")) > 0:
        return True
    return False


def _build_policy_signals(layer_quality: Dict[str, Dict[str, Any]], active_layers: List[str]) -> Dict[str, Any]:
    for name in active_layers:
        quality = dict(layer_quality.get(name) or {})
        if not quality:
            continue
        return {
            "primary_layer": name,
            "preferred_risk_posture": _text(quality.get("preferred_risk_posture")) or "balanced",
            "route_source": _text(quality.get("route_source")),
            "report_focus_targets": _list_text(quality.get("report_focus_targets"), limit=4),
            "preferred_regimes": _list_text(quality.get("preferred_regimes"), limit=2),
            "system_health": _text(quality.get("system_health")),
            "monitor_only_ratio": round(_safe_float(quality.get("monitor_only_ratio")), 4),
            "full_cycle_ratio": round(_safe_float(quality.get("full_cycle_ratio")), 4),
            "scanner_status": _text(quality.get("scanner_status")),
            "monitor_status": _text(quality.get("monitor_status")),
        }
    return {
        "primary_layer": "",
        "preferred_risk_posture": "balanced",
        "route_source": "",
        "report_focus_targets": [],
        "preferred_regimes": [],
        "system_health": "",
        "monitor_only_ratio": 0.0,
        "full_cycle_ratio": 0.0,
        "scanner_status": "",
        "monitor_status": "",
    }


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
    layer_quality = {
        "daily": _packet_quality(daily),
        "weekly": _packet_quality(weekly),
        "monthly": _packet_quality(monthly),
        "symbol": _packet_quality(symbol),
    }
    active_layers: List[str] = []
    for name, packet in [("daily", daily), ("weekly", weekly), ("monthly", monthly)]:
        quality = dict(layer_quality.get(name) or {})
        if name == "daily":
            if bool(packet.get("active")):
                active_layers.append(name)
            continue
        if _layer_context_ready(packet, quality):
            active_layers.append(name)
    symbol_override_enabled = bool(symbol.get("override_eligible")) and session_bias in {
        "active_selection",
        "position_management",
        "context_reuse",
    }
    if symbol_override_enabled:
        priority_order = ["daily", "symbol", "weekly", "monthly"]
        if "symbol" not in active_layers:
            active_layers.append("symbol")
    active_layers = [name for name in priority_order if name in set(active_layers)]
    rationale: List[str] = []
    if daily.get("status") == "ok":
        rationale.append("daily_memory_available")
    if weekly.get("status") == "ok":
        if "weekly" in active_layers:
            rationale.append("weekly_memory_active")
            if _text(layer_quality["weekly"].get("route_source")):
                rationale.append(f"weekly_route_source:{_text(layer_quality['weekly'].get('route_source'))}")
            if _text(layer_quality["weekly"].get("preferred_risk_posture")):
                rationale.append(f"weekly_risk_posture:{_text(layer_quality['weekly'].get('preferred_risk_posture'))}")
        elif bool(weekly.get("active")):
            rationale.append("weekly_memory_support_context_missing")
        else:
            rationale.append("weekly_memory_sample_too_thin")
    if monthly.get("status") == "ok":
        if "monthly" in active_layers:
            rationale.append("monthly_memory_active")
            if _safe_int(layer_quality["monthly"].get("regime_observation_total")) > 0:
                rationale.append("monthly_regime_observation_available")
        elif bool(monthly.get("active")):
            rationale.append("monthly_memory_support_context_missing")
        else:
            rationale.append("monthly_memory_sample_too_thin")
    if symbol_override_enabled:
        rationale.append("symbol_memory_override_eligible")
        if _text(layer_quality["symbol"].get("data_source")):
            rationale.append(f"symbol_memory_data_source:{_text(layer_quality['symbol'].get('data_source'))}")
        if _text(layer_quality["symbol"].get("evidence_strength")):
            rationale.append(f"symbol_memory_evidence_strength:{_text(layer_quality['symbol'].get('evidence_strength'))}")
    elif str(symbol.get("status") or "") == "ok":
        rationale.append(f"symbol_memory_gate:{str(symbol.get('override_gate_reason') or 'inactive')}")
    if not rationale:
        rationale.append("surface_only_no_memory_override")
    policy_signals = _build_policy_signals(layer_quality, active_layers)
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
        "layer_quality": layer_quality,
        "policy_signals": policy_signals,
        "rationale": rationale,
    }
