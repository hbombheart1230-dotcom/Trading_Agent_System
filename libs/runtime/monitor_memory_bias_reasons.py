from __future__ import annotations

from typing import Any, Dict, List


def build_monitor_memory_bias_reasons(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> List[str]:
    reasons: List[str] = []
    daily_best = [str(x or "").strip().lower() for x in list(daily_packet.get("best_playbooks") or []) if str(x or "").strip()]
    daily_worst = [str(x or "").strip().lower() for x in list(daily_packet.get("worst_playbooks") or []) if str(x or "").strip()]
    daily_failures = [str(x or "").strip().lower() for x in list(daily_packet.get("recent_failures") or []) if str(x or "").strip()]
    dominant_playbook = str(symbol_packet.get("dominant_playbook") or "").strip().lower()
    dominant_blocker = str(symbol_packet.get("dominant_monitor_blocker") or "").strip().lower()

    if "breakout" in daily_worst or any("breakout" in item for item in daily_failures):
        reasons.append("daily_breakout_quality_weak")
    if any("volume" in item for item in daily_failures):
        reasons.append("daily_volume_confirmation_weak")
    if "pullback" in daily_best or "defensive" in daily_best:
        reasons.append("daily_prefers_pullback_or_defensive")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and dominant_playbook:
        reasons.append(f"symbol_playbook:{dominant_playbook}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and dominant_blocker:
        reasons.append(f"symbol_blocker:{dominant_blocker}")
    return reasons or ["monitor_memory_bias_noop"]
