from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.runtime.quant.vwap_reclaim_observation import classify_below_vwap_reclaim_observation


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "unknown", "not_captured"} else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _factors(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _as_dict(row.get("quant_factor_snapshot"))
    factors = _as_dict(snapshot.get("factors"))
    if factors:
        return factors
    return _as_dict(row.get("factors"))


def _metric(row: Mapping[str, Any], factors: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    if row.get(key) not in (None, ""):
        return _float(row.get(key), default)
    return _float(factors.get(key), default)


def entry_time_bucket(opening_minutes: int | None) -> str:
    if opening_minutes is None:
        return "preopen_or_unknown"
    if opening_minutes < 0:
        return "preopen"
    if opening_minutes <= 20:
        return "open_0_20m"
    if opening_minutes <= 60:
        return "open_20_60m"
    if opening_minutes < 330:
        return "mid_session"
    if opening_minutes < 380:
        return "late_session"
    return "closeout_window"


def _cost_floor_state(row: Mapping[str, Any], factors: Mapping[str, Any]) -> str:
    direct = _text(row.get("entry_quant_cost_floor_state") or row.get("cost_floor_state"))
    if direct:
        return direct
    decision = _as_dict(row.get("entry_quant_decision"))
    cost_edge = _as_dict(decision.get("cost_edge"))
    return _text(cost_edge.get("cost_floor_state") or factors.get("cost_floor_state"))


def _entry_shape(row: Mapping[str, Any]) -> str:
    reason = _text(row.get("reason"))
    primary = _text(row.get("primary_failure_axis"))
    if reason in {
        "pullback_not_mature",
        "pullback_below_vwap_reclaim_not_ready",
        "pullback_structure_above_vwap_with_volume_confirmation",
    } or primary == "pullback_structure":
        return "pullback"
    if reason in {
        "below_vwap_reclaim_not_ready",
        "pullback_below_vwap_reclaim_not_ready",
    } or primary == "vwap_relationship":
        return "vwap_reclaim"
    if reason in {
        "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
        "breakout_above_recent_high_with_vwap_structure_confirmation",
        "breakout_not_ready",
    } or primary == "breakout_readiness":
        return "breakout"
    if reason in {"volume_confirmation_missing", "volume_insufficient"} or primary == "volume_confirmation":
        return "volume_confirmation"
    if reason == "human_chart_sanity_guard_blocked" or primary == "human_chart_sanity":
        return "human_chart_sanity"
    if reason in {"cost_edge_fail", "cost_filter_failed"} or primary == "cost_edge":
        return "cost_edge"
    return "other"


def _opening_probe_subtype(row: Mapping[str, Any]) -> str:
    probe = _as_dict(row.get("opening_momentum_probe_shadow"))
    reason = _text(probe.get("reason"))
    if not probe:
        return ""
    if _bool(probe.get("would_probe")):
        return "opening_momentum_probe_ready"
    if reason == "outside_opening_window":
        return "outside_opening_window"
    if "cost_edge_not_met" in reason:
        return "opening_probe_cost_edge_not_met"
    if "volume_ratio_below_probe_floor" in reason:
        return "opening_probe_volume_missing"
    if "below_vwap" in reason:
        return "opening_probe_below_vwap"
    if "momentum_structure_not_confirmed" in reason:
        return "opening_probe_structure_missing"
    return reason or "opening_probe_not_ready"


def _largecap_probe_subtype(row: Mapping[str, Any]) -> str:
    probe = _as_dict(row.get("opening_largecap_surge_shadow"))
    reason = _text(probe.get("reason"))
    if not probe:
        return ""
    if _bool(probe.get("would_probe")):
        return "largecap_surge_probe_ready"
    if reason == "outside_opening_window":
        return "outside_opening_window"
    if reason == "not_largecap_surge_watchlist":
        return "not_largecap_surge_watchlist"
    if "cost" in reason:
        return "largecap_surge_cost_edge_not_met"
    if "volume" in reason:
        return "largecap_surge_volume_missing"
    if "momentum" in reason or "structure" in reason:
        return "largecap_surge_structure_missing"
    return reason or "largecap_surge_not_ready"


def _runner_up_subtype(row: Mapping[str, Any]) -> str:
    if _text(row.get("shadow_role")) != "runner_up_evaluated":
        return ""
    profile = _as_dict(row.get("pullback_evidence_profile"))
    profile_subtype = _text(profile.get("subtype") or profile.get("profile") or profile.get("label"))
    if _bool(row.get("would_enter")):
        return "strong_runner_up"
    if _bool(row.get("weak_fallback_blocked")) or _text(row.get("reason")) == "weak_fallback_pullback":
        return "weak_fallback_blocked"
    if _bool(row.get("runner_up_quality_blocked")) or _text(row.get("reason")) == "runner_up_quality_gate_failed":
        return "runner_up_quality_blocked"
    if profile_subtype:
        if "theme" in profile_subtype:
            return "theme_confirmed_fallback"
        if "liquidity" in profile_subtype or "representative" in profile_subtype:
            return "liquidity_only_fallback"
        return f"runner_up_{profile_subtype}"
    return "runner_up_not_selected"


def _pullback_subtype(row: Mapping[str, Any], factors: Mapping[str, Any]) -> str:
    reason = _text(row.get("reason"))
    volume_ratio = _metric(row, factors, "volume_ratio")
    vwap_distance = _metric(row, factors, "vwap_distance", _metric(row, factors, "vwap_distance_pct"))
    pullback_depth = _metric(row, factors, "pullback_depth_pct")
    entry_quality = _metric(row, factors, "entry_quality_score")
    human_score = _metric(row, factors, "human_chart_entry_score")
    pullback_ok = _bool(row.get("pullback_ok")) or _bool(factors.get("pullback_ok"))
    volume_ok = _bool(row.get("volume_ok")) or _bool(factors.get("volume_ok"))
    if reason == "pullback_structure_above_vwap_with_volume_confirmation" or (pullback_ok and volume_ok):
        return "pullback_confirmed"
    if pullback_depth and pullback_depth < 0.0015:
        return "shallow_pullback"
    if pullback_depth > 0.018 or vwap_distance < -0.01:
        return "deep_pullback_risk"
    if reason == "pullback_not_mature" and (entry_quality >= 0.55 or human_score >= 0.50):
        return "healthy_pullback_forming"
    if volume_ratio < 0.20 or (entry_quality and entry_quality < 0.35):
        return "failed_pullback"
    return "pullback_not_mature"


def _volume_subtype(row: Mapping[str, Any], factors: Mapping[str, Any]) -> str:
    volume_ratio = _metric(row, factors, "volume_ratio")
    pullback_ok = _bool(row.get("pullback_ok")) or _bool(factors.get("pullback_ok"))
    volume_ok = _bool(row.get("volume_ok")) or _bool(factors.get("volume_ok"))
    adjustment_reason = _text(factors.get("volume_adjustment_reason") or row.get("volume_adjustment_reason"))
    skew_ratio = _metric(row, factors, "volume_spike_skew_ratio")
    if volume_ok:
        return "volume_confirmed"
    if adjustment_reason or skew_ratio >= 2.5:
        return "opening_spike_distortion"
    if volume_ratio < 0.20:
        return "dead_volume"
    if pullback_ok and volume_ratio < 0.80:
        return "volume_drying_pullback"
    if volume_ratio < 1.00:
        return "delayed_volume_confirmation"
    return "volume_confirmation_missing"


def _breakout_subtype(row: Mapping[str, Any], factors: Mapping[str, Any]) -> str:
    reason = _text(row.get("reason"))
    volume_ok = _bool(row.get("volume_ok")) or _bool(factors.get("volume_ok"))
    breakout_ok = _bool(row.get("breakout_ok")) or _bool(factors.get("breakout_ok"))
    extension_ok = _bool(row.get("extension_ok")) or _bool(factors.get("extension_ok"))
    vwap_distance = _metric(row, factors, "vwap_distance", _metric(row, factors, "vwap_distance_pct"))
    breakout_score = max(
        _metric(row, factors, "breakout_score"),
        _metric(row, factors, "breakout_proximity_score"),
        _metric(row, factors, "breakout_path_score"),
    )
    if reason in {
        "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
        "breakout_above_recent_high_with_vwap_structure_confirmation",
    } or (breakout_ok and volume_ok):
        return "confirmed_breakout"
    if not extension_ok or vwap_distance > 0.02:
        return "extended_breakout_chase"
    if breakout_ok and not volume_ok:
        return "breakout_without_volume"
    if breakout_score >= 0.80:
        return "pre_breakout_coil"
    return "false_breakout_risk"


def _human_chart_subtype(row: Mapping[str, Any], factors: Mapping[str, Any]) -> str:
    human_score = _metric(row, factors, "human_chart_entry_score")
    entry_quality = _metric(row, factors, "entry_quality_score")
    reclaim_progress = _metric(row, factors, "vwap_reclaim_progress")
    volume_ok = _bool(row.get("volume_ok")) or _bool(factors.get("volume_ok"))
    if human_score >= 0.65 or entry_quality >= 0.70:
        return "good_setup_hard_gated"
    if human_score and human_score < 0.35:
        return "bad_structure"
    if reclaim_progress >= 0.65 and volume_ok:
        return "continuation_watch"
    return "reversal_risk"


def build_entry_lane_observation(
    row: Mapping[str, Any],
    *,
    opening_minutes: int | None = None,
    market_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Attach a diagnostic lane label to a shadow candidate.

    The payload is observation-only. It must not be used directly to enter,
    exit, approve, or block a trade.
    """

    factors = _factors(row)
    context = _as_dict(market_context)
    if opening_minutes is None:
        for probe_key in ("opening_momentum_probe_shadow", "opening_largecap_surge_shadow"):
            probe = _as_dict(row.get(probe_key))
            if probe.get("minutes_since_open") not in (None, ""):
                try:
                    opening_minutes = int(probe.get("minutes_since_open"))
                except Exception:
                    opening_minutes = None
                break
    shape = _entry_shape(row)
    below_vwap = classify_below_vwap_reclaim_observation(row)
    runner_up_subtype = _runner_up_subtype(row)
    opening_subtype = _opening_probe_subtype(row)
    largecap_subtype = _largecap_probe_subtype(row)
    cost_state = _cost_floor_state(row, factors)
    subtype_v2 = ""

    selection_role = _text(row.get("shadow_role"))
    if selection_role == "opening_largecap_watchlist":
        primary_lane = "opening_largecap_surge"
        subtype = largecap_subtype or "largecap_surge_watchlist"
    elif _bool(below_vwap.get("applies")):
        primary_lane = "vwap_reclaim"
        subtype = _text(below_vwap.get("subtype")) or "vwap_reclaim_not_ready"
        subtype_v2 = _text(below_vwap.get("subtype_v2"))
    elif opening_subtype and opening_subtype != "outside_opening_window":
        primary_lane = "opening_momentum"
        subtype = opening_subtype
    elif shape == "cost_edge" or cost_state in {"not_met", "cost_floor_not_met"}:
        primary_lane = "cost_edge"
        subtype = "cost_edge_met" if cost_state == "met" else "cost_edge_not_met"
    elif shape == "pullback":
        primary_lane = "pullback_quality"
        subtype = _pullback_subtype(row, factors)
    elif shape == "volume_confirmation":
        primary_lane = "volume_confirmation"
        subtype = _volume_subtype(row, factors)
    elif shape == "breakout":
        primary_lane = "breakout_readiness"
        subtype = _breakout_subtype(row, factors)
    elif shape == "human_chart_sanity":
        primary_lane = "human_chart_sanity"
        subtype = _human_chart_subtype(row, factors)
    elif selection_role == "runner_up_evaluated":
        primary_lane = "runner_up_selection"
        subtype = runner_up_subtype or "runner_up_not_selected"
    else:
        primary_lane = "confirmed_or_other"
        subtype = "confirmed_entry" if _bool(row.get("would_enter")) else (_text(row.get("reason")) or "uncategorized")

    return {
        "schema_version": "entry_lane_observation.v1",
        "behavior_effect": "observation_only",
        "primary_lane": primary_lane,
        "subtype": subtype,
        "subtype_v2": subtype_v2,
        "selection_role": selection_role,
        "selection_subtype": runner_up_subtype,
        "entry_shape": shape,
        "time_bucket": entry_time_bucket(opening_minutes),
        "minutes_since_open": opening_minutes,
        "market_regime": _text(
            context.get("market_regime")
            or context.get("market_rail")
            or context.get("regime")
        )
        or "unknown",
        "market_regime_rail": _text(
            context.get("market_regime_rail")
            or context.get("rail_id")
            or context.get("rail")
        ),
        "market_regime_rail_shadow": _as_dict(context.get("market_regime_rail_shadow")),
        "cost_floor_state": cost_state,
        "reason": _text(row.get("reason")),
        "primary_failure_axis": _text(row.get("primary_failure_axis")),
        "features": {
            "volume_ratio": _metric(row, factors, "volume_ratio"),
            "vwap_distance_pct": _metric(row, factors, "vwap_distance", _metric(row, factors, "vwap_distance_pct")),
            "pullback_depth_pct": _metric(row, factors, "pullback_depth_pct"),
            "entry_quality_score": _metric(row, factors, "entry_quality_score"),
            "human_chart_entry_score": _metric(row, factors, "human_chart_entry_score"),
            "breakout_score": max(
                _metric(row, factors, "breakout_score"),
                _metric(row, factors, "breakout_proximity_score"),
                _metric(row, factors, "breakout_path_score"),
            ),
        },
    }
