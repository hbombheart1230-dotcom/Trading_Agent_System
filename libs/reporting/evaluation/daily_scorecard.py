from __future__ import annotations

from collections import Counter
from typing import Any

from .contracts import CONTRACT_VERSION, DecisionClass, IntegrityStatus, contract_metadata
from .metrics import performance_metrics


def build_daily_scorecard(
    *,
    day: str,
    inventory: dict[str, Any],
    trade_evaluations: list[dict[str, Any]],
    attributions: list[dict[str, Any]],
    q8_review: dict[str, Any],
    start_gate: dict[str, Any],
    day_validity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eligible = [
        row for row in trade_evaluations
        if bool((row.get("integrity") or {}).get("promotion_metric_eligible"))
    ]
    returns = [
        float((row.get("realized_outcome") or {}).get("net_return_pct"))
        for row in eligible
        if (row.get("realized_outcome") or {}).get("net_return_pct") is not None
    ]
    integrity_counts = Counter(
        str((row.get("integrity") or {}).get("status") or IntegrityStatus.FAIL.value)
        for row in trade_evaluations
    )
    horizon_rows = [
        row.get("horizon_alignment") or {}
        for row in trade_evaluations
        if str((row.get("horizon_alignment") or {}).get("status") or "") == "observed"
    ]
    horizon_buckets = Counter(str(row.get("bucket") or "unknown") for row in horizon_rows)
    horizon_violation_candidates = [
        row for row in horizon_rows
        if bool(row.get("horizon_violation_candidate"))
    ]
    before_min_rows = [
        row for row in horizon_rows
        if bool(row.get("exited_before_min_hold"))
    ]
    before_target_rows = [
        row for row in horizon_rows
        if bool(row.get("exited_before_target_hold"))
    ]
    target_improvement_rows = [
        row for row in horizon_rows
        if bool(row.get("target_hold_would_improve_exit"))
    ]
    early_exit_cost_values = [
        float(row.get("early_exit_cost_pct"))
        for row in horizon_rows
        if row.get("early_exit_cost_pct") is not None
    ]
    strategist_deltas = [
        row["deltas"]["strategist_delta_pct"]
        for row in attributions
        if (row.get("deltas") or {}).get("strategist_delta_pct") is not None
    ]
    q8_gate = q8_review.get("evaluation_trust_gate") if isinstance(q8_review.get("evaluation_trust_gate"), dict) else {}
    if str(start_gate.get("status") or "") != "READY":
        decision = DecisionClass.INSUFFICIENT_EVIDENCE.value
    elif not returns:
        decision = DecisionClass.INSUFFICIENT_EVIDENCE.value
    elif sum(returns) / len(returns) < 0:
        decision = DecisionClass.ADJUST_AND_RETEST.value
    else:
        decision = DecisionClass.RETAIN.value
    realized_performance = performance_metrics(returns)
    realized_performance["return_samples_pct"] = returns
    return {
        "schema_version": "daily_scorecard.v1",
        "contract_version": CONTRACT_VERSION,
        "day": day,
        "decision_class": decision,
        "evaluation_phase": {
            "q8_status": "CLOSED",
            "q9_status": "READINESS" if str(start_gate.get("status") or "") != "READY" else "FORWARD_WINDOW_ELIGIBLE",
            "full_chain_start_gate": start_gate,
            "q9_day_validity": day_validity or {},
        },
        "artifact_integrity": {
            "required_coverage": inventory.get("required_coverage"),
            "status_counts": dict(integrity_counts),
            "trade_count": len(trade_evaluations),
            "eligible_trade_count": len(eligible),
        },
        "realized_performance": realized_performance,
        "selection_attribution": {
            "comparison_count": len(strategist_deltas),
            "average_strategist_delta_pct": round(sum(strategist_deltas) / len(strategist_deltas), 4) if strategist_deltas else None,
            "unavailable_count": len(attributions) - len(strategist_deltas),
        },
        "horizon_alignment": {
            "observed_count": len(horizon_rows),
            "bucket_counts": dict(horizon_buckets),
            "exit_before_min_hold_count": len(before_min_rows),
            "exit_before_target_hold_count": len(before_target_rows),
            "horizon_violation_candidate_count": len(horizon_violation_candidates),
            "target_hold_would_improve_exit_count": len(target_improvement_rows),
            "average_early_exit_cost_pct": (
                round(sum(early_exit_cost_values) / len(early_exit_cost_values), 4)
                if early_exit_cost_values
                else None
            ),
        },
        "q8_shadow_evidence": {
            "candidate_count": q8_review.get("candidate_count"),
            "trusted_forward_count": q8_gate.get("trusted_forward_count"),
            "trusted_forward_coverage": q8_gate.get("trusted_forward_coverage"),
            "promotion_allowed": q8_gate.get("promotion_allowed"),
            "trust_gate_status": q8_gate.get("status"),
        },
        "contract": contract_metadata(),
    }
