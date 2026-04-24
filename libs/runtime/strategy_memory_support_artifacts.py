from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def row_metrics_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(row.get("support_metrics"))


def row_reporter_analysis_payload(row: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(row.get("support_reporter_analysis"))


def resolve_report_focus_targets(row: Mapping[str, Any]) -> list[str]:
    reporter = row_reporter_analysis_payload(row)
    if reporter:
        return [str(x or "").strip() for x in list(reporter.get("report_focus_targets") or []) if str(x or "").strip()][:6]
    digest = _mapping(row.get("reporter_analysis_digest"))
    return [str(x or "").strip() for x in list(digest.get("report_focus_targets") or []) if str(x or "").strip()][:6]


def resolve_system_health(row: Mapping[str, Any]) -> str:
    reporter = row_reporter_analysis_payload(row)
    operator = _mapping(reporter.get("operator_facing_summary"))
    direct = _text(operator.get("system_health") or reporter.get("system_health"))
    if direct:
        return direct
    digest = _mapping(row.get("reporter_analysis_digest"))
    return _text(digest.get("system_health"))


def resolve_scanner_status(row: Mapping[str, Any]) -> str:
    reporter = row_reporter_analysis_payload(row)
    scanner_eval = _mapping(reporter.get("scanner_evaluation"))
    direct = _text(scanner_eval.get("scanner_selection_status"))
    if direct:
        return direct
    digest = _mapping(row.get("reporter_analysis_digest"))
    return _text(digest.get("scanner_selection_status"))


def resolve_monitor_status(row: Mapping[str, Any]) -> str:
    reporter = row_reporter_analysis_payload(row)
    monitor_eval = _mapping(reporter.get("monitor_evaluation"))
    direct = _text(monitor_eval.get("monitor_status"))
    if direct:
        return direct
    digest = _mapping(row.get("reporter_analysis_digest"))
    return _text(digest.get("monitor_status"))


def resolve_route_context(row: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = row_metrics_payload(row)
    if metrics:
        return {
            "route_source": _text(metrics.get("route_source")),
            "route_selected_total": _mapping(metrics.get("route_selected_total")),
            "strategist_mode_total": _mapping(metrics.get("strategist_mode_total")),
            "alignment_totals": _mapping(metrics.get("scanner_monitor_alignment_total")),
        }
    digest = _mapping(row.get("reporter_analysis_digest"))
    route_mix = _mapping(digest.get("route_mix"))
    return {
        "route_source": _text(route_mix.get("route_source")),
        "route_selected_total": _mapping(route_mix.get("route_selected_total")),
        "strategist_mode_total": {},
        "alignment_totals": {},
    }


def resolve_monitor_reason_totals(row: Mapping[str, Any]) -> Dict[str, int]:
    metrics = row_metrics_payload(row)
    totals: Dict[str, int] = {}
    for key, value in _mapping(metrics.get("no_trade_reason_total")).items():
        name = _text(key)
        if name:
            totals[name] = totals.get(name, 0) + _safe_int(value, 0)
    reporter = row_reporter_analysis_payload(row)
    monitor_eval = _mapping(reporter.get("monitor_evaluation"))
    for key, value in _mapping(monitor_eval.get("monitor_reason_top")).items():
        name = _text(key)
        if name:
            totals[name] = max(totals.get(name, 0), _safe_int(value, 0))
    if totals:
        return totals
    digest = _mapping(row.get("reporter_analysis_digest"))
    return {str(x): 1 for x in list(digest.get("top_monitor_reasons") or []) if _text(x)}


def resolve_supervisor_blocker_totals(row: Mapping[str, Any]) -> Dict[str, int]:
    metrics = row_metrics_payload(row)
    totals: Dict[str, int] = {}
    for key, value in _mapping(metrics.get("intents_blocked_by_reason")).items():
        name = _text(key)
        if name:
            totals[name] = totals.get(name, 0) + _safe_int(value, 0)
    reporter = row_reporter_analysis_payload(row)
    supervisor = _mapping(reporter.get("supervisor_activity"))
    for key, value in _mapping(supervisor.get("blocked_reason_top")).items():
        name = _text(key)
        if name:
            totals[name] = max(totals.get(name, 0), _safe_int(value, 0))
    if totals:
        return totals
    digest = _mapping(row.get("reporter_analysis_digest"))
    return {str(x): 1 for x in list(digest.get("top_supervisor_blockers") or []) if _text(x)}


def resolve_regime_observation_counts(row: Mapping[str, Any]) -> Dict[str, int]:
    reporter = row_reporter_analysis_payload(row)
    chains = list(_mapping(reporter.get("decision_chains")).get("chains") or [])
    counts: Dict[str, int] = {}
    for item in chains:
        if not isinstance(item, Mapping):
            continue
        frame = _mapping(item.get("strategist_frame"))
        regime = _text(frame.get("market_regime"))
        if not regime:
            continue
        counts[regime] = counts.get(regime, 0) + 1
    return counts


def resolve_top_scanner_sources(row: Mapping[str, Any]) -> list[str]:
    digest = _mapping(row.get("reporter_analysis_digest"))
    sources = [str(x or "").strip() for x in list(digest.get("top_scanner_sources") or []) if str(x or "").strip()]
    if sources:
        return sources[:6]
    reporter = row_reporter_analysis_payload(row)
    strategy_effectiveness = _mapping(reporter.get("strategy_effectiveness"))
    scanner_priority_counts = _mapping(strategy_effectiveness.get("scanner_priority_counts"))
    ordered = sorted(scanner_priority_counts.items(), key=lambda item: (-_safe_int(item[1], 0), str(item[0])))
    return [str(name) for name, _count in ordered[:4]]


def resolve_candidate_source_totals(row: Mapping[str, Any]) -> Dict[str, int]:
    reporter = row_reporter_analysis_payload(row)
    scanner_eval = _mapping(reporter.get("scanner_evaluation"))
    totals = {
        _text(name): _safe_int(count, 0)
        for name, count in _mapping(scanner_eval.get("candidate_source_top")).items()
        if _text(name)
    }
    return {name: count for name, count in totals.items() if count > 0}


def resolve_scanner_evaluation_context(row: Mapping[str, Any]) -> Dict[str, Any]:
    reporter = row_reporter_analysis_payload(row)
    scanner_eval = _mapping(reporter.get("scanner_evaluation"))
    return {
        "selection_status": _text(scanner_eval.get("selection_status")),
        "avg_top_score": _safe_float(scanner_eval.get("avg_top_score")),
        "avg_candidate_pool_after_filter": _safe_float(scanner_eval.get("avg_candidate_pool_after_filter")),
        "scanner_summary_total": _safe_int(scanner_eval.get("scanner_summary_total")),
        "selected_symbol_top": _mapping(scanner_eval.get("selected_symbol_top")),
    }


def average_route_ratio(rows: Iterable[Mapping[str, Any]], key: str) -> float:
    total = 0.0
    count = 0
    for row in rows:
        route_context = resolve_route_context(row)
        route_selected_total = _mapping(route_context.get("route_selected_total"))
        route_total = sum(_safe_int(v, 0) for v in route_selected_total.values())
        if route_total <= 0:
            continue
        total += float(_safe_int(route_selected_total.get(key), 0)) / float(route_total)
        count += 1
    if count <= 0:
        return 0.0
    return round(total / float(count), 4)
