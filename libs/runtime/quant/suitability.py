from __future__ import annotations

from typing import Any, Dict, Mapping

from libs.runtime.quant.factors import build_factor_snapshot_from_candidate
from libs.runtime.quant.tactics import normalize_tactic_id


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, float(value))))


def _factor(snapshot: Mapping[str, Any], key: str, default: Any = None) -> Any:
    factors = snapshot.get("factors") if isinstance(snapshot.get("factors"), Mapping) else {}
    return factors.get(key, default)


def _score_band(value: float | None, lo: float, hi: float, *, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    v = float(value)
    if lo <= v <= hi:
        return 1.0
    if v < lo:
        return _clamp01(1.0 - ((lo - v) / max(abs(lo), 1e-9)))
    return _clamp01(1.0 - ((v - hi) / max(abs(hi), 1e-9)))


def _score_min(value: float | None, threshold: float, *, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    if threshold <= 0:
        return 1.0 if value > 0 else 0.0
    return _clamp01(float(value) / float(threshold))


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _to_float(value)


def _append_if(items: list[str], condition: bool, value: str) -> None:
    if condition and value and value not in items:
        items.append(value)


def score_tactic_suitability(
    factor_snapshot: Mapping[str, Any] | None,
    *,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    snapshot = dict(factor_snapshot or {}) if isinstance(factor_snapshot, Mapping) else {}
    tactic = normalize_tactic_id(
        tactic_id or snapshot.get("tactic_id"),
        playbook=playbook or str(snapshot.get("playbook") or "defensive"),
    )
    vwap = _num(_factor(snapshot, "vwap_distance_pct"))
    volume = _num(_factor(snapshot, "volume_ratio"))
    if volume is None:
        volume = _num(_factor(snapshot, "volume_spike20"))
    breakout_gap = _num(_factor(snapshot, "breakout_gap_pct"))
    trend = _num(_factor(snapshot, "trend_strength"))
    chart_fit = _num(_factor(snapshot, "scanner_chart_fit_score"))
    confidence = _num(_factor(snapshot, "confidence"))
    is_below_vwap = bool(_factor(snapshot, "is_below_vwap", False))
    dominant_block = str(_factor(snapshot, "dominant_block_reason", "") or "")
    expected_block = str(_factor(snapshot, "expected_monitor_block_reason", "") or "")

    components: Dict[str, float] = {}
    positives: list[str] = []
    penalties: list[str] = []

    if tactic == "vwap_reclaim_pullback":
        components["vwap_band"] = _score_band(vwap, -0.015, 0.025, fallback=0.35)
        components["volume_confirmation"] = _score_min(volume, 1.0, fallback=0.35)
        components["trend_support"] = _score_min(trend, 0.35, fallback=0.45)
        components["chart_fit"] = _score_min(chart_fit, 0.60, fallback=0.45)
        _append_if(positives, components["vwap_band"] >= 0.8, "vwap_pullback_band_fit")
        _append_if(positives, components["volume_confirmation"] >= 0.8, "volume_confirmation_fit")
        _append_if(penalties, expected_block in {"pullback_not_mature", "volume_confirmation_missing"}, expected_block)
    elif tactic == "lower_vwap_rebound_probe":
        components["lower_vwap_band"] = _score_band(vwap, -0.008, -0.0015, fallback=0.25)
        components["rebound_volume"] = _score_min(volume, 0.75, fallback=0.35)
        components["confidence"] = _score_min(confidence, 0.50, fallback=0.35)
        components["below_vwap_context"] = 1.0 if is_below_vwap else 0.25
        _append_if(positives, components["lower_vwap_band"] >= 0.8, "lower_vwap_rebound_band_fit")
    elif tactic in {"opening_range_breakout", "volume_breakout", "opening_gap_momentum", "trend_continuation"}:
        components["breakout_readiness"] = _score_min(breakout_gap, 0.0, fallback=0.40)
        components["volume_expansion"] = _score_min(volume, 1.2, fallback=0.35)
        components["trend_support"] = _score_min(trend, 0.40, fallback=0.40)
        components["not_below_vwap"] = 0.35 if is_below_vwap else 1.0
        _append_if(positives, components["volume_expansion"] >= 0.8, "volume_expansion_fit")
        _append_if(penalties, expected_block in {"breakout_not_ready", "volume_confirmation_missing"}, expected_block)
    elif tactic in {"reversal_reclaim", "mean_reversion_probe"}:
        components["reclaim_room"] = _score_band(vwap, -0.025, 0.010, fallback=0.40)
        components["volume_recovery"] = _score_min(volume, 0.8, fallback=0.35)
        components["chart_fit"] = _score_min(chart_fit, 0.55, fallback=0.45)
        _append_if(positives, components["reclaim_room"] >= 0.75, "reversal_reclaim_band_fit")
    else:
        components["confidence"] = _score_min(confidence, 0.55, fallback=0.45)
        components["chart_fit"] = _score_min(chart_fit, 0.55, fallback=0.45)
        components["risk_observation"] = 0.50

    if dominant_block:
        penalties.append(f"dominant_block:{dominant_block}")

    score = sum(components.values()) / float(len(components) or 1)
    if penalties:
        score -= min(0.20, 0.05 * len(penalties))
    score = round(_clamp01(score), 4)
    tier = "strong" if score >= 0.75 else "watch" if score >= 0.55 else "weak"
    return {
        "schema_version": "tactic_suitability.v1",
        "tactic_id": tactic,
        "score": score,
        "tier": tier,
        "components": {key: round(float(value), 4) for key, value in components.items()},
        "positive_reasons": positives[:6],
        "penalty_reasons": penalties[:6],
        "behavior_effect": "observation_only",
    }


def score_candidate_tactic_suitability(
    candidate: Mapping[str, Any] | None,
    *,
    tactic_id: str = "",
    playbook: str = "",
) -> Dict[str, Any]:
    snapshot = build_factor_snapshot_from_candidate(candidate, tactic_id=tactic_id, playbook=playbook)
    out = score_tactic_suitability(snapshot, tactic_id=tactic_id, playbook=playbook)
    out["factor_snapshot_ref"] = {
        "source": snapshot.get("source"),
        "tactic_id": snapshot.get("tactic_id"),
        "missing": list(snapshot.get("missing") or []),
    }
    return out

