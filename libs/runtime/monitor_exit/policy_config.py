from __future__ import annotations

import os
from typing import Any, Dict

from libs.runtime.broker_cost_profile import apply_broker_cost_profile_to_exit_policy
from libs.runtime.exit_policy import apply_env_stop_take_fallbacks


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


EXIT_POLICY_ALIAS_MAP = {
    "hard_stop_pct": "hard_stop_pct",
    "stop_loss_pct": "stop_loss_pct",
    "take_profit_pct": "take_profit_pct",
    "partial_take_profit_pct": "partial_take_profit_pct",
    "partial_take_profit_fraction": "partial_take_profit_fraction",
    "profit_ladder_levels_pct": "profit_ladder_levels_pct",
    "profit_ladder_fraction": "profit_ladder_fraction",
    "risk_reward_take_profit_r": "risk_reward_take_profit_r",
    "risk_reward_take_profit_rungs": "risk_reward_take_profit_rungs",
    "risk_reward_take_profit_fraction": "risk_reward_take_profit_fraction",
    "risk_reward_take_profit_min_pct": "risk_reward_take_profit_min_pct",
    "vwap_extension_take_profit_pct": "vwap_extension_take_profit_pct",
    "vwap_extension_take_profit_min_pct": "vwap_extension_take_profit_min_pct",
    "resistance_take_profit_near_pct": "resistance_take_profit_near_pct",
    "resistance_take_profit_min_pct": "resistance_take_profit_min_pct",
    "profit_time_stop_sec": "profit_time_stop_sec",
    "profit_time_stop_min_pct": "profit_time_stop_min_pct",
    "profit_time_stop_peak_giveback_pct": "profit_time_stop_peak_giveback_pct",
    "volume_exhaustion_take_profit_min_pct": "volume_exhaustion_take_profit_min_pct",
    "volume_exhaustion_volume_ratio_max": "volume_exhaustion_volume_ratio_max",
    "volume_exhaustion_strength_max": "volume_exhaustion_strength_max",
    "opening_gap_profit_take_min_pct": "opening_gap_profit_take_min_pct",
    "opening_gap_profit_take_window_sec": "opening_gap_profit_take_window_sec",
    "opening_gap_profit_take_fraction": "opening_gap_profit_take_fraction",
    "cost_aware_profit_floor_enabled": "cost_aware_profit_floor_enabled",
    "round_trip_cost_floor_pct": "round_trip_cost_floor_pct",
    "min_net_profit_buffer_pct": "min_net_profit_buffer_pct",
    "cost_aware_profit_floor_pct": "cost_aware_profit_floor_pct",
    "cost_aware_profit_floor_use_expected_exit": "cost_aware_profit_floor_use_expected_exit",
    "sell_slippage_buffer_pct": "sell_slippage_buffer_pct",
    "min_expected_net_profit_pct": "min_expected_net_profit_pct",
    "max_hold_sec": "max_hold_sec",
    "time_stop_sec": "time_stop_sec",
    "trailing_stop_pct": "trailing_stop_pct",
    "vol_expansion_ratio": "vol_expansion_ratio",
    "news_shock_threshold": "news_shock_threshold",
    "peak_drawdown_exit_pct": "peak_drawdown_exit_pct",
    "profit_protection_activation_pct": "profit_protection_activation_pct",
    "peak_drawdown_mode": "peak_drawdown_mode",
    "confirm_required_for_peak_drawdown": "confirm_required_for_peak_drawdown",
    "vwap_breakdown_pct": "vwap_breakdown_pct",
    "vwap_break_requires_profit": "vwap_break_requires_profit",
    "vwap_breakdown_confirmation_required": "vwap_breakdown_confirmation_required",
    "vwap_breakdown_confirm_bars": "vwap_breakdown_confirm_bars",
    "vwap_breakdown_volume_ratio_min": "vwap_breakdown_volume_ratio_min",
    "vwap_breakdown_low_break_pct": "vwap_breakdown_low_break_pct",
    "intraday_low_break_pct": "intraday_low_break_pct",
    "trend_strength_floor": "trend_strength_floor",
    "use_eod_flat": "use_eod_flat",
    "eod_flat_cutoff_min": "eod_flat_cutoff_min",
    "emergency_halt": "emergency_halt",
}


EXIT_PROFIT_DEFAULTS = {
    "cost_aware_profit_floor_enabled": True,
    "round_trip_cost_floor_pct": 0.009,
    "min_net_profit_buffer_pct": 0.003,
    "cost_aware_profit_floor_pct": 0.012,
    "partial_take_profit_pct": 0.012,
    "partial_take_profit_fraction": 0.50,
    "profit_ladder_levels_pct": [0.012, 0.016, 0.020],
    "profit_ladder_fraction": 0.34,
    "risk_reward_take_profit_r": 1.0,
    "risk_reward_take_profit_rungs": [1.0, 1.5, 2.0],
    "risk_reward_take_profit_fraction": 0.34,
    "risk_reward_take_profit_min_pct": 0.012,
    "vwap_extension_take_profit_pct": 0.030,
    "vwap_extension_take_profit_min_pct": 0.012,
    "resistance_take_profit_near_pct": 0.003,
    "resistance_take_profit_min_pct": 0.012,
    "profit_time_stop_sec": 900,
    "profit_time_stop_min_pct": 0.012,
    "profit_time_stop_peak_giveback_pct": 0.003,
    "volume_exhaustion_take_profit_min_pct": 0.012,
    "volume_exhaustion_volume_ratio_max": 0.80,
    "volume_exhaustion_strength_max": 0.75,
    "opening_gap_profit_take_min_pct": 0.012,
    "opening_gap_profit_take_window_sec": 1200,
    "opening_gap_profit_take_fraction": 1.0,
}


