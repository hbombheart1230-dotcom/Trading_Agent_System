from __future__ import annotations

from typing import Any, Dict

from libs.runtime.monitor_memory_bias_reasons import build_monitor_memory_bias_reasons
from libs.runtime.monitor_memory_bias_rules import build_monitor_memory_bias_rules
from libs.runtime.monitor_policy import MonitorEntryPolicy


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def build_monitor_memory_bias(
    *,
    commander_memory_policy: Dict[str, Any],
    memory_packets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    policy = dict(commander_memory_policy or {})
    if not bool(policy.get("monitor_bias_enabled")):
        return {
            "enabled": False,
            "bias_source": "commander_memory_bias.v1",
            "active_layers": [],
            "entry_policy_delta": {},
            "hold_policy_delta": {},
            "exit_policy_delta": {},
            "risk_posture": "neutral",
            "reason": ["monitor_bias_disabled"],
        }
    daily_packet = dict(memory_packets.get("daily_strategy_memory") or {})
    symbol_packet = dict(memory_packets.get("symbol_memory_packet") or {})
    rules = build_monitor_memory_bias_rules(
        commander_memory_policy=policy,
        daily_packet=daily_packet,
        symbol_packet=symbol_packet,
    )
    reasons = build_monitor_memory_bias_reasons(
        commander_memory_policy=policy,
        daily_packet=daily_packet,
        symbol_packet=symbol_packet,
    )
    return {
        "enabled": True,
        "bias_source": "commander_memory_bias.v1",
        "active_layers": [str(x or "") for x in list(policy.get("active_layers") or []) if str(x or "").strip()],
        "entry_policy_delta": dict(rules.get("entry_policy_delta") or {}),
        "hold_policy_delta": dict(rules.get("hold_policy_delta") or {}),
        "exit_policy_delta": dict(rules.get("exit_policy_delta") or {}),
        "risk_posture": str(rules.get("risk_posture") or "neutral"),
        "reason": reasons,
    }


def summarize_monitor_memory_bias(memory_bias: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(memory_bias or {})
    return {
        "enabled": bool(row.get("enabled")),
        "active_layers": [str(x or "") for x in list(row.get("active_layers") or []) if str(x or "").strip()][:4],
        "entry_delta_keys": [str(x or "") for x in list((row.get("entry_policy_delta") or {}).keys())[:6]],
        "hold_delta_keys": [str(x or "") for x in list((row.get("hold_policy_delta") or {}).keys())[:4]],
        "exit_delta_keys": [str(x or "") for x in list((row.get("exit_policy_delta") or {}).keys())[:4]],
        "risk_posture": str(row.get("risk_posture") or ""),
        "reason": [str(x or "") for x in list(row.get("reason") or [])[:4] if str(x or "").strip()],
        "bias_source": str(row.get("bias_source") or ""),
    }


def apply_monitor_memory_bias_to_entry_policy(
    *,
    entry_policy: Dict[str, Any],
    monitor_memory_bias: Dict[str, Any],
) -> Dict[str, Any]:
    baseline = MonitorEntryPolicy.from_mapping(entry_policy).to_dict()
    row = dict(monitor_memory_bias or {})
    deltas = []
    if not bool(row.get("enabled")):
        return {
            "policy": dict(baseline),
            "applied": False,
            "deltas": deltas,
        }
    out = dict(baseline)
    for field, raw_delta in dict(row.get("entry_policy_delta") or {}).items():
        delta = float(raw_delta or 0.0)
        before = baseline.get(field)
        if before is None or abs(delta) <= 1e-9:
            continue
        after = float(before)
        if field == "volume_ratio_min":
            after = _clamp(float(before) + delta, 0.4, 1.5)
        elif field == "max_extended_from_vwap_pct":
            after = _clamp(float(before) + delta, 0.03, 0.25)
        elif field == "breakout_buffer_pct":
            after = _clamp(float(before) + delta, 0.0, 0.03)
        else:
            continue
        if abs(after - float(before)) <= 1e-9:
            continue
        out[field] = round(after, 6)
        deltas.append(
            {
                "field": str(field),
                "delta": round(delta, 6),
                "from": float(before),
                "to": float(after),
            }
        )
    adjustments = [str(x or "").strip() for x in list(out.get("adjustments") or []) if str(x or "").strip()]
    if deltas:
        adjustments.append("commander_memory_bias")
    if adjustments:
        out["adjustments"] = tuple(dict.fromkeys(adjustments))
    out["policy_source"] = str(out.get("policy_source") or "monitor_entry_policy.v1")
    return {
        "policy": out,
        "applied": bool(deltas),
        "deltas": deltas,
    }


def apply_monitor_memory_bias_to_hold_controls(
    *,
    min_hold_sec: int,
    sell_cooldown_sec: int,
    confirm_ticks: int,
    monitor_memory_bias: Dict[str, Any],
) -> Dict[str, Any]:
    baseline = {
        "min_hold_sec": max(0, int(min_hold_sec or 0)),
        "sell_cooldown_sec": max(0, int(sell_cooldown_sec or 0)),
        "confirm_ticks": max(1, int(confirm_ticks or 1)),
    }
    row = dict(monitor_memory_bias or {})
    deltas = []
    if not bool(row.get("enabled")):
        return {"controls": dict(baseline), "applied": False, "deltas": deltas}
    out = dict(baseline)
    for field, raw_delta in dict(row.get("hold_policy_delta") or {}).items():
        delta = int(float(raw_delta or 0))
        before = baseline.get(field)
        if before is None or delta == 0:
            continue
        after = int(before)
        if field == "confirm_ticks":
            after = int(_clamp(int(before) + delta, 1, 5))
        elif field == "sell_cooldown_sec":
            after = int(_clamp(int(before) + delta, 0, 900))
        elif field == "min_hold_sec":
            after = int(_clamp(int(before) + delta, 0, 7200))
        else:
            continue
        if after == int(before):
            continue
        out[field] = after
        deltas.append({"field": str(field), "delta": delta, "from": int(before), "to": int(after)})
    return {"controls": out, "applied": bool(deltas), "deltas": deltas}


def apply_monitor_memory_bias_to_exit_policy(
    *,
    exit_policy: Dict[str, Any],
    monitor_memory_bias: Dict[str, Any],
) -> Dict[str, Any]:
    baseline = dict(exit_policy or {})
    row = dict(monitor_memory_bias or {})
    deltas = []
    if not bool(row.get("enabled")):
        return {"policy": dict(baseline), "applied": False, "deltas": deltas}
    out = dict(baseline)
    for field, raw_delta in dict(row.get("exit_policy_delta") or {}).items():
        delta = float(raw_delta or 0.0)
        before = baseline.get(field)
        if before in (None, "") or abs(delta) <= 1e-9:
            continue
        after = float(before)
        if field == "stop_loss_pct":
            after = _clamp(float(before) + delta, 0.003, 0.10)
        elif field == "take_profit_pct":
            after = _clamp(float(before) + delta, 0.0, 0.25)
        elif field == "trailing_stop_pct":
            after = _clamp(float(before) + delta, 0.0, 0.15)
        elif field == "peak_drawdown_exit_pct":
            after = _clamp(float(before) + delta, 0.0, 0.15)
        elif field == "vwap_breakdown_pct":
            after = _clamp(float(before) + delta, 0.0, 0.03)
        else:
            continue
        if abs(after - float(before)) <= 1e-9:
            continue
        out[field] = round(after, 6)
        deltas.append({"field": str(field), "delta": round(delta, 6), "from": float(before), "to": float(after)})
    return {"policy": out, "applied": bool(deltas), "deltas": deltas}
