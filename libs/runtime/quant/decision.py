from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.runtime.monitor_exit.reasons import is_emergency_exit_reason, is_hard_exit_reason
from libs.runtime.quant.entry_promotion_policy import evaluate_promoted_entry_policy
from libs.runtime.quant.tactics import normalize_tactic_id
from libs.runtime.strategy_horizon_feedback import (
    extract_commander_horizon_policy_from_state,
    extract_strategy_horizon_feedback_from_state,
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, (list, tuple)) else []


def _factors(snapshot: Mapping[str, Any] | None) -> Dict[str, Any]:
    obj = _mapping(snapshot)
    return _mapping(obj.get("factors"))


def _expected_hold_window(state: Mapping[str, Any] | None) -> Dict[str, Any]:
    commander = extract_commander_horizon_policy_from_state(state)
    horizon = commander or extract_strategy_horizon_feedback_from_state(state)
    window = _mapping(horizon.get("expected_hold_window"))
    if not window:
        return {}
    return {
        "min_sec": _to_int(window.get("min_sec"), 0),
        "target_sec": _to_int(window.get("target_sec"), 0),
        "max_sec": _to_int(window.get("max_sec"), 0),
        "source": "commander" if commander else str(horizon.get("source") or "strategist"),
    }


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def build_entry_quant_decision(
    entry_info: Mapping[str, Any] | None,
    *,
    selected: Mapping[str, Any] | None = None,
    factor_snapshot: Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    entry = _mapping(entry_info)
    selected_row = _mapping(selected)
    factors = _factors(factor_snapshot)
    tactic = normalize_tactic_id(
        tactic_id or _mapping(factor_snapshot).get("tactic_id") or selected_row.get("tactical_strategy"),
        playbook=playbook or str(selected_row.get("playbook") or "defensive"),
    )
    suitability = _mapping(selected_row.get("tactic_suitability"))
    suitability_score = suitability.get("score")
    suitability_tier = str(suitability.get("tier") or "unavailable")
    cost_filter = _mapping(entry.get("entry_cost_filter")) or _mapping(entry.get("cost_filter"))
    failed_checks = [str(x or "").strip() for x in _list(entry.get("failed_checks")) if str(x or "").strip()]
    hard_failures = [str(x or "").strip() for x in _list(entry.get("hard_filter_fail_reasons")) if str(x or "").strip()]
    reason = str(entry.get("guard_reason") or entry.get("reason") or "").strip()
    axis = str(entry.get("primary_failure_axis") or "").strip()
    blockers: list[str] = []
    warnings: list[str] = []
    positives: list[str] = []

    cost_ok = bool(entry.get("cost_adjusted_edge_ok"))
    cost_filter_passed = bool(cost_filter.get("passed") or cost_filter.get("cost_adjusted_edge_ok"))
    cost_floor_state = str(factors.get("cost_floor_state") or "").strip()
    if not cost_floor_state:
        if cost_filter or entry.get("cost_adjusted_edge_pct") not in (None, ""):
            cost_floor_state = "met" if bool(cost_ok or cost_filter_passed) else "not_met"
    if cost_filter and not cost_filter_passed:
        _append_unique(blockers, "cost_edge_fail")
    elif cost_floor_state == "not_met" or (entry.get("cost_adjusted_edge_pct") not in (None, "") and not cost_ok):
        _append_unique(blockers, "cost_edge_fail")
    elif cost_ok or cost_floor_state == "met":
        _append_unique(positives, "cost_edge_ok")

    reason_pool = {reason, axis, *failed_checks, *hard_failures}
    if "volume_confirmation_missing" in reason_pool or "volume_insufficient" in reason_pool:
        _append_unique(blockers, "volume_confirmation_missing")
    if "directional_edge_evidence_missing" in reason_pool:
        _append_unique(blockers, "directional_edge_evidence_missing")
    if "same_symbol_position_open" in reason_pool:
        _append_unique(blockers, "same_symbol_position_open")
    if "pullback_not_mature" in reason_pool:
        target = blockers if tactic != "lower_vwap_rebound_probe" else warnings
        _append_unique(target, "pullback_not_mature")
    for item in hard_failures:
        _append_unique(blockers, item)

    if suitability_tier == "weak":
        _append_unique(warnings, "weak_tactic_suitability")
        if tactic == "lower_vwap_rebound_probe":
            _append_unique(blockers, "weak_probe_tactic_suitability")
    elif suitability_tier in {"strong", "watch"}:
        _append_unique(positives, f"tactic_suitability_{suitability_tier}")

    promoted_policy = evaluate_promoted_entry_policy(
        tactic_id=tactic,
        suitability_tier=suitability_tier,
        suitability_score=suitability_score,
        factors=factors,
        cost_ok=bool(cost_ok or cost_filter_passed or cost_floor_state == "met"),
    )
    for item in _list(promoted_policy.get("blockers")):
        _append_unique(blockers, str(item))
    for item in _list(promoted_policy.get("warnings")):
        _append_unique(warnings, str(item))
    for item in _list(promoted_policy.get("positive_reasons")):
        _append_unique(positives, str(item))

    if blockers:
        decision = "block_recommended"
    elif bool(entry.get("triggered")) or str(entry.get("legacy_entry_decision") or "").upper() == "BUY":
        decision = "entry_ready"
    else:
        decision = "wait"

    return {
        "schema_version": "quant_entry_decision.v1",
        "tactic_id": tactic,
        "playbook": str(playbook or selected_row.get("playbook") or ""),
        "decision": decision,
        "blockers": blockers[:10],
        "warnings": warnings[:10],
        "positive_reasons": positives[:10],
        "commander_override_required": bool(blockers),
        "override_reason_required_for": blockers[:10],
        "cost_edge": {
            "ok": bool(cost_ok or cost_filter_passed),
            "cost_adjusted_edge_pct": entry.get("cost_adjusted_edge_pct"),
            "cost_drag_pct": entry.get("cost_drag_pct"),
            "cost_floor_state": cost_floor_state or "unavailable",
        },
        "tactic_suitability": {
            "score": _to_float(suitability_score) if suitability_score not in (None, "") else None,
            "tier": suitability_tier,
        },
        "expected_hold_window": _expected_hold_window(state),
        "factor_snapshot_ref": {
            "source": _mapping(factor_snapshot).get("source"),
            "tactic_id": _mapping(factor_snapshot).get("tactic_id"),
            "missing": list(_mapping(factor_snapshot).get("missing") or []),
        },
        "promoted_entry_policy": dict(promoted_policy),
        "behavior_effect": "observation_only",
    }


def build_exit_quant_decision(
    exit_info: Mapping[str, Any] | None,
    *,
    state: Mapping[str, Any] | None = None,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    exit_obj = _mapping(exit_info)
    reason = str(exit_obj.get("reason") or exit_obj.get("monitor_reason") or "").strip()
    tactic = normalize_tactic_id(tactic_id, playbook=playbook or "defensive")
    expected = _expected_hold_window(state)
    exit_vs_strategy = _mapping(exit_obj.get("exit_vs_strategy_intent"))
    actual_hold_sec = _to_int(
        exit_obj.get("position_age_seconds")
        if exit_obj.get("position_age_seconds") not in (None, "")
        else exit_obj.get("hold_sec")
        if exit_obj.get("hold_sec") not in (None, "")
        else exit_vs_strategy.get("actual_hold_sec"),
        0,
    )
    min_hold_sec = _to_int(expected.get("min_sec") or _mapping(exit_vs_strategy.get("expected_hold_window")).get("min_sec"), 0)
    triggered = bool(exit_obj.get("triggered") or exit_obj.get("exit_signal_detected"))
    reason_key = reason.lower().replace(" ", "_")
    confirmation_style_reason = reason_key in {"intraday_low_break", "vwap_breakdown", "vwap_exit"}
    hard_invalidation_reason = str(exit_obj.get("protective_exit_hard_invalidation_reason") or "")
    metric_only_protective_hard = bool(
        confirmation_style_reason
        and hard_invalidation_reason.startswith(("intraday_low_break_deep:", "vwap_breakdown_deep:"))
    )
    explicit_hard_exit = bool(exit_obj.get("hard_exit") and not confirmation_style_reason)
    protective_hard_exit = bool(exit_obj.get("protective_exit_hard_invalidation") and not metric_only_protective_hard)
    hard_exit = bool(
        is_emergency_exit_reason(reason)
        or exit_obj.get("emergency_exit")
        or protective_hard_exit
        or explicit_hard_exit
        or (is_hard_exit_reason(reason) and not confirmation_style_reason)
    )
    confirmation_required = bool(
        exit_obj.get("intraday_low_break_confirmation_required")
        or exit_obj.get("intraday_low_break_confirmation_pending")
        or exit_obj.get("time_limit_reassessment_required")
        or confirmation_style_reason
    )
    confirmed = bool(
        exit_obj.get("intraday_low_break_confirmed")
        or not exit_obj.get("intraday_low_break_confirmation_pending")
    )
    early_exit = bool(triggered and actual_hold_sec > 0 and min_hold_sec > 0 and actual_hold_sec < min_hold_sec)
    warnings: list[str] = []
    blockers: list[str] = []
    positives: list[str] = []

    if hard_exit:
        _append_unique(positives, "hard_exit_allowed")
    if early_exit and not hard_exit:
        _append_unique(warnings, "early_exit_before_expected_min_hold")
    if confirmation_required and not hard_exit and not confirmed:
        _append_unique(blockers, "exit_confirmation_pending")
    if bool(exit_obj.get("cost_aware_profit_floor_blocked")):
        _append_unique(blockers, "cost_profit_floor_not_met")
    if bool(exit_obj.get("expected_exit_profit_floor_blocked")):
        _append_unique(blockers, "expected_exit_profit_floor_not_met")

    if not triggered:
        decision = "hold_watch"
    elif hard_exit:
        decision = "hard_exit"
    elif blockers:
        decision = "confirm_before_exit_recommended"
    elif early_exit:
        decision = "early_exit_warning"
    else:
        decision = "exit_aligned"

    return {
        "schema_version": "quant_exit_decision.v1",
        "tactic_id": tactic,
        "playbook": str(playbook or ""),
        "decision": decision,
        "exit_reason": reason,
        "hard_exit": bool(hard_exit),
        "confirmation_required": bool(confirmation_required),
        "confirmation_pending": bool(confirmation_required and not confirmed and not hard_exit),
        "blockers": blockers[:10],
        "warnings": warnings[:10],
        "positive_reasons": positives[:10],
        "expected_hold_window": expected or _mapping(exit_vs_strategy.get("expected_hold_window")),
        "actual_hold_sec": actual_hold_sec if actual_hold_sec > 0 else None,
        "early_exit_flag": bool(early_exit),
        "hold_window_mismatch": bool(early_exit and not hard_exit),
        "exit_vs_strategy_alignment": str(exit_vs_strategy.get("exit_alignment") or ""),
        "exit_vs_strategy_alignment_reason": str(exit_vs_strategy.get("alignment_reason") or ""),
        "pnl_ratio": exit_obj.get("pnl_ratio"),
        "gross_pnl_ratio": exit_obj.get("gross_pnl_ratio"),
        "cost_floor": {
            "cost_aware_profit_floor_met": bool(exit_obj.get("cost_aware_profit_floor_met")),
            "expected_exit_profit_floor_met": bool(exit_obj.get("expected_exit_profit_floor_met")),
            "cost_aware_profit_floor_gap_pct": exit_obj.get("cost_aware_profit_floor_gap_pct"),
            "expected_exit_profit_floor_gap_pct": exit_obj.get("expected_exit_profit_floor_gap_pct"),
        },
        "behavior_effect": "observation_only",
    }
