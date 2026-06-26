from __future__ import annotations

import re
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


def _numeric_drivers(value: Any, *, limit: int = 4) -> Dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    rows = []
    for key, raw in value.items():
        try:
            rows.append((str(key or ""), float(raw)))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: abs(item[1]), reverse=True)
    return {key: number for key, number in rows[:limit] if key}


def _candidate_score(candidate: Mapping[str, Any]) -> Any:
    value = candidate.get("score")
    return candidate.get("score_total") if value in (None, "") else value


def _selection_summary(
    *,
    symbol: str,
    candidate: Mapping[str, Any],
    original_selected: str,
) -> str:
    rank = candidate.get("rank")
    score = _candidate_score(candidate)
    bits = [f"executed symbol {symbol}"]
    if rank not in (None, ""):
        bits.append(f"scanner rank #{rank}")
    if score not in (None, ""):
        try:
            bits.append(f"score {float(score):.3f}")
        except (TypeError, ValueError):
            pass
    if original_selected and original_selected != symbol:
        bits.append(f"after scanner top pick {original_selected} was not executed")
    return "; ".join(bits)


def _different_number(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    try:
        return abs(float(left) - float(right)) > 1e-9
    except (TypeError, ValueError):
        return str(left) != str(right)


def _needs_reanchor(
    context: Mapping[str, Any],
    *,
    symbol: str,
    original_selected: str,
    candidate: Mapping[str, Any] | None,
) -> bool:
    scanner_selected = _text(context.get("scanner_selected_symbol"))
    if original_selected and original_selected != symbol:
        already_reanchored = bool(
            _text(context.get("selected_symbol")) == symbol
            and _text(context.get("executed_symbol")) == symbol
            and (
                not isinstance(context.get("selected_candidate"), Mapping)
                or _text((context.get("selected_candidate") or {}).get("symbol")) == symbol
            )
        )
        if not already_reanchored:
            return True
    if scanner_selected and scanner_selected != symbol:
        if not (
            _text(context.get("selected_symbol")) == symbol
            and _text(context.get("executed_symbol")) == symbol
        ):
            return True
    selection_text = " ".join(
        str(context.get(key) or "")
        for key in ("selection_reason", "summary")
    )
    for pattern in (
        r"(?:selected symbol|scanner selected)\s+([0-9A-Z]{6})",
        r"final selected symbol\s+([0-9A-Z]{6})",
    ):
        match = re.search(pattern, selection_text, flags=re.IGNORECASE)
        if match and _text(match.group(1)) != symbol:
            return True
    if not candidate:
        return False
    if (
        context.get("selected_rank") not in (None, "")
        and candidate.get("rank") not in (None, "")
        and str(context.get("selected_rank")) != str(candidate.get("rank"))
    ):
        return True
    score = _candidate_score(candidate)
    if _different_number(context.get("selected_score"), score):
        return True
    if _different_number(context.get("selected_score_total"), candidate.get("score_total")):
        return True
    if _different_number(context.get("confidence"), candidate.get("confidence")):
        return True
    return False


def _reanchor_selected_fields(
    target: Dict[str, Any],
    *,
    symbol: str,
    candidate: Mapping[str, Any] | None,
    original_selected: str,
) -> None:
    target["selected_symbol"] = symbol
    if not candidate:
        for key in (
            "selected_rank",
            "selected_score",
            "selected_score_total",
            "selected_status",
            "selected_sources",
            "source_scores",
            "score_breakdown",
            "selected_symbol_score_drivers",
            "confidence",
            "confidence_label",
            "scanner_chart_fit",
            "scanner_macro_chart_fit",
        ):
            target.pop(key, None)
        target["selection_reason"] = (
            f"executed symbol {symbol}; scanner candidate metrics unavailable"
        )
        return

    field_map = (
        ("selected_rank", "rank"),
        ("selected_status", "status"),
        ("selected_sources", "sources"),
        ("source_scores", "source_scores"),
        ("score_breakdown", "score_breakdown"),
        ("confidence", "confidence"),
        ("scanner_chart_fit", "scanner_chart_fit"),
        ("scanner_macro_chart_fit", "scanner_macro_chart_fit"),
    )
    for target_key, source_key in field_map:
        value = candidate.get(source_key)
        if value not in (None, "", [], {}):
            target[target_key] = value
        else:
            target.pop(target_key, None)

    score = _candidate_score(candidate)
    if score not in (None, ""):
        target["selected_score"] = score
        target["selected_score_total"] = candidate.get("score_total", score)
    else:
        target.pop("selected_score", None)
        target.pop("selected_score_total", None)

    breakdown = candidate.get("score_breakdown")
    target["selected_symbol_score_drivers"] = _numeric_drivers(breakdown)
    if target.get("confidence") not in (None, ""):
        try:
            confidence = float(target["confidence"])
            target["confidence_label"] = (
                "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
            )
        except (TypeError, ValueError):
            target.pop("confidence_label", None)
    target["executed_candidate_snapshot"] = dict(candidate)
    target["selected_candidate"] = dict(candidate)
    summary = _selection_summary(
        symbol=symbol,
        candidate=candidate,
        original_selected=original_selected,
    )
    target["selection_reason"] = summary
    target["summary"] = summary


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

    current_selected_candidate = (
        dict(out.get("selected_candidate"))
        if isinstance(out.get("selected_candidate"), Mapping)
        else {}
    )
    candidate_selected_symbol = _text(current_selected_candidate.get("symbol"))
    original_selected = _text(
        out.get("scanner_selected_symbol")
        or (
            candidate_selected_symbol
            if candidate_selected_symbol and candidate_selected_symbol != symbol
            else ""
        )
        or out.get("selected_symbol")
    )
    candidate = _candidate_from_context(out, symbol)
    if not _needs_reanchor(
        out,
        symbol=symbol,
        original_selected=original_selected,
        candidate=candidate,
    ):
        return out

    out["executed_symbol"] = symbol
    if original_selected and original_selected != symbol:
        out.setdefault("scanner_selected_symbol", original_selected)
        if current_selected_candidate:
            out.setdefault("scanner_selected_candidate", current_selected_candidate)
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
    _reanchor_selected_fields(
        out,
        symbol=symbol,
        candidate=candidate,
        original_selected=original_selected,
    )

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
        _reanchor_selected_fields(
            trace_out,
            symbol=symbol,
            candidate=candidate,
            original_selected=trace_original or original_selected,
        )
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
