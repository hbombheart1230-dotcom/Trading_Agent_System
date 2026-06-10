from __future__ import annotations

from typing import Any, Dict, Mapping


SUPPORTIVE_RAILS = {
    "krx_night_futures_gap_up",
    "risk_on_supportive",
}

RELAXABLE_REASONS = {
    "volume_insufficient",
    "volume_confirmation_missing",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
    "breakout_not_ready",
    "cost_adjusted_edge_not_ready",
    "quant_entry_block:cost_edge_fail",
    "quant_entry_block:volume_confirmation_missing",
}

HARD_BLOCK_REASONS = {
    "same_symbol_position_open",
    "same_symbol_pending_buy",
    "max_positions_reached",
    "buy_blocked_closeout_window",
    "post_exit_cooldown",
    "closeout_unresolved_flatten_required",
    "overnight_carry_recovery_pending",
    "risk_off_defensive_observe_no_entry",
    "human_chart_sanity_guard_blocked",
}

HARD_BLOCKER_TOKENS = {
    "same_symbol_position_open",
    "same_symbol_pending_buy",
    "directional_edge_evidence_missing",
    "weak_probe_tactic_suitability",
    "vwap_pullback_promoted_quality_gate",
    "exit_risk_score>=0.40",
    "vwap_breakdown_persistence=strong",
    "entry_chart_score<0.25",
    "swing_low_break=true",
}


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "unknown", "not_captured"} else text


def _lower(value: Any) -> str:
    return _text(value).lower()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return bool(value)
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


def _factors(factor_snapshot: Mapping[str, Any] | None) -> Dict[str, Any]:
    snapshot = _as_dict(factor_snapshot)
    return _as_dict(snapshot.get("factors"))


def _blockers(entry_quant_decision: Mapping[str, Any] | None) -> list[str]:
    decision = _as_dict(entry_quant_decision)
    return [_text(item) for item in list(decision.get("blockers") or []) if _text(item)]


def _cost_state(entry_quant_decision: Mapping[str, Any] | None, factors: Mapping[str, Any]) -> str:
    decision = _as_dict(entry_quant_decision)
    cost = _as_dict(decision.get("cost_edge"))
    return _lower(cost.get("cost_floor_state") or factors.get("cost_floor_state"))


def _market_supportive(*, market_regime: Any, market_regime_rail: Any) -> bool:
    regime = _lower(market_regime)
    rail = _lower(market_regime_rail)
    return rail in SUPPORTIVE_RAILS or (regime == "risk_on" and "risk_off" not in rail)


def _has_hard_block(*, reason: str, guard_reason: str, blockers: list[str]) -> bool:
    reason_values = {reason, guard_reason}
    if reason_values & HARD_BLOCK_REASONS:
        return True
    return any(item in HARD_BLOCKER_TOKENS for item in blockers)


def _cost_near_miss_ok(
    *,
    blockers: list[str],
    cost_state: str,
    cost_adjusted_edge_pct: Any,
    cost_drag_pct: Any,
) -> bool:
    has_cost_block = "cost_edge_fail" in blockers or cost_state == "not_met"
    if not has_cost_block:
        return True
    edge = _float(cost_adjusted_edge_pct, 0.0)
    drag = _float(cost_drag_pct, 0.0)
    if cost_adjusted_edge_pct not in (None, "") and edge < -0.0025:
        return False
    return drag <= 0.0035


