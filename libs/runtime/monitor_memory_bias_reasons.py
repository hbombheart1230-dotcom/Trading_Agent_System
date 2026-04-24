from __future__ import annotations

from typing import Any, Dict, List


def _safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def build_monitor_memory_bias_reasons(
    *,
    commander_memory_policy: Dict[str, Any],
    daily_packet: Dict[str, Any],
    symbol_packet: Dict[str, Any],
) -> List[str]:
    reasons: List[str] = []
    policy_signals = dict(commander_memory_policy.get("policy_signals") or {})
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
    preferred_risk_posture = str(policy_signals.get("preferred_risk_posture") or "").strip()
    if preferred_risk_posture:
        reasons.append(f"commander_risk_posture:{preferred_risk_posture}")
    monitor_status = str(policy_signals.get("monitor_status") or "").strip()
    if monitor_status:
        reasons.append(f"commander_monitor_status:{monitor_status}")
    report_focus_targets = [str(x or "").strip() for x in list(policy_signals.get("report_focus_targets") or []) if str(x or "").strip()]
    if report_focus_targets:
        reasons.append(f"commander_focus:{report_focus_targets[0]}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and dominant_playbook:
        reasons.append(f"symbol_playbook:{dominant_playbook}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and dominant_blocker:
        reasons.append(f"symbol_blocker:{dominant_blocker}")
    if bool(commander_memory_policy.get("symbol_memory_override_enabled")):
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
    return (reasons or ["monitor_memory_bias_noop"])[:8]
