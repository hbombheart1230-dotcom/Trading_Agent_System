from __future__ import annotations

from typing import Any, Mapping


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_num(row: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _nested_mapping(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    return value if isinstance(value, Mapping) else {}


def decompose_scanner_score(candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return an additive, read-only score view for scanner candidates.

    This does not change ranking behavior. It only separates the fields that are
    often conflated in reports: raw technical quality, strategy context,
    cost/horizon fit, and execution readiness.
    """

    row = candidate if isinstance(candidate, Mapping) else {}
    score_breakdown = _nested_mapping(row, "score_breakdown")
    features = _nested_mapping(row, "features")
    quant = _nested_mapping(row, "quant_factors")
    cost = _nested_mapping(row, "cost_filter")
    monitor = _nested_mapping(row, "monitor")

    raw_momentum = _first_num(
        row,
        (
            "raw_momentum_quality_score",
            "momentum_score",
            "trend_score",
            "breakout_score",
            "score_intrinsic",
        ),
    )
    if raw_momentum is None:
        raw_momentum = _first_num(score_breakdown, ("momentum", "trend", "breakout", "intrinsic"))

    strategy_context = _first_num(
        row,
        (
            "strategy_context_score",
            "strategist_score",
            "theme_score",
            "rank_score",
        ),
    )
    if strategy_context is None:
        strategy_context = _first_num(score_breakdown, ("strategy", "strategist", "theme", "rank_score"))

    cost_horizon = _first_num(
        row,
        (
            "cost_horizon_fit_score",
            "cost_adjusted_edge_pct",
            "expected_edge_pct",
            "reward_room_pct",
        ),
    )
    if cost_horizon is None:
        cost_horizon = _first_num(cost, ("cost_adjusted_edge_pct", "expected_edge_pct"))
    if cost_horizon is None:
        cost_horizon = _first_num(quant, ("cost_adjusted_edge_pct", "reward_room_pct"))
    if cost_horizon is None:
        cost_horizon = _first_num(features, ("reward_room_pct", "expected_move_pct"))

    execution_readiness = _first_num(
        row,
        (
            "execution_readiness_score",
            "entry_quality_score",
            "transition_readiness_score",
            "confidence_score",
        ),
    )
    if execution_readiness is None:
        execution_readiness = _first_num(monitor, ("entry_quality_score", "transition_readiness_score"))
    if execution_readiness is None:
        execution_readiness = _first_num(quant, ("entry_quality_score", "confidence_score"))

    return {
        "schema_version": "scanner_score_decomposition.v1",
        "behavior_effect": "observation_only",
        "symbol": str(row.get("symbol") or ""),
        "rank": row.get("rank"),
        "total_score": _first_num(row, ("score_total", "score", "combined_score")),
        "raw_momentum_quality_score": raw_momentum,
        "strategy_context_score": strategy_context,
        "cost_horizon_fit_score": cost_horizon,
        "execution_readiness_score": execution_readiness,
        "source_fields_present": {
            "score_breakdown": bool(score_breakdown),
            "features": bool(features),
            "quant_factors": bool(quant),
            "cost_filter": bool(cost),
            "monitor": bool(monitor),
        },
        "limitations": [
            "Field names vary by artifact source; missing components mean unavailable, not zero.",
            "This decomposition is report-only and does not alter scanner ranking.",
        ],
    }


__all__ = ["decompose_scanner_score"]
