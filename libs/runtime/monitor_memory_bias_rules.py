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
    policy_signals = dict(commander_memory_policy.get("policy_signals") or {})
    preferred_risk_posture = str(policy_signals.get("preferred_risk_posture") or "").strip().lower()
    system_health = str(policy_signals.get("system_health") or "").strip().upper()
    monitor_status = str(policy_signals.get("monitor_status") or "").strip().lower()
    monitor_only_ratio = float(policy_signals.get("monitor_only_ratio") or 0.0)
    report_focus_targets = {
        str(x or "").strip().lower() for x in list(policy_signals.get("report_focus_targets") or []) if str(x or "").strip()
    }
    dominant_playbook = str(symbol_packet.get("dominant_playbook") or "").strip().lower()
    dominant_blocker = str(symbol_packet.get("dominant_monitor_blocker") or "").strip().lower()

    if "breakout" in daily_worst or any("breakout" in item for item in daily_failures):
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0015
        entry_policy_delta["max_extended_from_vwap_pct"] = entry_policy_delta.get("max_extended_from_vwap_pct", 0.0) - 0.005
        exit_policy_delta["stop_loss_pct"] = exit_policy_delta.get("stop_loss_pct", 0.0) - 0.003
        exit_policy_delta["take_profit_pct"] = exit_policy_delta.get("take_profit_pct", 0.0) - 0.005
        exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - 0.004
        hold_policy_delta["confirm_ticks"] = int(hold_policy_delta.get("confirm_ticks", 0)) - 1
        risk_posture = "defensive"
    if any("volume" in item for item in daily_failures):
        entry_policy_delta["volume_ratio_min"] = entry_policy_delta.get("volume_ratio_min", 0.0) + 0.03
        exit_policy_delta["trailing_stop_pct"] = exit_policy_delta.get("trailing_stop_pct", 0.0) - 0.002
        exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - 0.003
        risk_posture = "defensive"
    if "pullback" in daily_best or "defensive" in daily_best:
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
        exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - 0.001
        risk_posture = "defensive"

    if preferred_risk_posture == "defensive" or system_health == "RED" or monitor_only_ratio >= 0.7:
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
        entry_policy_delta["max_extended_from_vwap_pct"] = entry_policy_delta.get("max_extended_from_vwap_pct", 0.0) - 0.0025
        exit_policy_delta["stop_loss_pct"] = exit_policy_delta.get("stop_loss_pct", 0.0) - 0.002
        exit_policy_delta["take_profit_pct"] = exit_policy_delta.get("take_profit_pct", 0.0) - 0.003
        exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - 0.003
        hold_policy_delta["confirm_ticks"] = int(hold_policy_delta.get("confirm_ticks", 0)) - 1
        risk_posture = "defensive"
    if monitor_status == "overtrading_risk":
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
        entry_policy_delta["volume_ratio_min"] = entry_policy_delta.get("volume_ratio_min", 0.0) + 0.01
        exit_policy_delta["take_profit_pct"] = exit_policy_delta.get("take_profit_pct", 0.0) - 0.002
        exit_policy_delta["trailing_stop_pct"] = exit_policy_delta.get("trailing_stop_pct", 0.0) - 0.002
        hold_policy_delta["confirm_ticks"] = int(hold_policy_delta.get("confirm_ticks", 0)) - 1
        risk_posture = "defensive"
    if "guard_blocks" in report_focus_targets or "exit_quality" in report_focus_targets:
        entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + 0.0005
        exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - 0.003
        exit_policy_delta["vwap_breakdown_pct"] = exit_policy_delta.get("vwap_breakdown_pct", 0.0) - 0.001
        risk_posture = "defensive"

    if bool(commander_memory_policy.get("symbol_memory_override_enabled")):
        symbol_multiplier = _symbol_signal_multiplier(symbol_packet)
        if dominant_playbook in {"pullback", "defensive"}:
            entry_policy_delta["breakout_buffer_pct"] = entry_policy_delta.get("breakout_buffer_pct", 0.0) + (0.0005 * symbol_multiplier)
            exit_policy_delta["peak_drawdown_exit_pct"] = exit_policy_delta.get("peak_drawdown_exit_pct", 0.0) - (0.001 * symbol_multiplier)
            risk_posture = "defensive"
        if "below_vwap_reclaim_not_ready" in dominant_blocker:
            entry_policy_delta["max_extended_from_vwap_pct"] = entry_policy_delta.get("max_extended_from_vwap_pct", 0.0) - (0.0025 * symbol_multiplier)
            exit_policy_delta["vwap_breakdown_pct"] = exit_policy_delta.get("vwap_breakdown_pct", 0.0) - (0.001 * symbol_multiplier)
            risk_posture = "defensive"
        if "volume" in dominant_blocker:
            entry_policy_delta["volume_ratio_min"] = entry_policy_delta.get("volume_ratio_min", 0.0) + (0.02 * symbol_multiplier)
            exit_policy_delta["trailing_stop_pct"] = exit_policy_delta.get("trailing_stop_pct", 0.0) - (0.001 * symbol_multiplier)
            risk_posture = "defensive"

    return {
        "entry_policy_delta": {str(k): float(v) for k, v in entry_policy_delta.items() if abs(float(v)) > 1e-9},
        "hold_policy_delta": {str(k): int(v) for k, v in hold_policy_delta.items() if int(v) != 0},
        "exit_policy_delta": {str(k): float(v) for k, v in exit_policy_delta.items() if abs(float(v)) > 1e-9},
        "risk_posture": risk_posture,
    }
