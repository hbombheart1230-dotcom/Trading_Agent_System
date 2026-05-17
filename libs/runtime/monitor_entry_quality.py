from __future__ import annotations

import os
from typing import Any, Dict, List


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _config_float(config: Dict[str, Any], key: str, env_key: str, default: float) -> float:
    if config.get(key) not in (None, ""):
        return _to_float(config.get(key), default)
    raw = os.getenv(env_key)
    if raw not in (None, ""):
        return _to_float(raw, default)
    return float(default)


def entry_candidate_sources(row: Dict[str, Any]) -> set[str]:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    raw_sources: List[Any] = []
    for value in (
        candidate.get("sources"),
        row.get("sources"),
        row.get("selected_sources"),
    ):
        if isinstance(value, (list, tuple, set)):
            raw_sources.extend(list(value))
        elif value not in (None, ""):
            raw_sources.extend(str(value).replace("+", ",").split(","))
    return {str(item or "").strip().lower() for item in raw_sources if str(item or "").strip()}


def entry_candidate_source_scores(row: Dict[str, Any]) -> Dict[str, Any]:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    for value in (row.get("source_scores"), candidate.get("source_scores")):
        if isinstance(value, dict):
            return dict(value)
    return {}


def entry_candidate_score_breakdown(row: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(row.get("score_breakdown"), dict):
        return dict(row.get("score_breakdown") or {})
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    if isinstance(candidate.get("score_breakdown"), dict):
        return dict(candidate.get("score_breakdown") or {})
    return {}


def entry_candidate_chart_fit_score(row: Dict[str, Any]) -> float:
    for key in ("scanner_chart_fit_score", "scanner_macro_chart_fit_score", "entry_compatibility_score"):
        value = _to_float(row.get(key))
        if value > 0.0:
            return value
    for key in ("scanner_chart_fit", "scanner_macro_chart_fit"):
        nested = row.get(key) if isinstance(row.get(key), dict) else {}
        value = _to_float(nested.get("score"))
        if value > 0.0:
            return value
    return 0.0


def entry_candidate_chart_fit_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("scanner_chart_fit_score", "scanner_macro_chart_fit_score", "entry_compatibility_score"):
        if row.get(key) not in (None, ""):
            return {"available": True, "score": _to_float(row.get(key)), "source": key}
    for key in ("scanner_chart_fit", "scanner_macro_chart_fit"):
        nested = row.get(key) if isinstance(row.get(key), dict) else {}
        if nested.get("score") not in (None, ""):
            return {"available": True, "score": _to_float(nested.get("score")), "source": f"{key}.score"}
    return {"available": False, "score": 0.0, "source": ""}


def selected_rank_from_candidate(row: Dict[str, Any]) -> int:
    for key in ("rank", "priority_rank", "scanner_rank", "selected_rank"):
        rank = _to_int(row.get(key))
        if rank > 0:
            return int(rank)
    return 0


def evaluate_entry_quality_gate(
    *,
    selected: Dict[str, Any],
    entry_info: Dict[str, Any],
    entry_cost_filter: Dict[str, Any],
) -> Dict[str, Any]:
    selected_rank = selected_rank_from_candidate(selected)
    chart_fit = entry_candidate_chart_fit_snapshot(selected)
    chart_fit_available = bool(chart_fit.get("available"))
    chart_fit_score = _to_float(chart_fit.get("score"))
    cost_filter_enabled = bool(entry_cost_filter.get("enabled"))
    cost_filter_passed = bool(entry_cost_filter.get("passed"))
    edge_evidence_type = str(entry_cost_filter.get("edge_evidence_type") or "").strip()
    estimated_gross_edge_available = entry_cost_filter.get("estimated_gross_edge_pct") not in (None, "")
    directional_edge_available = bool(entry_cost_filter.get("directional_edge_available")) or edge_evidence_type == "directional"
    fail_reasons = list(entry_cost_filter.get("fail_reasons") or [])
    reasons: List[str] = []

    hard_min_chart_fit = _config_float({}, "unused", "MONITOR_ENTRY_HARD_MIN_CHART_FIT", 0.35)
    runner_min_chart_fit = _config_float({}, "unused", "MONITOR_ENTRY_RUNNER_MIN_CHART_FIT", 0.55)
    runner_rank_floor = _to_int(os.getenv("MONITOR_ENTRY_RUNNER_RANK_FLOOR", "4") or 4)
    if runner_rank_floor <= 0:
        runner_rank_floor = 4
    runner_up = bool(selected_rank >= runner_rank_floor > 0)

    if chart_fit_available and chart_fit_score < hard_min_chart_fit:
        reasons.append("chart_fit_below_hard_floor")
    if runner_up:
        if chart_fit_available and chart_fit_score < runner_min_chart_fit:
            reasons.append("runner_up_chart_fit_below_min")
        if cost_filter_enabled and not cost_filter_passed:
            reasons.append("runner_up_cost_filter_not_passed")
        if cost_filter_enabled and not (directional_edge_available or estimated_gross_edge_available):
            reasons.append("runner_up_edge_evidence_missing")

    blocked = bool(bool(entry_info.get("triggered")) and reasons)
    reason = ""
    if blocked:
        if "chart_fit_below_hard_floor" in reasons:
            reason = "entry_chart_fit_too_low"
        elif "runner_up_chart_fit_below_min" in reasons:
            reason = "runner_up_chart_fit_not_enough"
        elif "runner_up_cost_filter_not_passed" in reasons:
            reason = "runner_up_cost_edge_not_ready"
        else:
            reason = "runner_up_edge_evidence_missing"

    return {
        "schema_version": "entry_quality_gate.v1",
        "enabled": True,
        "blocked": bool(blocked),
        "reason": reason,
        "reasons": reasons,
        "selected_rank": int(selected_rank),
        "runner_up": bool(runner_up),
        "runner_rank_floor": int(runner_rank_floor),
        "chart_fit_available": bool(chart_fit_available),
        "chart_fit_score": float(chart_fit_score),
        "chart_fit_source": str(chart_fit.get("source") or ""),
        "hard_min_chart_fit": float(hard_min_chart_fit),
        "runner_min_chart_fit": float(runner_min_chart_fit),
        "cost_filter_enabled": bool(cost_filter_enabled),
        "cost_filter_passed": bool(cost_filter_passed),
        "cost_filter_fail_reasons": fail_reasons,
        "directional_edge_available": bool(directional_edge_available),
        "estimated_gross_edge_available": bool(estimated_gross_edge_available),
        "edge_evidence_type": edge_evidence_type,
    }


def classify_vwap_reclaim_pullback_candidate(
    *,
    candidate_row: Dict[str, Any],
    selected_rank: int,
    fallback_used: bool,
    entry_info: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Classify pullback evidence without symbol-specific penalties."""
    row = dict(candidate_row or {})
    score_breakdown = entry_candidate_score_breakdown(row)
    source_scores = entry_candidate_source_scores(row)
    sources = entry_candidate_sources(row)
    entry = dict(entry_info or {})
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    grouped = entry.get("grouped_logic_trace") if isinstance(entry.get("grouped_logic_trace"), dict) else {}
    condition_scores = entry.get("condition_scores") if isinstance(entry.get("condition_scores"), dict) else {}

    theme_boost = max(0.0, _to_float(score_breakdown.get("theme_boost")))
    raw_theme_match = row.get("theme_match")
    theme_match = (
        bool(raw_theme_match)
        if isinstance(raw_theme_match, bool)
        else _is_trueish(raw_theme_match)
    ) or "sector_theme" in sources or theme_boost > 0.0
    trading_value = max(0.0, _to_float(score_breakdown.get("trading_value")))
    if trading_value <= 0.0 and source_scores.get("top_value") not in (None, ""):
        trading_value = max(0.0, min(1.0, _to_float(source_scores.get("top_value")) / 2.0))
    top_value_confirmed = "top_value" in sources or trading_value >= 0.20
    top_volume_confirmed = "top_volume" in sources or _to_float(source_scores.get("top_volume")) > 0.0 or max(
        _to_float(score_breakdown.get("volume_surge")),
        _to_float(metrics.get("volume_ratio")) / 2.0,
    ) >= 0.20
    volume_confirmation = bool(
        metrics.get("volume_ok")
        or grouped.get("breakout_volume_gate_ok")
        or _to_float(metrics.get("volume_ratio")) >= 1.0
    )
    chart_fit_score = max(
        entry_candidate_chart_fit_score(row),
        _to_float(condition_scores.get("entry_quality_score")),
        _to_float(grouped.get("scanner_chart_fit_score")),
    )
    selected_rank = int(selected_rank or 0)
    fallback_rank_weak = bool(fallback_used and selected_rank >= 4)

    subtype = "vwap_reclaim_setup"
    if theme_match:
        subtype = "theme_confirmed_pullback"
    elif top_value_confirmed and top_volume_confirmed:
        subtype = "market_representative_pullback"
    elif trading_value >= 0.20 or top_value_confirmed or top_volume_confirmed:
        subtype = "liquidity_confirmed_pullback"

    fallback_qualified = True
    fallback_rejection_reason = ""
    if fallback_rank_weak:
        fallback_qualified = bool(
            theme_match
            or trading_value >= 0.20
            or (volume_confirmation and chart_fit_score >= 0.75)
            or (top_value_confirmed and top_volume_confirmed)
        )
        if not fallback_qualified:
            subtype = "weak_fallback_pullback"
            fallback_rejection_reason = "theme_unconfirmed_fallback_without_liquidity_edge"

    return {
        "schema_version": "pullback_evidence_profile.v1",
        "subtype": subtype,
        "fallback_qualified": bool(fallback_qualified),
        "fallback_rejection_reason": fallback_rejection_reason,
        "fallback_rank_weak": bool(fallback_rank_weak),
        "selected_rank": int(selected_rank),
        "theme_match": bool(theme_match),
        "theme_boost": float(theme_boost),
        "trading_value": float(trading_value),
        "top_value_confirmed": bool(top_value_confirmed),
        "top_volume_confirmed": bool(top_volume_confirmed),
        "volume_confirmation": bool(volume_confirmation),
        "chart_fit_score": float(chart_fit_score),
    }
