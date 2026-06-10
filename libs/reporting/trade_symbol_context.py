from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _text(value: Any) -> str:
    return str(value or "").strip().upper()


def _find_candidate(rowset: Any, symbol: str) -> Optional[Dict[str, Any]]:
    if not isinstance(rowset, list) or not symbol:
        return None
    for row in rowset:
        if isinstance(row, Mapping) and _text(row.get("symbol")) == symbol:
            return dict(row)
    return None


def _candidate_from_context(scanner_context: Mapping[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    for key in (
        "ranked_candidates",
        "top_candidates",
        "runner_ups",
        "runner_ups_lost",
    ):
        found = _find_candidate(scanner_context.get(key), symbol)
        if found:
            return found

    trace = scanner_context.get("scanner_selection_trace")
    if isinstance(trace, Mapping):
        for key in ("ranked_candidates", "top_candidates", "runner_ups"):
            found = _find_candidate(trace.get(key), symbol)
            if found:
                return found
    return None


def normalize_scanner_context_for_executed_symbol(
    scanner_context: Mapping[str, Any] | None,
    *,
    executed_symbol: str,
) -> Dict[str, Any]:
    """Make scanner context explicit when the executed symbol differs from rank #1.

    Live runs can legitimately execute a runner-up after monitor/commander gates.
    Reports still need the actual trade symbol as the selected symbol, while
    preserving the original scanner top pick for audit.
    """

    out = dict(scanner_context or {})
    symbol = _text(executed_symbol)
    if not symbol:
        return out

    original_selected = _text(out.get("scanner_selected_symbol") or out.get("selected_symbol"))
    out["executed_symbol"] = symbol
    if original_selected and original_selected != symbol:
        out.setdefault("scanner_selected_symbol", original_selected)
        for key in ("rank", "score", "score_total", "status"):
            selected_key = f"selected_{key}"
            scanner_key = f"scanner_selected_{key}"
            if out.get(selected_key) not in (None, ""):
                out.setdefault(scanner_key, out.get(selected_key))
        out["selection_mismatch"] = {
            "status": "executed_symbol_differs_from_scanner_selected",
            "scanner_selected_symbol": original_selected,
            "executed_symbol": symbol,
            "reason": "runner_up_or_later_monitor_selection_executed",
        }
    out["selected_symbol"] = symbol

    candidate = _candidate_from_context(out, symbol)
    if candidate:
        for target_key, source_key in (
            ("selected_rank", "rank"),
            ("selected_score", "score"),
            ("selected_score_total", "score_total"),
            ("selected_status", "status"),
        ):
            if candidate.get(source_key) not in (None, ""):
                out[target_key] = candidate.get(source_key)
        out["executed_candidate_snapshot"] = candidate
    elif original_selected and original_selected != symbol:
        for key in ("selected_rank", "selected_score", "selected_score_total", "selected_status"):
            out.pop(key, None)

    trace = out.get("scanner_selection_trace")
    if isinstance(trace, Mapping):
        trace_out = dict(trace)
        trace_original = _text(trace_out.get("selected_symbol"))
        if trace_original and trace_original != symbol:
            trace_out.setdefault("scanner_selected_symbol", trace_original)
            for key in ("rank", "score", "score_total", "status"):
                selected_key = f"selected_{key}"
                scanner_key = f"scanner_selected_{key}"
                if trace_out.get(selected_key) not in (None, ""):
                    trace_out.setdefault(scanner_key, trace_out.get(selected_key))
        trace_out["executed_symbol"] = symbol
        trace_out["selected_symbol"] = symbol
        if candidate:
            trace_out["executed_candidate_snapshot"] = candidate
        elif trace_original and trace_original != symbol:
            for key in ("selected_rank", "selected_score", "selected_score_total", "selected_status"):
                trace_out.pop(key, None)
        out["scanner_selection_trace"] = trace_out

    return out


def normalize_trade_payload_symbol_context(
    payload: Mapping[str, Any] | None,
    *,
    executed_symbol: str,
) -> Dict[str, Any]:
    out = dict(payload or {})
    symbol = _text(executed_symbol)
    if not symbol:
        return out
    out["symbol"] = symbol
    scanner_context = out.get("scanner_context")
    if isinstance(scanner_context, Mapping):
        out["scanner_context"] = normalize_scanner_context_for_executed_symbol(
            scanner_context,
            executed_symbol=symbol,
        )
    return out
