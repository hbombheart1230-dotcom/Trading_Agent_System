from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple


def _clip(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _humanize_reason(value: Any) -> str:
    text = _clip(value, max_len=120)
    if not text:
        return ""
    return text.replace("_", " ")


def _top_numeric_drivers(score_breakdown: Mapping[str, Any] | None, *, limit: int = 4) -> Dict[str, float]:
    items: List[Tuple[str, float]] = []
    for key, raw in dict(score_breakdown or {}).items():
        try:
            items.append((str(key or ""), float(raw)))
        except Exception:
            continue
    items.sort(key=lambda item: abs(item[1]), reverse=True)
    out: Dict[str, float] = {}
    for key, value in items:
        if not key:
            continue
        out[key] = value
        if len(out) >= limit:
            break
    return out


def _candidate_rows(
    scanner_reason: Mapping[str, Any] | None,
    scanner_selection_trace: Mapping[str, Any] | None,
    scanner_artifact: Mapping[str, Any] | None,
    monitor_artifact: Mapping[str, Any] | None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def _append(candidate_rows: Any) -> None:
        for row in list(candidate_rows or []):
            if isinstance(row, dict):
                rows.append(dict(row))

    reason = dict(scanner_reason or {})
    trace = dict(scanner_selection_trace or {})
    scanner = dict(scanner_artifact or {})
    monitor = dict(monitor_artifact or {})
    handoff = monitor.get("scanner_monitor_handoff") if isinstance(monitor.get("scanner_monitor_handoff"), dict) else {}
    cascade = handoff.get("entry_candidate_cascade") if isinstance(handoff.get("entry_candidate_cascade"), dict) else {}

    _append(reason.get("top_candidates"))
    _append(reason.get("runner_ups"))
    _append(trace.get("ranked_candidates"))
    _append(handoff.get("scanner_top_candidates"))
    _append(cascade.get("runner_rows"))
    _append(scanner.get("ranking_table"))
    ranking_table = scanner.get("candidate_ranking_table") if isinstance(scanner.get("candidate_ranking_table"), dict) else {}
    _append(ranking_table.get("rows"))

    deduped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        existing = deduped.get(symbol)
        if not existing:
            deduped[symbol] = dict(row)
            continue
        merged = dict(existing)
        for key, value in row.items():
            if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                merged[key] = value
        deduped[symbol] = merged
    return list(deduped.values())


def _find_candidate_row(rows: List[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    for row in rows:
        if str(row.get("symbol") or "").strip() == symbol:
            return dict(row)
    return {}


def _filter_symbol_rows(rows: Any, symbol: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    target = str(symbol or "").strip()
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        if target and str(row.get("symbol") or "").strip() == target:
            continue
        out.append(dict(row))
    return out


def _prepend_unique(items: List[str], row: str) -> List[str]:
    text = _clip(row, max_len=220)
    if not text:
        return items
    existing = [str(item or "").strip() for item in items if str(item or "").strip()]
    if text in existing:
        return existing
    return [text] + existing


def reanchor_scanner_selection_for_monitor_fallback(
    *,
    scanner_reason_human: Mapping[str, Any] | None,
    scanner_selection_trace: Mapping[str, Any] | None,
    scanner_artifact: Mapping[str, Any] | None,
    monitor_artifact: Mapping[str, Any] | None,
    trade_symbol: str,
) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    reason = dict(scanner_reason_human or {})
    trace = dict(scanner_selection_trace or {})
    scanner = dict(scanner_artifact or {})
    monitor = dict(monitor_artifact or {})
    symbol = str(trade_symbol or "").strip()
    handoff = monitor.get("scanner_monitor_handoff") if isinstance(monitor.get("scanner_monitor_handoff"), dict) else {}
    cascade = handoff.get("entry_candidate_cascade") if isinstance(handoff.get("entry_candidate_cascade"), dict) else {}

    scanner_top_pick = str(
        handoff.get("scanner_selected_symbol")
        or reason.get("selected_symbol")
        or scanner.get("selected_symbol")
        or scanner.get("top_stock")
        or ""
    ).strip()
    monitor_selected_symbol = str(
        handoff.get("monitor_selected_symbol")
        or cascade.get("fallback_to_symbol")
        or ""
    ).strip()
    fallback_used = bool(cascade.get("fallback_used"))

    if (
        not symbol
        or not fallback_used
        or not monitor_selected_symbol
        or symbol != monitor_selected_symbol
        or not scanner_top_pick
        or symbol == scanner_top_pick
    ):
        effective = str(reason.get("selected_symbol") or symbol or "").strip()
        return reason, trace, effective

    rows = _candidate_rows(reason, trace, scanner, monitor)
    selected_row = _find_candidate_row(rows, symbol)
    selected_rank = _safe_int(selected_row.get("rank"), _safe_int(reason.get("selected_rank"), 0))
    selected_score = selected_row.get("score_total")
    selected_confidence = selected_row.get("confidence")
    selected_risk = selected_row.get("risk_score")
    selected_score_breakdown = (
        selected_row.get("score_breakdown")
        if isinstance(selected_row.get("score_breakdown"), dict)
        else {}
    )
    rejection_reason = _humanize_reason(
        handoff.get("monitor_rejection_reason_summary")
        or handoff.get("monitor_rejection_reason_code")
        or cascade.get("reason")
    )
    fallback_trace = [dict(row) for row in list(cascade.get("fallback_trace") or []) if isinstance(row, dict)]
    fallback_trigger_reason = _humanize_reason(
        next(
            (
                row.get("reason")
                for row in fallback_trace
                if bool(row.get("triggered")) and str(row.get("symbol") or "").strip() == symbol
            ),
            "",
        )
    )

    summary = (
        f"Scanner top pick {scanner_top_pick} was blocked at monitor stage"
        + (f" for {rejection_reason}" if rejection_reason else "")
        + f", so runner-up re-evaluation selected {symbol}"
        + (f" as scanner rank #{selected_rank}" if selected_rank > 0 else "")
        + (
            f" with score {_safe_float(selected_score, 0.0):.3f}"
            if selected_score not in (None, "")
            else ""
        )
        + "."
    )
    comparison = (
        f"Actual traded symbol was {symbol} after monitor fallback from scanner top pick {scanner_top_pick}."
    )
    if fallback_trigger_reason:
        comparison += f" Entry trigger confirmed on {fallback_trigger_reason}."

    reason["selected_symbol"] = symbol
    if selected_rank > 0:
        reason["selected_rank"] = selected_rank
    if selected_score not in (None, ""):
        reason["selected_score"] = selected_score
    if selected_confidence not in (None, ""):
        reason["confidence"] = selected_confidence
    if selected_risk not in (None, ""):
        reason["selected_risk"] = selected_risk
    if selected_score_breakdown:
        reason["score_breakdown"] = dict(selected_score_breakdown)
    reason["monitor_fallback_used"] = True
    reason["selection_path"] = "monitor_fallback_from_scanner_top_pick"
    reason["scanner_top_pick_symbol"] = scanner_top_pick
    reason["scanner_top_pick_rank"] = _safe_int(handoff.get("scanner_rank"), 1)
    reason["monitor_selected_symbol"] = symbol
    reason["monitor_fallback_reason"] = rejection_reason
    reason["monitor_trigger_reason"] = fallback_trigger_reason
    reason["summary"] = summary
    reason["comparison"] = comparison
    reason["selected_symbol_score_drivers"] = _top_numeric_drivers(selected_score_breakdown, limit=4)
    if reason.get("runner_ups"):
        reason["runner_ups"] = _filter_symbol_rows(reason.get("runner_ups"), symbol)
    if reason.get("runner_ups_lost"):
        reason["runner_ups_lost"] = _filter_symbol_rows(reason.get("runner_ups_lost"), symbol)

    bullets = [str(item or "").strip() for item in list(reason.get("bullets") or []) if str(item or "").strip()]
    bullets = _prepend_unique(bullets, f"Monitor fallback selected {symbol} after scanner top pick {scanner_top_pick} was blocked.")
    if rejection_reason:
        bullets = _prepend_unique(bullets, f"Top-pick rejection reason: {rejection_reason}.")
    if fallback_trigger_reason:
        bullets = _prepend_unique(bullets, f"Fallback entry trigger: {fallback_trigger_reason}.")
    if selected_rank > 0 or selected_score not in (None, ""):
        metric_bits: List[str] = []
        if selected_rank > 0:
            metric_bits.append(f"scanner rank #{selected_rank}")
        if selected_score not in (None, ""):
            metric_bits.append(f"score {_safe_float(selected_score, 0.0):.3f}")
        if selected_confidence not in (None, ""):
            metric_bits.append(f"confidence {_safe_float(selected_confidence, 0.0):.3f}")
        if selected_risk not in (None, ""):
            metric_bits.append(f"risk {_safe_float(selected_risk, 0.0):.3f}")
        bullets = _prepend_unique(bullets, f"Actual traded symbol {symbol} had {'; '.join(metric_bits)}.")
    reason["bullets"] = bullets[:14]

    trace["selected_symbol"] = symbol
    if selected_rank > 0:
        trace["selected_rank"] = selected_rank
    trace["selection_reason"] = summary
    if selected_score_breakdown:
        trace["selected_symbol_score_drivers"] = _top_numeric_drivers(selected_score_breakdown, limit=4)
    trace["monitor_fallback_used"] = True
    trace["selection_path"] = "monitor_fallback_from_scanner_top_pick"
    trace["scanner_top_pick_symbol"] = scanner_top_pick
    trace["monitor_selected_symbol"] = symbol
    trace["monitor_fallback_reason"] = rejection_reason
    trace["monitor_trigger_reason"] = fallback_trigger_reason

    return reason, trace, symbol
