from __future__ import annotations

from typing import Any, Dict, Mapping


TARGET_REASONS = {"below_vwap_reclaim_not_ready", "pullback_below_vwap_reclaim_not_ready"}


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "unknown", "not_captured"} else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _factors(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _as_dict(row.get("quant_factor_snapshot"))
    factors = _as_dict(snapshot.get("factors"))
    if factors:
        return factors
    return _as_dict(row.get("factors"))


def _market_rail(row: Mapping[str, Any]) -> str:
    lane = _as_dict(row.get("entry_lane_observation"))
    if lane.get("market_regime_rail"):
        return _text(lane.get("market_regime_rail"))
    shadow = _as_dict(lane.get("market_regime_rail_shadow"))
    if shadow.get("market_regime_rail"):
        return _text(shadow.get("market_regime_rail"))
    for key in ("market_regime_rail", "rail_id", "market_rail"):
        if row.get(key):
            return _text(row.get(key))
    return ""


def _reason_matches(row: Mapping[str, Any]) -> bool:
    reason = _text(row.get("reason"))
    axis = _text(row.get("primary_failure_axis"))
    return reason in TARGET_REASONS or axis == "vwap_relationship"


def classify_below_vwap_reclaim_subtype_v2(
    *,
    vwap_distance: float,
    reclaim_progress: float,
    volume_ratio: float,
    pullback_depth: float,
    entry_quality: float,
    human_chart_score: float,
    reclaim_ok: bool,
    pullback_ok: bool,
    volume_ok: bool,
    market_regime_rail: str = "",
) -> str:
    """Return a more diagnostic observation-only subtype."""

    rail = _text(market_regime_rail).lower()
    improving_volume = bool(volume_ok or volume_ratio >= 0.85)
    post_reclaim = bool(
        (reclaim_ok or reclaim_progress >= 0.85)
        and pullback_ok
        and improving_volume
        and -0.004 <= vwap_distance <= 0.004
    )
    if post_reclaim:
        return "confirmed_post_reclaim_pullback"
    if (
        ("risk_off" in rail or "gap_down" in rail or "breadth_collapse" in rail)
        and vwap_distance >= -0.012
        and reclaim_progress < 0.35
        and volume_ratio < 0.35
    ):
        return "index_or_largecap_rebound_below_vwap"
    if vwap_distance <= -0.012:
        return "deep_below_vwap_failure"
    if vwap_distance >= -0.006 and (pullback_ok or entry_quality >= 0.5 or human_chart_score >= 0.45):
        return "shallow_below_vwap_rebound"
    if -0.003 <= vwap_distance <= 0.0015:
        return "near_vwap_reclaim_setup"
    return "ordinary_below_vwap_failure"


def classify_below_vwap_reclaim_observation(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify VWAP reclaim blockers for observation only.

    This intentionally does not decide whether the candidate should enter. It
    only labels blocked candidates so Q8 can separate true failures from setups
    that may be close to reclaiming VWAP.
    """

    if not _reason_matches(row):
        return {
            "schema_version": "below_vwap_reclaim_observation.v1",
            "behavior_effect": "observation_only",
            "applies": False,
            "subtype": "",
            "reason": "not_below_vwap_reclaim_blocker",
        }

    factors = _factors(row)
    vwap_distance = _float(
        row.get("vwap_distance_pct")
        if row.get("vwap_distance_pct") not in (None, "")
        else row.get("vwap_distance"),
        _float(factors.get("vwap_distance_pct"), _float(factors.get("vwap_distance"), 0.0)),
    )
    reclaim_progress = _float(factors.get("vwap_reclaim_progress"), _float(row.get("vwap_reclaim_progress"), 0.0))
    volume_ratio = _float(row.get("volume_ratio"), _float(factors.get("volume_ratio"), 0.0))
    pullback_depth = _float(factors.get("pullback_depth_pct"), _float(row.get("pullback_depth_pct"), 0.0))
    entry_quality = _float(factors.get("entry_quality_score"), _float(row.get("entry_quality_score"), 0.0))
    human_chart_score = _float(factors.get("human_chart_entry_score"), _float(row.get("human_chart_entry_score"), 0.0))
    reclaim_ok = _bool(factors.get("reclaim_ok")) or _bool(factors.get("vwap_reclaim_ok")) or _bool(row.get("vwap_reclaim_ok"))
    pullback_ok = _bool(factors.get("pullback_ok")) or _bool(row.get("pullback_ok"))
    volume_ok = _bool(factors.get("volume_ok")) or _bool(row.get("volume_ok"))
    market_regime_rail = _market_rail(row)

    abs_distance = abs(vwap_distance)
    near_vwap = bool(-0.003 <= vwap_distance < 0.0 or abs_distance <= 0.0015)
    improving_volume = bool(volume_ok or volume_ratio >= 0.85)
    reclaim_in_progress = bool(
        not reclaim_ok
        and reclaim_progress >= 0.65
        and vwap_distance >= -0.006
        and improving_volume
    )
    post_reclaim_pullback = bool(
        (reclaim_ok or reclaim_progress >= 0.85)
        and pullback_ok
        and improving_volume
        and -0.004 <= vwap_distance <= 0.004
    )

    if post_reclaim_pullback:
        subtype = "post_reclaim_pullback_candidate"
    elif reclaim_in_progress:
        subtype = "reclaim_in_progress_with_improving_volume"
    elif near_vwap:
        subtype = "near_vwap_reclaim_setup"
    else:
        subtype = "true_below_vwap_failure"
    subtype_v2 = classify_below_vwap_reclaim_subtype_v2(
        vwap_distance=float(vwap_distance),
        reclaim_progress=float(reclaim_progress),
        volume_ratio=float(volume_ratio),
        pullback_depth=float(pullback_depth),
        entry_quality=float(entry_quality),
        human_chart_score=float(human_chart_score),
        reclaim_ok=bool(reclaim_ok),
        pullback_ok=bool(pullback_ok),
        volume_ok=bool(volume_ok),
        market_regime_rail=market_regime_rail,
    )

    return {
        "schema_version": "below_vwap_reclaim_observation.v2",
        "behavior_effect": "observation_only",
        "applies": True,
        "subtype": subtype,
        "subtype_v2": subtype_v2,
        "vwap_distance_pct": float(vwap_distance),
        "vwap_reclaim_progress": float(reclaim_progress),
        "volume_ratio": float(volume_ratio),
        "pullback_depth_pct": float(pullback_depth),
        "entry_quality_score": float(entry_quality),
        "human_chart_entry_score": float(human_chart_score),
        "reclaim_ok": bool(reclaim_ok),
        "pullback_ok": bool(pullback_ok),
        "volume_ok": bool(volume_ok),
        "market_regime_rail": market_regime_rail,
        "near_vwap": bool(near_vwap),
        "improving_volume": bool(improving_volume),
        "reclaim_in_progress": bool(reclaim_in_progress),
        "post_reclaim_pullback": bool(post_reclaim_pullback),
    }
