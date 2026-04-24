from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from libs.core.symbols import normalize_symbol

_CASCADE_ELIGIBLE_REASONS = {
    "too_extended_from_vwap",
    "breakout_not_ready",
    "volume_insufficient",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
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
    entry_guard_blocked: bool,
    entry_triggered: bool,
    entry_reason: str,
    max_runner_ups: int = 2,
) -> Dict[str, Any]:
    selected_sym = normalize_symbol(selected_symbol)
    reason = str(entry_reason or "").strip()
    plan: Dict[str, Any] = {
        "attempted": False,
        "eligible": False,
        "reason": reason,
        "top_pick_symbol": selected_sym,
        "runner_up_symbols": [],
        "skipped": [],
        "warnings": [],
        "fallback_used": False,
        "fallback_to_symbol": "",
    }
    if not selected_sym:
        plan["blocked_reason"] = "missing_selected_symbol"
        return plan
    if open_position_count > 0:
        plan["blocked_reason"] = "open_position_present"
        return plan
    if entry_guard_blocked:
        plan["blocked_reason"] = "entry_guard_blocked"
        return plan
    if entry_triggered:
        plan["blocked_reason"] = "top_pick_triggered"
        return plan
    if reason not in _CASCADE_ELIGIBLE_REASONS:
        plan["blocked_reason"] = "reason_not_cascade_eligible"
        return plan

    missing_quote_symbols = _quote_missing_symbols(scanner_output)
    runner_rows: List[Mapping[str, Any]] = []
    for row in list(ranked_candidates or []):
        if not isinstance(row, Mapping):
            continue
        symbol = normalize_symbol(row.get("symbol") or "")
        if not symbol or symbol == selected_sym:
            continue
        row_out = dict(row)
        if symbol in missing_quote_symbols:
            row_out["_quote_metrics_missing"] = True
            plan["warnings"].append(
                {"symbol": symbol, "reason": "quote_metrics_missing_monitor_fallback_allowed"}
            )
        runner_rows.append(row_out)
        if len(runner_rows) >= max(0, int(max_runner_ups)):
            break

    plan["eligible"] = bool(runner_rows)
    plan["runner_up_symbols"] = [normalize_symbol(row.get("symbol") or "") for row in runner_rows]
    if not runner_rows:
        plan["blocked_reason"] = "no_runner_up_candidates"
        return plan

    plan["attempted"] = True
    plan["runner_rows"] = [dict(row) for row in runner_rows]
    return plan
