from __future__ import annotations

from typing import Any, Dict, Mapping


_BLOCKED_RUNNER_REASONS = {
    "volume_confirmation_missing",
    "volume_insufficient",
    "volume_missing",
    "cost_adjusted_edge_not_ready",
    "cost_filter_failed",
    "directional_edge_evidence_missing",
    "estimated_gross_edge_missing",
    "entry_quality_gate_blocked",
    "pullback_not_mature",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def evaluate_runner_up_entry_quality(
    *,
    runner_row: Mapping[str, Any],
    runner_entry: Mapping[str, Any],
    runner_guard_blocked: bool = False,
) -> Dict[str, Any]:
    """Require runner-up buys to prove their own edge, not inherit rank-1 intent."""

    row = dict(runner_row or {})
    entry = dict(runner_entry or {})
    metrics = _mapping(entry.get("metrics"))
    scores = _mapping(entry.get("condition_scores"))
    score_breakdown = _mapping(row.get("score_breakdown")) or _mapping(entry.get("score_breakdown"))
    reason = str(entry.get("reason") or "").strip()
    reason_l = reason.lower()

    checks: Dict[str, bool] = {}
    checks["triggered"] = bool(entry.get("triggered") or entry.get("intent_submitted"))
    checks["guard_clear"] = not bool(runner_guard_blocked or entry.get("guard_blocked"))
    checks["reason_clear"] = reason not in _BLOCKED_RUNNER_REASONS
    checks["cost_edge_ok"] = bool(entry.get("cost_adjusted_edge_ok"))

    turnover_value = max(
        _to_float(score_breakdown.get("turnover"), 0.0),
        _to_float(row.get("turnover_score"), 0.0),
        _to_float(row.get("turnover"), 0.0),
        _to_float(row.get("turnover_value"), 0.0),
    )
    turnover_observed = any(
        key in score_breakdown or key in row
        for key in ("turnover", "turnover_score", "turnover_value")
    )
    checks["turnover_ok"] = bool(turnover_value > 0.0 or not turnover_observed)

    volume_observed = any(key in metrics for key in ("volume_ok", "volume_ratio", "relative_volume", "volume"))
    volume_ratio = _to_float(metrics.get("volume_ratio"), 0.0)
    checks["volume_ok"] = bool(
        not volume_observed
        or metrics.get("volume_ok")
        or volume_ratio >= 1.0
        or "volume" in reason_l
    )

    entry_path = str(entry.get("entry_condition_path") or "").strip()
    checks["chart_mature"] = bool(
        metrics.get("pullback_mature")
        or metrics.get("breakout_ok")
        or metrics.get("pullback_volume_path_ok")
        or metrics.get("human_chart_entry_setup_applied")
        or entry_path in {
            "breakout_path",
            "pullback_volume_path",
            "human_chart_setup_path",
            "inverse_hedge_reclaim_path",
            "etf_discount_reversion_path",
        }
        or "breakout" in reason_l
        or "vwap" in reason_l
        or "pullback" in reason_l
        or "rebound" in reason_l
    )

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "passed": not failed,
        "failed_checks": failed,
        "checks": checks,
        "reason": "" if not failed else "runner_up_quality_gate_failed",
        "turnover_value": turnover_value if turnover_observed else None,
        "turnover_observed": bool(turnover_observed),
        "volume_ratio": volume_ratio if volume_ratio > 0.0 else None,
        "entry_reason": reason,
    }
