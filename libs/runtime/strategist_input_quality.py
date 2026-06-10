from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.runtime.quant.market_regime_observation import classify_market_regime_rail


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value or []) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _headline_count_from_sample_map(value: Any) -> int:
    total = 0
    for row in _dict(value).values():
        if not isinstance(row, Mapping):
            continue
        total += _safe_int(row.get("count"))
    return total


def build_market_regime_rail_context(payload: Mapping[str, Any]) -> Dict[str, Any]:
    global_signal = _dict(payload.get("global_sentiment_signal"))
    packet = {
        "generated_at": _text(payload.get("generated_at") or payload.get("saved_at")),
        "global_sentiment": {
            "score": global_signal.get("score"),
            "status": global_signal.get("status"),
            "source": global_signal.get("source"),
        },
        "index_moves": _dict(global_signal.get("index_moves")),
        "korea_indices": _dict(global_signal.get("korea_indices")),
        "macro_moves": _dict(global_signal.get("macro_moves")),
    }
    return classify_market_regime_rail(packet)


def build_news_quality_context(payload: Mapping[str, Any]) -> Dict[str, Any]:
    news_context = _dict(payload.get("news_context"))
    query_targets = [_text(x) for x in _list(payload.get("news_query_targets")) if _text(x)]
    candidate_signal_map = _dict(payload.get("news_sentiment_signal"))
    market_signal_map = _dict(payload.get("market_news_sentiment_signal"))
    candidate_count = (
        _safe_int(news_context.get("candidate_headline_count"))
        or _headline_count_from_sample_map(payload.get("candidate_news_sample"))
    )
    market_count = (
        _safe_int(news_context.get("market_headline_count"))
        or _headline_count_from_sample_map(payload.get("market_news_sample"))
    )
    total = _safe_int(news_context.get("headline_count")) or candidate_count + market_count
    avg_score = _safe_float(news_context.get("avg_score"))
    candidate_signal_count = _safe_int(news_context.get("candidate_signal_total")) or len(candidate_signal_map)
    market_signal_count = _safe_int(news_context.get("market_signal_total")) or len(market_signal_map)

    issues: list[str] = []
    if total <= 0:
        issues.append("headline_count_zero")
    if candidate_count <= 0:
        issues.append("candidate_news_missing")
    if market_count <= 0:
        issues.append("market_news_missing")
    if not query_targets:
        issues.append("query_targets_missing")
    if candidate_signal_count <= 0:
        issues.append("candidate_sentiment_missing")
    if market_signal_count <= 0:
        issues.append("market_sentiment_missing")

    if not issues:
        status = "ok"
    elif total > 0 and query_targets:
        status = "partial"
    else:
        status = "weak"

    return {
        "schema_version": "strategist.news_quality_context.v1",
        "status": status,
        "headline_count": total,
        "candidate_headline_count": candidate_count,
        "market_headline_count": market_count,
        "query_target_count": len(query_targets),
        "candidate_signal_count": candidate_signal_count,
        "market_signal_count": market_signal_count,
        "avg_score": round(avg_score, 4),
        "issues": issues,
        "selected_symbol_requires_news_support": status != "ok",
        "usage_rule": (
            "news_may_support_relaxation_only_with_chart_volume_cost_confirmation"
            if status == "ok"
            else "do_not_relax_on_news_without_fresh_symbol_specific_evidence"
        ),
    }


def build_risk_off_exception_policy(
    *,
    market_regime_rail: Mapping[str, Any],
    news_quality: Mapping[str, Any],
) -> Dict[str, Any]:
    regime = _text(market_regime_rail.get("market_regime"))
    rail = _text(market_regime_rail.get("market_regime_rail"))
    news_status = _text(news_quality.get("status"))
    risk_off = bool(
        regime == "risk_off"
        or rail.startswith("risk_off")
        or rail.startswith("global_risk_off")
        or rail in {"krx_night_futures_gap_down", "risk_off_breadth_collapse"}
        or "gap_down" in rail
        or "breadth_collapse" in rail
    )
    return {
        "schema_version": "strategist.risk_off_exception_policy.v1",
        "risk_off_active": bool(risk_off),
        "market_regime": regime,
        "market_regime_rail": rail,
        "news_quality_status": news_status,
        "allowed_exception_conditions": [
            "opening_momentum_probe_with_small_size",
            "cost_floor_pass",
            "relative_strength_leader",
            "volume_confirmation",
            "vwap_or_opening_range_reclaim",
            "fresh_symbol_news_not_negative",
        ]
        if risk_off
        else [],
        "disallowed_conditions": [
            "gap_chase_without_pullback",
            "below_vwap_without_reclaim",
            "cost_edge_not_met",
            "dead_volume",
            "news_quality_weak_or_missing",
        ]
        if risk_off
        else ["cost_edge_not_met", "dead_volume"],
        "instruction": (
            "In risk-off rails, relaxation is allowed only when all exception conditions are explicitly satisfied; otherwise keep defensive or no-trade stance."
            if risk_off
            else "No risk-off exception required; still keep cost, volume, and chart gates explicit."
        ),
    }


def build_strategist_input_quality_context(payload: Mapping[str, Any]) -> Dict[str, Any]:
    rail = build_market_regime_rail_context(payload)
    news = build_news_quality_context(payload)
    exceptions = build_risk_off_exception_policy(market_regime_rail=rail, news_quality=news)
    return {
        "schema_version": "strategist.input_quality_context.v1",
        "market_regime_rail": rail,
        "news_quality": news,
        "risk_off_exception_policy": exceptions,
    }


__all__ = [
    "build_market_regime_rail_context",
    "build_news_quality_context",
    "build_risk_off_exception_policy",
    "build_strategist_input_quality_context",
]
