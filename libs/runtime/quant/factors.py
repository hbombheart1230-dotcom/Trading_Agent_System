from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.runtime.quant.contracts import FactorSnapshot
from libs.runtime.quant.tactics import normalize_tactic_id


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return bool(value)
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "y", "on"}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _optional_float(*values: Any) -> float | None:
    value = _first_present(*values)
    if value in (None, ""):
        return None
    return _to_float(value)


def _nested_mapping(root: Mapping[str, Any] | None, key: str) -> Dict[str, Any]:
    if isinstance(root, Mapping) and isinstance(root.get(key), Mapping):
        return dict(root.get(key) or {})
    return {}


def _cost_floor_state(cost_filter: Mapping[str, Any] | None) -> str:
    if not isinstance(cost_filter, Mapping) or not cost_filter:
        return "unavailable"
    if bool(cost_filter.get("passed") or cost_filter.get("cost_adjusted_edge_ok")):
        return "met"
    return "not_met"


def _compact_missing(factors: Mapping[str, Any], required_keys: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(key for key in required_keys if factors.get(key) in (None, ""))


def build_factor_snapshot(
    *,
    tactic_id: str = "",
    playbook: str = "",
    factors: Mapping[str, Any] | None = None,
    required_keys: tuple[str, ...] = (),
    source: str = "quant_factor_snapshot.v1",
) -> Dict[str, Any]:
    payload = dict(factors or {})
    normalized_tactic = normalize_tactic_id(tactic_id, playbook=playbook or "defensive")
    snapshot = FactorSnapshot(
        tactic_id=normalized_tactic,
        factors=payload,
        missing=_compact_missing(payload, required_keys),
        source=source,
    )
    out = snapshot.as_dict()
    out["playbook"] = str(playbook or "")
    out["behavior_effect"] = "observation_only"
    return out


def build_factor_snapshot_from_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    row = dict(candidate or {}) if isinstance(candidate, Mapping) else {}
    features = _nested_mapping(row, "features")
    components = _nested_mapping(row, "components")
    chart_fit = _nested_mapping(row, "scanner_chart_fit_components")
    macro_chart_fit = _nested_mapping(row, "scanner_macro_chart_fit_components")
    factors = {
        "symbol": str(row.get("symbol") or ""),
        "score_total": _optional_float(row.get("score_total"), row.get("score")),
        "confidence": _optional_float(row.get("confidence")),
        "risk_score": _optional_float(row.get("risk_score")),
        "vwap_distance_pct": _optional_float(features.get("engine_vwap_distance"), features.get("vwap_distance")),
        "compat_vwap_distance_abs": _optional_float(row.get("vwap_distance_abs"), features.get("compat_vwap_distance_abs")),
        "is_below_vwap": _to_bool(_first_present(row.get("is_below_vwap"), features.get("compat_is_below_vwap")), False),
        "volume_ratio": _optional_float(row.get("volume_ratio"), features.get("compat_volume_ratio")),
        "volume_spike20": _optional_float(features.get("engine_volume_spike20")),
        "breakout_gap_pct": _optional_float(row.get("breakout_gap_pct"), features.get("compat_breakout_gap_pct")),
        "entry_compatibility_score": _optional_float(row.get("entry_compatibility_score")),
        "scanner_chart_fit_score": _optional_float(row.get("scanner_chart_fit_score")),
        "scanner_macro_chart_fit_score": _optional_float(row.get("scanner_macro_chart_fit_score")),
        "trend_strength": _optional_float(features.get("engine_trend_strength")),
        "cross_section_rank": _optional_float(features.get("engine_cross_section_rank")),
        "sector_relative_strength": _optional_float(features.get("engine_sector_relative_strength")),
        "news_sentiment_component": _optional_float(components.get("news_sentiment")),
        "theme_boost_component": _optional_float(components.get("theme_boost_component")),
        "dominant_block_reason": str(row.get("dominant_block_reason") or ""),
        "expected_monitor_block_reason": str(row.get("expected_monitor_block_reason") or ""),
        "scanner_chart_fit_available": bool(chart_fit),
        "scanner_macro_chart_fit_available": bool(macro_chart_fit),
    }
    return build_factor_snapshot(
        tactic_id=tactic_id,
        playbook=playbook,
        factors=factors,
        required_keys=("score_total", "confidence", "vwap_distance_pct", "volume_ratio"),
        source="quant_candidate_factor_snapshot.v1",
    )


def build_factor_snapshot_from_monitor_entry(
    entry_info: Mapping[str, Any] | None,
    *,
    selected: Mapping[str, Any] | None = None,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    entry = dict(entry_info or {}) if isinstance(entry_info, Mapping) else {}
    selected_row = dict(selected or {}) if isinstance(selected, Mapping) else {}
    metrics = _nested_mapping(entry, "metrics")
    scores = _nested_mapping(entry, "condition_scores")
    cost_filter = _nested_mapping(entry, "entry_cost_filter")
    if not cost_filter:
        cost_filter = _nested_mapping(entry, "cost_filter")
    signal_evidence = _nested_mapping(entry, "signal_evidence")
    checks = _nested_mapping(signal_evidence, "checks")
    derived = _nested_mapping(signal_evidence, "derived")
    factors = {
        "symbol": str(selected_row.get("symbol") or entry.get("symbol") or ""),
        "triggered": bool(entry.get("triggered")),
        "reason": str(entry.get("reason") or ""),
        "pattern": str(entry.get("pattern") or ""),
        "entry_condition_path": str(entry.get("entry_condition_path") or ""),
        "vwap_distance_pct": _optional_float(metrics.get("vwap_distance"), metrics.get("extended_from_vwap_pct")),
        "volume_ratio": _optional_float(metrics.get("volume_ratio")),
        "pullback_depth_pct": _optional_float(metrics.get("pullback_depth_pct"), metrics.get("pullback_pct")),
        "breakout_gap_pct": _optional_float(metrics.get("breakout_gap_pct")),
        "vwap_reclaim_progress": _optional_float(metrics.get("vwap_reclaim_progress")),
        "reclaim_ok": _to_bool(_first_present(checks.get("reclaim_ok"), metrics.get("vwap_reclaim_ok")), False),
        "volume_ok": _to_bool(_first_present(checks.get("volume_ok"), metrics.get("volume_ok")), False),
        "pullback_ok": _to_bool(_first_present(checks.get("pullback_ok"), metrics.get("pullback_ok")), False),
        "breakout_ok": _to_bool(_first_present(checks.get("breakout_ok"), metrics.get("breakout_ok")), False),
        "confidence_score": _optional_float(scores.get("confidence_score"), metrics.get("confidence_score")),
        "confidence_threshold": _optional_float(scores.get("confidence_threshold"), metrics.get("confidence_threshold")),
        "entry_quality_score": _optional_float(scores.get("entry_quality_score"), metrics.get("entry_quality_score")),
        "weighted_score_total": _optional_float(derived.get("weighted_score_total"), entry.get("total_score")),
        "weighted_score_passed": _to_bool(_first_present(derived.get("weighted_score_passed"), entry.get("score_passed")), False),
        "cost_floor_state": _cost_floor_state(cost_filter),
        "cost_adjusted_edge_ok": _to_bool(entry.get("cost_adjusted_edge_ok"), False),
        "cost_adjusted_edge_pct": _optional_float(entry.get("cost_adjusted_edge_pct"), cost_filter.get("cost_adjusted_edge_pct")),
        "cost_drag_pct": _optional_float(entry.get("cost_drag_pct"), cost_filter.get("cost_drag_pct")),
        "round_trip_cost_floor_pct": _optional_float(cost_filter.get("round_trip_cost_floor_pct")),
        "human_chart_entry_score": _optional_float(metrics.get("human_chart_entry_score")),
        "human_chart_exit_risk_score": _optional_float(metrics.get("human_chart_exit_risk_score")),
        "human_chart_setup_score": _optional_float(metrics.get("human_chart_setup_score")),
        "lower_vwap_rebound_probe_path_ok": _to_bool(metrics.get("lower_vwap_rebound_probe_path_ok"), False),
    }
    return build_factor_snapshot(
        tactic_id=tactic_id,
        playbook=playbook,
        factors=factors,
        required_keys=("vwap_distance_pct", "volume_ratio", "cost_floor_state", "confidence_score"),
        source="quant_monitor_entry_factor_snapshot.v1",
    )

