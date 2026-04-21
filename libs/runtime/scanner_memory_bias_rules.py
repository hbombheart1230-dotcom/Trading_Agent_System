from __future__ import annotations

from typing import Any, Dict


def build_scanner_memory_bias_rules(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> Dict[str, Any]:
    source_weight_delta: Dict[str, float] = {}
    feature_bias: Dict[str, float] = {}
    symbol_adjustments: Dict[str, Dict[str, Any]] = {}

    daily_best = [str(x or "").strip().lower() for x in list(daily_packet.get("best_playbooks") or []) if str(x or "").strip()]
    daily_worst = [str(x or "").strip().lower() for x in list(daily_packet.get("worst_playbooks") or []) if str(x or "").strip()]
    daily_failures = [str(x or "").strip().lower() for x in list(daily_packet.get("recent_failures") or []) if str(x or "").strip()]
    symbol = str(symbol_packet.get("symbol") or "").strip()
    dominant_playbook = str(symbol_packet.get("dominant_playbook") or "").strip().lower()
    dominant_blocker = str(symbol_packet.get("dominant_monitor_blocker") or "").strip().lower()

    if "pullback" in daily_best or "defensive" in daily_best:
        source_weight_delta["top_value"] = 0.015
        feature_bias["prefer_shallow_pullback_candidates"] = 1.0
        feature_bias["prefer_reclaim_candidates"] = 1.0
    if "breakout" in daily_worst or any("breakout" in item for item in daily_failures):
        source_weight_delta["top_change_rate"] = -0.02
        feature_bias["penalize_overextended"] = 1.0
    if any("volume" in item for item in daily_failures):
        feature_bias["prefer_volume_confirmation"] = 1.0

    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and symbol:
        symbol_delta = 0.0
        reasons = []
        if dominant_playbook in {"pullback", "defensive"}:
            symbol_delta += 0.015
            reasons.append(f"dominant_playbook:{dominant_playbook}")
        elif dominant_playbook == "breakout":
            symbol_delta -= 0.01
            reasons.append("dominant_playbook:breakout")
        if "below_vwap_reclaim_not_ready" in dominant_blocker:
            feature_bias["prefer_reclaim_candidates"] = 1.0
            reasons.append("dominant_blocker:reclaim")
        if "volume" in dominant_blocker:
            feature_bias["prefer_volume_confirmation"] = 1.0
            reasons.append("dominant_blocker:volume")
        if abs(symbol_delta) > 1e-9:
            symbol_adjustments[symbol] = {
                "delta": round(symbol_delta, 6),
                "reason": ", ".join(reasons)[:160],
            }

    return {
        "source_weight_delta": source_weight_delta,
        "feature_bias": feature_bias,
        "symbol_adjustments": symbol_adjustments,
    }