def _nested_eod_flat(policy: Dict[str, Any], section: str) -> Dict[str, Any]:
    monitor = policy.get("monitor") if isinstance(policy.get("monitor"), dict) else {}
    exit_cfg = monitor.get("exit") if isinstance(monitor.get("exit"), dict) else {}
    eod_flat = exit_cfg.get("eod_flat") if isinstance(exit_cfg.get("eod_flat"), dict) else {}
    return eod_flat if isinstance(eod_flat, dict) else {}


def resolve_exit_policy_config(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_exit_cfg = (
        (((applied_policy.get("monitor") or {}).get("exit")) or {})
        if isinstance(((applied_policy.get("monitor") or {}).get("exit")), dict)
        else {}
    )
    if isinstance(applied_policy.get("exit_policy"), dict):
        out.update(dict(applied_policy.get("exit_policy") or {}))
    applied_exit_policy_overrides = (
        dict(applied_exit_cfg.get("policy_overrides") or {})
        if isinstance(applied_exit_cfg.get("policy_overrides"), dict)
        else {}
    )
    if applied_exit_policy_overrides:
        out.update(applied_exit_policy_overrides)

    for src_key, dst_key in EXIT_POLICY_ALIAS_MAP.items():
        if out.get(dst_key) in (None, "") and policy.get(src_key) not in (None, ""):
            out[dst_key] = policy.get(src_key)

    env_values = {
        "max_hold_sec": str(os.getenv("EXIT_POLICY_MAX_HOLD_SEC", "") or "").strip(),
        "trailing_stop_pct": str(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "") or "").strip(),
        "vol_expansion_ratio": str(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "") or "").strip(),
        "news_shock_threshold": str(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "") or "").strip(),
        "peak_drawdown_exit_pct": str(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_EXIT_PCT", "") or "").strip(),
        "profit_protection_activation_pct": str(os.getenv("EXIT_POLICY_PROFIT_PROTECTION_ACTIVATION_PCT", "") or "").strip(),
        "peak_drawdown_mode": str(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_MODE", "") or "").strip(),
        "vwap_breakdown_pct": str(os.getenv("EXIT_POLICY_VWAP_BREAKDOWN_PCT", "") or "").strip(),
        "intraday_low_break_pct": str(os.getenv("EXIT_POLICY_INTRADAY_LOW_BREAK_PCT", "") or "").strip(),
        "trend_strength_floor": str(os.getenv("EXIT_POLICY_TREND_STRENGTH_FLOOR", "") or "").strip(),
    }
    eod_flat_enabled = _nested_eod_flat(applied_policy, "applied").get("enabled")
    if eod_flat_enabled is None:
        eod_flat_enabled = _nested_eod_flat(policy, "policy").get("enabled")
    eod_flat_raw = str(os.getenv("EXIT_POLICY_USE_EOD_FLAT", "") or "").strip()
    eod_cutoff_value = _nested_eod_flat(applied_policy, "applied").get("cutoff_min")
    if eod_cutoff_value is None:
        eod_cutoff_value = _nested_eod_flat(policy, "policy").get("cutoff_min")
    emergency_raw = str(os.getenv("EXIT_POLICY_EMERGENCY_HALT", "") or "").strip()

    out = apply_env_stop_take_fallbacks(out)
    if env_values["max_hold_sec"]:
        base = to_float(out.get("max_hold_sec"))
        x = to_float(env_values["max_hold_sec"])
        out["max_hold_sec"] = int(x if x > 0.0 else base)
    for key in (
        "trailing_stop_pct",
        "vol_expansion_ratio",
        "news_shock_threshold",
        "peak_drawdown_exit_pct",
        "profit_protection_activation_pct",
        "vwap_breakdown_pct",
        "intraday_low_break_pct",
    ):
        raw = env_values[key]
        if raw:
            base = to_float(out.get(key))
            x = to_float(raw)
            out[key] = float(x if x > 0.0 else base)
    if env_values["peak_drawdown_mode"]:
        out["peak_drawdown_mode"] = str(env_values["peak_drawdown_mode"] or "").strip().lower()
    if env_values["trend_strength_floor"]:
        out["trend_strength_floor"] = to_float(env_values["trend_strength_floor"], to_float(out.get("trend_strength_floor")))
    if eod_flat_enabled is not None:
        out["use_eod_flat"] = is_trueish(eod_flat_enabled)
    elif eod_flat_raw:
        out["use_eod_flat"] = is_trueish(eod_flat_raw)
    elif out.get("use_eod_flat") in (None, ""):
        out["use_eod_flat"] = True
    if eod_cutoff_value is not None:
        base = to_float(out.get("eod_flat_cutoff_min"))
        if base <= 0.0:
            base = 10.0
        x = to_float(eod_cutoff_value)
        out["eod_flat_cutoff_min"] = int(x if x > 0.0 else base)
    if emergency_raw:
        out["emergency_halt"] = is_trueish(emergency_raw)
    if out.get("profit_protection_activation_pct") in (None, ""):
        out["profit_protection_activation_pct"] = 0.008
    if out.get("peak_drawdown_mode") in (None, ""):
        out["peak_drawdown_mode"] = "profit_protection"
    for key, value in EXIT_PROFIT_DEFAULTS.items():
        if out.get(key) in (None, ""):
            out[key] = value
    out.setdefault("policy_source", str(out.get("effective_policy_source") or "monitor_exit_policy_effective"))
    out.setdefault("effective_policy_source", str(out.get("policy_source") or "monitor_exit_policy_effective"))
    return apply_broker_cost_profile_to_exit_policy(out)
