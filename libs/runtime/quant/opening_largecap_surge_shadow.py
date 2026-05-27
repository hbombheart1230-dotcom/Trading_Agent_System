from __future__ import annotations

from typing import Any, Dict, Mapping


OPENING_LARGECAP_SURGE_WATCHLIST = frozenset(
    {
        "005930",  # Samsung Electronics
        "000660",  # SK hynix
        "009150",  # Samsung Electro-Mechanics
    }
)
OPENING_LARGECAP_SURGE_WINDOW_MINUTES = 20
OPENING_LARGECAP_SURGE_VOLUME_FLOOR = 0.72
OPENING_LARGECAP_SURGE_HUMAN_SCORE_FLOOR = 0.55


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "unknown", "not_captured"} else text


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _symbol(row: Mapping[str, Any]) -> str:
    return _text(row.get("symbol") or row.get("stk_cd") or row.get("code"))


def _factor_snapshot(row: Mapping[str, Any]) -> Dict[str, Any]:
    snapshot = _as_dict(row.get("quant_factor_snapshot"))
    return _as_dict(snapshot.get("factors"))


def _cost_ok(row: Mapping[str, Any]) -> bool:
    if _bool(row.get("cost_adjusted_edge_ok")):
        return True
    decision = _as_dict(row.get("entry_quant_decision"))
    cost_edge = _as_dict(decision.get("cost_edge"))
    if _bool(cost_edge.get("ok")):
        return True
    factors = _factor_snapshot(row)
    if _bool(factors.get("cost_adjusted_edge_ok")):
        return True
    return _text(row.get("entry_quant_cost_floor_state")) == "met" or _text(factors.get("cost_floor_state")) == "met"


def build_opening_largecap_surge_shadow(
    row: Mapping[str, Any],
    *,
    opening_minutes: int | None,
) -> Dict[str, Any]:
    symbol = _symbol(row)
    if symbol not in OPENING_LARGECAP_SURGE_WATCHLIST:
        return {
            "eligible": False,
            "would_probe": False,
            "reason": "not_largecap_surge_watchlist",
            "symbol": symbol,
            "behavior_effect": "observation_only",
        }
    if opening_minutes is None or opening_minutes > OPENING_LARGECAP_SURGE_WINDOW_MINUTES:
        return {
            "eligible": False,
            "would_probe": False,
            "reason": "outside_opening_window",
            "symbol": symbol,
            "minutes_since_open": opening_minutes,
            "watchlist": sorted(OPENING_LARGECAP_SURGE_WATCHLIST),
            "behavior_effect": "observation_only",
        }

    factors = _factor_snapshot(row)
    volume_ratio = _float(row.get("volume_ratio"), _float(factors.get("volume_ratio"), 0.0)) or 0.0
    vwap_distance = _float(row.get("vwap_distance"), _float(factors.get("vwap_distance_pct"), 0.0)) or 0.0
    human_chart_entry_score = _float(factors.get("human_chart_entry_score"), 0.0) or 0.0
    breakout_ok = _bool(row.get("breakout_ok")) or _bool(factors.get("breakout_ok"))
    weighted_score_passed = _bool(factors.get("weighted_score_passed"))
    cost_ok = _cost_ok(row)
    structure_ok = bool(
        breakout_ok
        or weighted_score_passed
        or human_chart_entry_score >= OPENING_LARGECAP_SURGE_HUMAN_SCORE_FLOOR
    )
    would_probe = bool(
        cost_ok
        and volume_ratio >= OPENING_LARGECAP_SURGE_VOLUME_FLOOR
        and vwap_distance >= 0.0
        and structure_ok
    )

    reason_parts = []
    if not cost_ok:
        reason_parts.append("cost_edge_not_met")
    if volume_ratio < OPENING_LARGECAP_SURGE_VOLUME_FLOOR:
        reason_parts.append("volume_ratio_below_largecap_floor")
    if vwap_distance < 0.0:
        reason_parts.append("below_vwap")
    if not structure_ok:
        reason_parts.append("momentum_structure_not_confirmed")

    return {
        "eligible": True,
        "would_probe": would_probe,
        "reason": "opening_largecap_surge_ready" if would_probe else ",".join(reason_parts),
        "symbol": symbol,
        "minutes_since_open": opening_minutes,
        "cost_ok": cost_ok,
        "volume_ratio": volume_ratio,
        "volume_floor": OPENING_LARGECAP_SURGE_VOLUME_FLOOR,
        "vwap_distance_pct": vwap_distance,
        "breakout_ok": breakout_ok,
        "weighted_score_passed": weighted_score_passed,
        "human_chart_entry_score": human_chart_entry_score,
        "human_score_floor": OPENING_LARGECAP_SURGE_HUMAN_SCORE_FLOOR,
        "probe_size_hint": "small",
        "watchlist": sorted(OPENING_LARGECAP_SURGE_WATCHLIST),
        "behavior_effect": "observation_only",
    }
