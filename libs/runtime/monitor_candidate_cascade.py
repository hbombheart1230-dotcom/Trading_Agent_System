from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from libs.core.symbols import normalize_symbol

_CASCADE_ELIGIBLE_REASONS = {
    "too_extended_from_vwap",
    "breakout_not_ready",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
}

_HARD_BLOCK_CASCADE_REASONS = {
    "same_symbol_position_open",
    "same_symbol_pending_buy",
    "volume_insufficient",
    "volume_confirmation_missing",
    "volume_missing",
    "cost_filter_failed",
    "cost_adjusted_edge_not_ready",
    "directional_edge_evidence_missing",
    "estimated_gross_edge_missing",
    "entry_quality_gate_blocked",
    "pullback_not_mature",
    "risk_policy_block",
    "closeout_window",
    "daily_loss_limit",
    "broker_truth_mismatch",
    "data_quality_guard",
    "buy_blocked_post_exit_cooldown",
    "buy_blocked_closeout_window",
}

_DEFAULT_MAX_PRIORITY_RANK = 3
_DEFAULT_Q15_MAX_RUNNER_UP_RANK = 3
_DEFAULT_Q15_MAX_SCORE_GAP = 0.20

_Q15_HIGH_RISK_RUNNER_BLOCKERS = {
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
    "volume_confirmation_missing",
    "volume_missing",
    "cost_filter_failed",
    "cost_adjusted_edge_not_ready",
    "directional_edge_evidence_missing",
    "estimated_gross_edge_missing",
    "pullback_not_mature",
    "too_extended_from_vwap",
    "still_overextended_after_pullback",
}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _candidate_rank(row: Mapping[str, Any], fallback_rank: int) -> int:
    for key in ("rank", "priority_rank", "scanner_rank", "selected_rank"):
        try:
            rank = int(float(row.get(key)))
        except Exception:
            rank = 0
        if rank > 0:
            return int(rank)
    return max(1, int(fallback_rank))


def _candidate_score(row: Mapping[str, Any]) -> float | None:
    for key in (
        "score_total",
        "post_adjust_score_total",
        "adjusted_score_total",
        "total_score",
        "score",
        "scanner_score_total",
    ):
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _candidate_blocker(row: Mapping[str, Any]) -> str:
    for key in (
        "expected_monitor_block_reason",
        "dominant_block_reason",
        "monitor_block_reason",
        "entry_block_reason",
        "primary_failure_axis",
        "reason",
    ):
        reason = str(row.get(key) or "").strip()
        if reason:
            return reason
    return ""


def _normalize_reason_set(values: Sequence[Any] | None) -> set[str]:
    return {
        str(item or "").strip()
        for item in list(values or [])
        if str(item or "").strip()
    }


