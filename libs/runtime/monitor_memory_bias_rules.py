from __future__ import annotations

from typing import Any, Dict


def build_monitor_memory_bias_rules(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> Dict[str, Any]:
    entry_policy_delta: Dict[str, float] = {}
    hold_policy_delta: Dict[str, Any] = {}
    exit_policy_delta: Dict[str, Any] = {}
    risk_posture = "neutral"

    daily_best = [str(x or "").strip().lower() for x in list(daily_packet.get("best_playbooks") or []) if str(x or "").strip()]
    daily_worst = [str(x or "").strip().lower() for x in list(daily_packet.get("worst_playbooks") or []) if str(x or "").strip()]
    daily_failures = [str(x or "").strip().lower() for x in list(daily_packet.get("recent_failures") or []) if str(x or "").strip()]
    dominant_playbook = str(symbol_packet.get("dominant_playbook") or "").strip().lower()
    dominant_blocker = str(symbol_packet.get("dominant_monitor_blocker") or "").strip().lower()

    if "breakout" in daily_worst or any("breakout" in item for item in daily_failures):
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0015
        entry_policy_delta["max_extended_from_vwap_pct"] = entry_policy_delta.get("max_extended_from_vwap_pct", 0.0) - 0.01
        risk_posture = "defensive"
    if any("volume" in item for item in daily_failures):
        entry_policy_delta["volume_ratio_min"] = entry_policy_delta.get("volume_ratio_min", 0.0) + 0.03
        risk_posture = "defensive"
    if "pullback" in daily_best or "defensive" in daily_best:
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
        risk_posture = "defensive"

    if bool(commander_memory_policy.get("symbol_memory_override_enabled")):
        if dominant_playbook in {"pullback", "defensive"}:
            entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
            risk_posture = "defensive"
        if "below_vwap_reclaim_not_ready" in dominant_blocker:
            entry_policy_delta["max_extended_from_vwap_pct"] = entry_policy_delta.get("max_extended_from_vwap_pct", 0.0) - 0.005
            risk_posture = "defensive"
        if "volume" in dominant_blocker:
            entry_policy_delta["volume_ratio_min"] = entry_policy_delta.get("volume_ratio_min", 0.0) + 0.02
            risk_posture = "defensive"

    return {
        "entry_policy_delta": {str(k): float(v) for k, v in entry_policy_delta.items() if abs(float(v)) > 1e-9},
        "hold_policy_delta": hold_policy_delta,
        "exit_policy_delta": exit_policy_delta,
        "risk_posture": risk_posture,
    }
