from __future__ import annotations

from typing import Any, Dict, List


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def build_scanner_memory_bias_reasons(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> List[str]:
    reasons: List[str] = []
    policy_signals = dict(commander_memory_policy.get("policy_signals") or {})
    if str(daily_packet.get("status") or "") == "ok":
        reasons.append("daily_strategy_memory_available")
        if list(daily_packet.get("best_playbooks") or []):
            reasons.append(f"daily_best:{','.join([str(x) for x in list(daily_packet.get('best_playbooks') or [])[:2]])}")
        if list(daily_packet.get("recent_failures") or []):
            reasons.append(f"daily_failure:{str(list(daily_packet.get('recent_failures') or [])[0])}")
    preferred_risk_posture = str(policy_signals.get("preferred_risk_posture") or "").strip()
    if preferred_risk_posture:
        reasons.append(f"commander_risk_posture:{preferred_risk_posture}")
    scanner_status = str(policy_signals.get("scanner_status") or "").strip()
    if scanner_status:
        reasons.append(f"commander_scanner_status:{scanner_status}")
    report_focus_targets = [str(x or "").strip() for x in list(policy_signals.get("report_focus_targets") or []) if str(x or "").strip()]
    if report_focus_targets:
        reasons.append(f"commander_focus:{report_focus_targets[0]}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and str(symbol_packet.get("symbol") or "").strip():
        reasons.append(f"symbol_override:{str(symbol_packet.get('symbol') or '').strip()}")
        if str(symbol_packet.get("dominant_playbook") or "").strip():
            reasons.append(f"symbol_playbook:{str(symbol_packet.get('dominant_playbook') or '').strip()}")
        evidence_strength = str(symbol_packet.get("evidence_strength") or "").strip()
        if evidence_strength:
            reasons.append(f"symbol_evidence_strength:{evidence_strength}")
        recency_days = _safe_int(symbol_packet.get("recency_days"))
        if recency_days is not None:
            reasons.append(f"symbol_recency_days:{recency_days}")
            if recency_days > 20:
                reasons.append("symbol_recency_blocked")
            elif recency_days >= 10:
                reasons.append("symbol_recency_damped")
    if not reasons:
        reasons.append("memory_bias_inactive")
    return reasons[:8]