def _quote_missing_symbols(scanner_output: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(scanner_output, Mapping):
        return set()
    diagnostic = scanner_output.get("quote_data_diagnostic")
    if not isinstance(diagnostic, Mapping):
        return set()
    return {
        normalize_symbol(symbol)
        for symbol in list(diagnostic.get("zero_quote_metric_symbols") or [])
        if normalize_symbol(symbol)
    }


def build_entry_candidate_cascade_plan(
    *,
    selected_symbol: str,
    ranked_candidates: Sequence[Mapping[str, Any]] | None,
    scanner_output: Mapping[str, Any] | None,
    open_position_count: int,
    max_positions: int = 1,
    entry_guard_blocked: bool = False,
    entry_guard_reason: str = "",
    entry_triggered: bool = False,
    entry_reason: str = "",
    max_runner_ups: int = _DEFAULT_MAX_PRIORITY_RANK - 1,
    cascade_enabled: bool = True,
    cascade_allowed_reasons: Sequence[Any] | None = None,
    cascade_blocked_reasons: Sequence[Any] | None = None,
    hard_block_override_enabled: bool = False,
    hard_block_override_reason: str = "",
    excluded_symbols: Sequence[Any] | None = None,
    q15_runner_up_gate_enabled: bool = True,
    q15_max_runner_up_rank: int = _DEFAULT_Q15_MAX_RUNNER_UP_RANK,
    q15_max_score_gap: float = _DEFAULT_Q15_MAX_SCORE_GAP,
) -> Dict[str, Any]:
    selected_sym = normalize_symbol(selected_symbol)
    reason = str(entry_reason or "").strip()
    guard_reason = str(entry_guard_reason or "").strip()
    max_positions = max(1, int(max_positions or 1))
    max_runner_ups = max(0, int(max_runner_ups))
    if not bool(cascade_enabled):
        max_runner_ups = 0
    requested_max_priority_rank = max(1, int(max_runner_ups) + 1)
    q15_rank_cap = max(1, int(q15_max_runner_up_rank or _DEFAULT_Q15_MAX_RUNNER_UP_RANK))
    q15_score_gap_cap = max(0.0, float(q15_max_score_gap))
    max_priority_rank = min(requested_max_priority_rank, q15_rank_cap) if q15_runner_up_gate_enabled else requested_max_priority_rank
    if q15_runner_up_gate_enabled:
        max_runner_ups = min(max_runner_ups, max(0, max_priority_rank - 1))
    allowed_reasons = _normalize_reason_set(cascade_allowed_reasons) or set(_CASCADE_ELIGIBLE_REASONS)
    blocked_reasons = _normalize_reason_set(cascade_blocked_reasons)
    plan: Dict[str, Any] = {
        "attempted": False,
        "eligible": False,
        "reason": reason,
        "top_pick_symbol": selected_sym,
        "max_priority_rank": int(max_priority_rank),
        "requested_max_priority_rank": int(requested_max_priority_rank),
        "max_runner_ups": int(max_runner_ups),
        "requested_max_runner_ups": int(max(0, requested_max_priority_rank - 1)),
        "cascade_enabled": bool(cascade_enabled and max_runner_ups > 0),
        "q15_runner_up_gate_enabled": bool(q15_runner_up_gate_enabled),
        "q15_max_runner_up_rank": int(q15_rank_cap),
        "q15_max_score_gap": float(q15_score_gap_cap),
        "cascade_allowed_reasons": sorted(allowed_reasons),
        "cascade_blocked_reasons": sorted(blocked_reasons),
        "hard_block_override_enabled": bool(hard_block_override_enabled),
        "hard_block_override_reason": str(hard_block_override_reason or ""),
        "runner_up_symbols": [],
        "skipped": [],
        "warnings": [],
        "fallback_used": False,
        "fallback_to_symbol": "",
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "entry_guard_reason": guard_reason,
    }
    if not selected_sym:
        plan["blocked_reason"] = "missing_selected_symbol"
        return plan
    if open_position_count >= max_positions:
        plan["blocked_reason"] = "max_positions_reached"
        return plan
    hard_blocked_reason = guard_reason if guard_reason in _HARD_BLOCK_CASCADE_REASONS else (
        reason if reason in _HARD_BLOCK_CASCADE_REASONS else ""
    )
    if hard_blocked_reason and not (bool(hard_block_override_enabled) and str(hard_block_override_reason or "").strip()):
        plan["blocked_reason"] = "hard_entry_blocker_no_cascade"
        plan["hard_blocked_reason"] = hard_blocked_reason
        return plan
    if hard_blocked_reason:
        plan["warnings"].append(
            {
                "reason": "hard_entry_blocker_override_used",
                "hard_blocked_reason": hard_blocked_reason,
                "override_reason": str(hard_block_override_reason or ""),
            }
        )
    if entry_guard_blocked:
        plan["blocked_reason"] = "entry_guard_blocked"
        return plan
    if entry_triggered:
        plan["blocked_reason"] = "top_pick_triggered"
        return plan
    if not bool(cascade_enabled) or max_runner_ups <= 0:
        plan["blocked_reason"] = "cascade_disabled_by_entry_control"
        return plan
    if reason in blocked_reasons:
        plan["blocked_reason"] = "reason_cascade_blocked_by_policy"
        return plan
    if reason not in allowed_reasons:
        plan["blocked_reason"] = "reason_not_cascade_eligible"
        return plan

    missing_quote_symbols = _quote_missing_symbols(scanner_output)
    excluded = {
        normalize_symbol(symbol)
        for symbol in list(excluded_symbols or [])
        if normalize_symbol(symbol)
    }
    selected_score = None
    for index, row in enumerate(list(ranked_candidates or []), start=1):
        if not isinstance(row, Mapping):
            continue
        if normalize_symbol(row.get("symbol") or "") == selected_sym:
            selected_score = _candidate_score(row)
            break
    if selected_score is not None:
        plan["top_pick_score"] = selected_score
    runner_rows: List[Mapping[str, Any]] = []
    for index, row in enumerate(list(ranked_candidates or []), start=1):
        if not isinstance(row, Mapping):
            continue
        symbol = normalize_symbol(row.get("symbol") or "")
        if not symbol or symbol == selected_sym:
            continue
        candidate_rank = _candidate_rank(row, index)
        if candidate_rank > max_priority_rank:
            plan["skipped"].append(
                {"symbol": symbol, "reason": "rank_above_cascade_limit", "rank": int(candidate_rank)}
            )
            continue
        candidate_score = _candidate_score(row)
        if q15_runner_up_gate_enabled and selected_score is not None and candidate_score is not None:
            score_gap = float(selected_score) - float(candidate_score)
            if score_gap > q15_score_gap_cap:
                plan["skipped"].append(
                    {
                        "symbol": symbol,
                        "reason": "q15_score_gap_above_runner_up_limit",
                        "rank": int(candidate_rank),
                        "top_pick_score": selected_score,
                        "candidate_score": candidate_score,
                        "score_gap": score_gap,
                        "max_score_gap": q15_score_gap_cap,
                    }
                )
                continue
        blocker = _candidate_blocker(row)
        if q15_runner_up_gate_enabled and blocker in _Q15_HIGH_RISK_RUNNER_BLOCKERS:
            plan["skipped"].append(
                {
                    "symbol": symbol,
                    "reason": "q15_runner_up_expected_blocker",
                    "rank": int(candidate_rank),
                    "expected_blocker": blocker,
                }
            )
            continue
        if symbol in excluded:
            plan["skipped"].append({"symbol": symbol, "reason": "excluded_same_symbol_or_pending_buy"})
            continue
        row_out = dict(row)
        if symbol in missing_quote_symbols:
            row_out["_quote_metrics_missing"] = True
            plan["warnings"].append(
                {"symbol": symbol, "reason": "quote_metrics_missing_monitor_fallback_allowed"}
            )
        runner_rows.append(row_out)
        if len(runner_rows) >= max_runner_ups:
            break

    plan["eligible"] = bool(runner_rows)
    plan["runner_up_symbols"] = [normalize_symbol(row.get("symbol") or "") for row in runner_rows]
    if not runner_rows:
        plan["blocked_reason"] = "no_runner_up_candidates"
        return plan

    plan["attempted"] = True
    plan["runner_rows"] = [dict(row) for row in runner_rows]
    return plan
