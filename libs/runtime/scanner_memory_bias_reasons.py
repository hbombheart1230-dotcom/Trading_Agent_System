from __future__ import annotations

from typing import Any, Dict, List


def build_scanner_memory_bias_reasons(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> List[str]:
    reasons: List[str] = []
    if str(daily_packet.get("status") or "") == "ok":
        reasons.append("daily_strategy_memory_available")
        if list(daily_packet.get("best_playbooks") or []):
            reasons.append(f"daily_best:{','.join([str(x) for x in list(daily_packet.get('best_playbooks') or [])[:2]])}")
        if list(daily_packet.get("recent_failures") or []):
            reasons.append(f"daily_failure:{str(list(daily_packet.get('recent_failures') or [])[0])}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and str(symbol_packet.get("symbol") or "").strip():
        reasons.append(f"symbol_override:{str(symbol_packet.get('symbol') or '').strip()}")
        if str(symbol_packet.get("dominant_playbook") or "").strip():
            reasons.append(f"symbol_playbook:{str(symbol_packet.get('dominant_playbook') or '').strip()}")
    if not reasons:
        reasons.append("memory_bias_inactive")
    return reasons[:6]
