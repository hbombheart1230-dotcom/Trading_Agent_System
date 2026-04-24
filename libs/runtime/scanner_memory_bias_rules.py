from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _symbol_signal_multiplier(symbol_packet: Dict[str, Any]) -> float:
    evidence_strength = str(symbol_packet.get("evidence_strength") or "").strip().lower()
    recency_days = _safe_float(symbol_packet.get("recency_days"))
    multiplier = 1.0
    if evidence_strength == "moderate":
        multiplier *= 0.75
    elif evidence_strength == "thin":
        multiplier *= 0.5
    elif evidence_strength == "none":
        return 0.0
    if recency_days is not None:
        if recency_days > 20:
            return 0.0
        if recency_days >= 10:
            multiplier *= 0.7
        elif recency_days >= 5:
            multiplier *= 0.85
    return round(multiplier, 6)


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
    policy_signals = dict(commander_memory_policy.get("policy_signals") or {})
    preferred_risk_posture = str(policy_signals.get("preferred_risk_posture") or "").strip().lower()
    system_health = str(policy_signals.get("system_health") or "").strip().upper()
    scanner_status = str(policy_signals.get("scanner_status") or "").strip().lower()
    monitor_only_ratio = float(policy_signals.get("monitor_only_ratio") or 0.0)
    report_focus_targets = {
        str(x or "").strip().lower() for x in list(policy_signals.get("report_focus_targets") or []) if str(x or "").strip()
    }
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

    if preferred_risk_posture == "defensive" or system_health == "RED" or monitor_only_ratio >= 0.7:
        source_weight_delta["top_value"] = round(float(source_weight_delta.get("top_value") or 0.0) + 0.005, 6)
        source_weight_delta["top_change_rate"] = round(float(source_weight_delta.get("top_change_rate") or 0.0) - 0.01, 6)
        feature_bias["prefer_shallow_pullback_candidates"] = 1.0
    if scanner_status in {"weak", "misaligned", "overfit"} or "scanner_fit" in report_focus_targets:
        source_weight_delta["top_change_rate"] = round(float(source_weight_delta.get("top_change_rate") or 0.0) - 0.01, 6)
        feature_bias["penalize_overextended"] = 1.0
    if "guard_blocks" in report_focus_targets:
        feature_bias["prefer_volume_confirmation"] = 1.0

    if bool(commander_memory_policy.get("symbol_memory_override_enabled")) and symbol:
        symbol_multiplier = _symbol_signal_multiplier(symbol_packet)
        symbol_delta = 0.0
        reasons = []
        if dominant_playbook in {"pullback", "defensive"}:
            symbol_delta += 0.015
            reasons.append(f"dominant_playbook:{dominant_playbook}")
        elif dominant_playbook == "breakout":
            symbol_delta -= 0.01
            reasons.append("dominant_playbook:breakout")
        if symbol_multiplier >= 0.6 and "below_vwap_reclaim_not_ready" in dominant_blocker:
            feature_bias["prefer_reclaim_candidates"] = 1.0
            reasons.append("dominant_blocker:reclaim")
        if symbol_multiplier >= 0.6 and "volume" in dominant_blocker:
            feature_bias["prefer_volume_confirmation"] = 1.0
            reasons.append("dominant_blocker:volume")
        symbol_delta = round(symbol_delta * symbol_multiplier, 6)
        if symbol_multiplier < 1.0:
            reasons.append(f"symbol_signal_multiplier:{symbol_multiplier:.2f}")
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
