from __future__ import annotations

from typing import Any, Dict, List

from libs.reporting.trade_execution_outcome_text import build_execution_outcome_human_payload
from libs.reporting.trade_report_common import (
    clip_text as clip,
    format_ratio_pct,
    list_text as _list_text,
    safe_float,
)


def normalize_stop_thresholds(thresholds: Dict[str, Any]) -> Dict[str, Any]:
    data = thresholds if isinstance(thresholds, dict) else {}
    nested = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    return nested or data


def resolve_strategist_adaptive_exit(monitor: Dict[str, Any]) -> Dict[str, Any]:
    data = monitor if isinstance(monitor, dict) else {}
    for candidate in (
        ((data.get("policy_ref") or {}).get("exit_plan") or {}).get("adaptive_exit"),
        (((data.get("decision_trace") or {}).get("policy_ref") or {}).get("exit_plan") or {}).get("adaptive_exit"),
        (((data.get("timing_assessment") or {}).get("entry_plan") or {}).get("adaptive_exit")),
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def resolve_adaptive_stop_loss_pct(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Any:
    thresholds = normalize_stop_thresholds(thresholds)
    adaptive_exit = monitor.get("adaptive_exit") if isinstance(monitor.get("adaptive_exit"), dict) else {}
    if adaptive_exit.get("stop_loss_pct") not in (None, ""):
        return adaptive_exit.get("stop_loss_pct")
    if thresholds.get("adaptive_stop_loss_pct") not in (None, ""):
        return thresholds.get("adaptive_stop_loss_pct")
    threshold_snapshot = monitor.get("threshold_snapshot") if isinstance(monitor.get("threshold_snapshot"), dict) else {}
    if threshold_snapshot.get("adaptive_stop_loss_pct") not in (None, ""):
        return threshold_snapshot.get("adaptive_stop_loss_pct")
    return None


def build_monitor_stop_policy_trace(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = normalize_stop_thresholds(thresholds)
    strategist_adaptive_exit = resolve_strategist_adaptive_exit(monitor)
    adaptive_stop_loss_pct = resolve_adaptive_stop_loss_pct(monitor, thresholds)
    hard_stop_pct = (
        thresholds.get("hard_stop_pct")
        if thresholds.get("hard_stop_pct") not in (None, "")
        else monitor.get("hard_stop_pct")
    )
    effective_stop_loss_pct = (
        thresholds.get("effective_stop_loss_pct")
        if thresholds.get("effective_stop_loss_pct") not in (None, "")
        else adaptive_stop_loss_pct
        if adaptive_stop_loss_pct not in (None, "")
        else hard_stop_pct
    )
    return {
        "hard_stop_pct": hard_stop_pct,
        "adaptive_stop_loss_pct": adaptive_stop_loss_pct,
        "effective_stop_loss_pct": effective_stop_loss_pct,
        "trailing_stop_pct": thresholds.get("trailing_stop_pct"),
        "take_profit_pct": thresholds.get("take_profit_pct"),
        "partial_take_profit_pct": thresholds.get("partial_take_profit_pct"),
        "partial_take_profit_fraction": thresholds.get("partial_take_profit_fraction"),
        "profit_ladder_levels_pct": thresholds.get("profit_ladder_levels_pct"),
        "profit_ladder_fraction": thresholds.get("profit_ladder_fraction"),
        "risk_reward_take_profit_r": thresholds.get("risk_reward_take_profit_r"),
        "risk_reward_take_profit_rungs": thresholds.get("risk_reward_take_profit_rungs"),
        "risk_reward_take_profit_fraction": thresholds.get("risk_reward_take_profit_fraction"),
        "risk_reward_take_profit_min_pct": thresholds.get("risk_reward_take_profit_min_pct"),
        "vwap_extension_take_profit_pct": thresholds.get("vwap_extension_take_profit_pct"),
        "vwap_extension_take_profit_min_pct": thresholds.get("vwap_extension_take_profit_min_pct"),
        "resistance_take_profit_near_pct": thresholds.get("resistance_take_profit_near_pct"),
        "resistance_take_profit_min_pct": thresholds.get("resistance_take_profit_min_pct"),
        "profit_time_stop_sec": thresholds.get("profit_time_stop_sec"),
        "profit_time_stop_min_pct": thresholds.get("profit_time_stop_min_pct"),
        "profit_time_stop_peak_giveback_pct": thresholds.get("profit_time_stop_peak_giveback_pct"),
        "volume_exhaustion_take_profit_min_pct": thresholds.get("volume_exhaustion_take_profit_min_pct"),
        "volume_exhaustion_volume_ratio_max": thresholds.get("volume_exhaustion_volume_ratio_max"),
        "volume_exhaustion_strength_max": thresholds.get("volume_exhaustion_strength_max"),
        "opening_gap_profit_take_min_pct": thresholds.get("opening_gap_profit_take_min_pct"),
        "opening_gap_profit_take_window_sec": thresholds.get("opening_gap_profit_take_window_sec"),
        "opening_gap_profit_take_fraction": thresholds.get("opening_gap_profit_take_fraction"),
        "cost_aware_profit_floor_enabled": thresholds.get("cost_aware_profit_floor_enabled"),
        "round_trip_cost_floor_pct": thresholds.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": thresholds.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": thresholds.get("cost_aware_profit_floor_pct"),
        "strategist_baseline_stop_loss_pct": strategist_adaptive_exit.get("stop_loss_pct"),
        "strategist_baseline_take_profit_pct": strategist_adaptive_exit.get("take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": strategist_adaptive_exit.get("trailing_stop_pct"),
    }


def build_monitor_blocker_trace(monitor: Dict[str, Any]) -> Dict[str, Any]:
    data = monitor if isinstance(monitor, dict) else {}
    entry_metrics = data.get("entry_metrics") if isinstance(data.get("entry_metrics"), dict) else {}
    entry_thresholds = data.get("entry_thresholds") if isinstance(data.get("entry_thresholds"), dict) else {}
    timing_assessment = data.get("timing_assessment") if isinstance(data.get("timing_assessment"), dict) else {}
    policy_ref = data.get("policy_ref") if isinstance(data.get("policy_ref"), dict) else {}
    threshold_shortfalls: List[str] = []
    if entry_metrics.get("volume_ratio") not in (None, "") and entry_thresholds.get("volume_ratio_min") not in (None, ""):
        volume_ratio = safe_float(entry_metrics.get("volume_ratio"), 0.0)
        volume_ratio_min = safe_float(entry_thresholds.get("volume_ratio_min"), 0.0)
        if volume_ratio < volume_ratio_min:
            threshold_shortfalls.append(f"volume ratio {volume_ratio:.2f} below min {volume_ratio_min:.2f}")
    if entry_metrics.get("extended_from_vwap_pct") not in (None, "") and entry_thresholds.get("max_extended_from_vwap_pct") not in (None, ""):
        extended = safe_float(entry_metrics.get("extended_from_vwap_pct"), 0.0)
        extended_max = safe_float(entry_thresholds.get("max_extended_from_vwap_pct"), 0.0)
        if extended > extended_max:
            threshold_shortfalls.append(
                f"VWAP extension {format_ratio_pct(extended)}% above max {format_ratio_pct(extended_max)}%"
            )
    if entry_metrics.get("pullback_depth_pct") not in (None, "") and entry_thresholds.get("pullback_min_pct") not in (None, ""):
        pullback_depth = safe_float(entry_metrics.get("pullback_depth_pct"), 0.0)
        pullback_min = safe_float(entry_thresholds.get("pullback_min_pct"), 0.0)
        if pullback_depth < pullback_min:
            threshold_shortfalls.append(
                f"pullback depth {format_ratio_pct(pullback_depth)}% below min {format_ratio_pct(pullback_min)}%"
            )
    return {
        "entry_check_summary": clip(data.get("entry_check_summary"), max_len=260),
        "entry_blockers": _list_text(data.get("entry_blockers"), limit=8, max_len=120),
        "threshold_shortfalls": threshold_shortfalls[:4],
        "timing_assessment": dict(timing_assessment or {}),
        "policy_ref": dict(policy_ref or {}),
        "entry_condition_path": clip(data.get("entry_condition_path"), max_len=80),
        "entry_condition_paths_passed": _list_text(data.get("entry_condition_paths_passed"), limit=4, max_len=80),
        "condition_scores": dict(data.get("condition_scores") or {}),
        "grouped_logic_trace": dict(data.get("grouped_logic_trace") or {}),
    }


def build_execution_outcome_human(
    execution: Dict[str, Any],
    executor: Dict[str, Any],
    *,
    story_type: str,
    mode_label: str,
) -> Dict[str, Any]:
    return build_execution_outcome_human_payload(
        execution,
        executor,
        story_type=story_type,
        mode_label=mode_label,
    )