def evaluate_market_rail_translation(
    *,
    entry_info: Mapping[str, Any] | None,
    entry_quant_decision: Mapping[str, Any] | None,
    factor_snapshot: Mapping[str, Any] | None,
    market_regime: Any = "",
    market_regime_rail: Any = "",
) -> Dict[str, Any]:
    """Translate supportive market rails into limited existing-lane relaxations.

    This intentionally does not create a new lane. It only marks when an
    existing near-ready blocker can be treated as a small probe under a strong
    market rail. Operational hard guards remain non-relaxable.
    """

    entry = _as_dict(entry_info)
    factors = _factors(factor_snapshot)
    blockers = _blockers(entry_quant_decision)
    reason = _lower(entry.get("reason"))
    guard_reason = _lower(entry.get("guard_reason"))
    axis = _lower(entry.get("primary_failure_axis"))
    rail = _text(market_regime_rail)
    regime = _text(market_regime)

    volume_ratio = _float(factors.get("volume_ratio"))
    vwap_distance = _float(factors.get("vwap_distance_pct"))
    reclaim_progress = _float(factors.get("vwap_reclaim_progress"))
    entry_quality = _float(factors.get("entry_quality_score"))
    human_score = _float(factors.get("human_chart_entry_score"))
    exit_risk = _float(factors.get("human_chart_exit_risk_score"))
    weighted_score = _float(factors.get("weighted_score_total"))
    breakout_ok = _bool(factors.get("breakout_ok"))
    weighted_passed = _bool(factors.get("weighted_score_passed"))
    cost_state = _cost_state(entry_quant_decision, factors)
    cost_edge = _as_dict(_as_dict(entry_quant_decision).get("cost_edge"))

    relaxed: list[str] = []
    notes: list[str] = []
    hard_block = _has_hard_block(reason=reason, guard_reason=guard_reason, blockers=blockers)
    supportive = _market_supportive(market_regime=regime, market_regime_rail=rail)
    cost_near = _cost_near_miss_ok(
        blockers=blockers,
        cost_state=cost_state,
        cost_adjusted_edge_pct=cost_edge.get("cost_adjusted_edge_pct"),
        cost_drag_pct=cost_edge.get("cost_drag_pct") if cost_edge.get("cost_drag_pct") not in (None, "") else factors.get("cost_drag_pct"),
    )

    if not supportive:
        notes.append("market_rail_not_supportive")
    if hard_block:
        notes.append("hard_blocker_present")
    if not cost_near:
        notes.append("cost_edge_not_near_miss")
    if exit_risk >= 0.55:
        notes.append("exit_risk_too_high")
    if human_score and human_score < 0.25:
        notes.append("human_chart_entry_too_weak")

    volume_near = bool(
        (reason in {"volume_insufficient", "volume_confirmation_missing"} or axis == "volume_confirmation" or "volume_confirmation_missing" in blockers)
        and volume_ratio >= 0.45
        and entry_quality >= 0.62
        and vwap_distance >= -0.004
    )
    vwap_near = bool(
        reason in {"below_vwap_reclaim_not_ready", "pullback_below_vwap_reclaim_not_ready"}
        and vwap_distance >= -0.012
        and volume_ratio >= 0.45
        and (reclaim_progress >= 0.65 or entry_quality >= 0.66 or human_score >= 0.50)
    )
    breakout_near = bool(
        reason == "breakout_not_ready"
        and volume_ratio >= 0.55
        and vwap_distance >= -0.003
        and (breakout_ok or weighted_passed or weighted_score >= 1.2 or entry_quality >= 0.70)
    )
    cost_only_near = bool(
        ("cost_edge_fail" in blockers or guard_reason == "cost_adjusted_edge_not_ready")
        and reason in RELAXABLE_REASONS
        and entry_quality >= 0.70
        and volume_ratio >= 0.50
        and vwap_distance >= -0.004
    )

    if volume_near:
        relaxed.append("volume_confirmation_near_ready")
    if vwap_near:
        relaxed.append("vwap_reclaim_near_ready")
    if breakout_near:
        relaxed.append("breakout_near_ready")
    if cost_only_near or (cost_near and ("cost_edge_fail" in blockers or cost_state == "not_met")):
        relaxed.append("cost_near_miss")

    allowed = bool(
        supportive
        and not hard_block
        and cost_near
        and exit_risk < 0.55
        and (not human_score or human_score >= 0.25)
        and any(item in relaxed for item in {"volume_confirmation_near_ready", "vwap_reclaim_near_ready", "breakout_near_ready", "cost_near_miss"})
        and (volume_near or vwap_near or breakout_near or cost_only_near)
    )
    return {
        "schema_version": "market_rail_translation.v1",
        "behavior_effect": "entry_guard_translation" if allowed else "observation_only",
        "applied": bool(allowed),
        "market_regime": regime,
        "market_regime_rail": rail,
        "relaxation_scope": "supportive_market_rail_existing_lanes_only",
        "relaxed_blockers": relaxed[:8],
        "probe_size_hint": "small" if allowed else "",
        "probe_max_qty": 1 if allowed else 0,
        "allow_probe": bool(allowed),
        "reason": "supportive_market_rail_near_ready_probe" if allowed else ",".join(notes) or "not_near_ready",
        "inputs": {
            "reason": reason,
            "guard_reason": guard_reason,
            "primary_failure_axis": axis,
            "blockers": blockers,
            "cost_floor_state": cost_state,
            "volume_ratio": volume_ratio,
            "vwap_distance_pct": vwap_distance,
            "vwap_reclaim_progress": reclaim_progress,
            "entry_quality_score": entry_quality,
            "human_chart_entry_score": human_score,
            "human_chart_exit_risk_score": exit_risk,
            "weighted_score_total": weighted_score,
        },
    }


__all__ = ["evaluate_market_rail_translation"]
