from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from libs.core.symbols import normalize_symbol

_CASCADE_ELIGIBLE_REASONS = {
    "too_extended_from_vwap",
    "breakout_not_ready",
    "volume_insufficient",
    "volume_confirmation_missing",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
    "pullback_not_mature",
}

_DEFAULT_MAX_PRIORITY_RANK = 10


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
    excluded_symbols: Sequence[Any] | None = None,
) -> Dict[str, Any]:
    selected_sym = normalize_symbol(selected_symbol)
    reason = str(entry_reason or "").strip()
    guard_reason = str(entry_guard_reason or "").strip()
    duplicate_symbol_guard = guard_reason in {"same_symbol_position_open", "same_symbol_pending_buy"}
    max_positions = max(1, int(max_positions or 1))
    max_runner_ups = max(0, int(max_runner_ups))
    if not bool(cascade_enabled):
        max_runner_ups = 0
    max_priority_rank = max(1, int(max_runner_ups) + 1)
    allowed_reasons = _normalize_reason_set(cascade_allowed_reasons) or set(_CASCADE_ELIGIBLE_REASONS)
    blocked_reasons = _normalize_reason_set(cascade_blocked_reasons)
    plan: Dict[str, Any] = {
        "attempted": False,
        "eligible": False,
        "reason": reason,
        "top_pick_symbol": selected_sym,
        "max_priority_rank": int(max_priority_rank),
        "max_runner_ups": int(max_runner_ups),
        "cascade_enabled": bool(cascade_enabled and max_runner_ups > 0),
        "cascade_allowed_reasons": sorted(allowed_reasons),
        "cascade_blocked_reasons": sorted(blocked_reasons),
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
    if entry_guard_blocked:
        if not duplicate_symbol_guard:
            plan["blocked_reason"] = "entry_guard_blocked"
            return plan
    if entry_triggered and not duplicate_symbol_guard:
        plan["blocked_reason"] = "top_pick_triggered"
        return plan
    if not bool(cascade_enabled) or max_runner_ups <= 0:
        plan["blocked_reason"] = "cascade_disabled_by_entry_control"
        return plan
    if reason in blocked_reasons and not duplicate_symbol_guard:
        plan["blocked_reason"] = "reason_cascade_blocked_by_policy"
        return plan
    if reason not in allowed_reasons and not duplicate_symbol_guard:
        plan["blocked_reason"] = "reason_not_cascade_eligible"
        return plan

    missing_quote_symbols = _quote_missing_symbols(scanner_output)
    excluded = {
        normalize_symbol(symbol)
        for symbol in list(excluded_symbols or [])
        if normalize_symbol(symbol)
    }
    runner_rows: List[Mapping[str, Any]] = []
    for row in list(ranked_candidates or []):
        if not isinstance(row, Mapping):
            continue
        symbol = normalize_symbol(row.get("symbol") or "")
        if not symbol or symbol == selected_sym:
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
