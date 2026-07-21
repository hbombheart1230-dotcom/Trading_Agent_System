from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from libs.market.korea_index_sanity import korea_index_sanity


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def load_latest_macro_packet(
    *,
    day: str = "",
    root: Path = Path("data/logs/macro_indicators"),
) -> Dict[str, Any]:
    if day:
        latest = root / str(day)[:10] / "latest.json"
        payload = _read_json(latest)
        if payload:
            return payload
    candidates = sorted(root.glob("*/latest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return _read_json(candidates[0]) if candidates else {}


def classify_market_regime_rail(macro_packet: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify macro/index evidence for Q8 observation only."""

    global_sentiment = _as_dict(macro_packet.get("global_sentiment"))
    index_moves = _as_dict(macro_packet.get("index_moves"))
    korea_indices = _as_dict(macro_packet.get("korea_indices"))
    sanity = korea_index_sanity(korea_indices) if korea_indices else {"status": "ok", "warning_count": 0, "warnings": [], "extreme_move_requires_confirmation": False}
    krx_night_futures = _as_dict(macro_packet.get("krx_night_futures"))
    macro_moves = _as_dict(macro_packet.get("macro_moves"))

    global_score = _float(global_sentiment.get("score"), 0.0)
    kospi_pct = _float(index_moves.get("kospi_pct"), 0.0)
    kosdaq_pct = _float(index_moves.get("kosdaq_pct"), 0.0)
    kospi200_pct = _float(index_moves.get("kospi200_pct"), 0.0)
    krx_night_pct = _float(
        index_moves.get("krx_night_futures_pct"),
        _float(krx_night_futures.get("change_pct"), 0.0),
    )
    nasdaq_pct = _float(index_moves.get("nasdaq_pct"), 0.0)
    sp500_pct = _float(index_moves.get("sp500_pct"), 0.0)
    dxy_pct = _float(macro_moves.get("dxy_pct"), 0.0)
    vix_pct = _float(macro_moves.get("vix_pct"), 0.0)
    breadth = _float(korea_indices.get("breadth"), 0.0)
    korea_avg = _float(korea_indices.get("average_change_pct"), (kospi_pct + kosdaq_pct) / 2.0)

    if krx_night_pct <= -1.0:
        regime = "risk_off"
        rail = "krx_night_futures_gap_down"
        rationale = "krx_night_futures_deeply_negative_before_or_near_open"
    elif krx_night_pct >= 1.0 and global_score >= 0.0:
        regime = "risk_on"
        rail = "krx_night_futures_gap_up"
        rationale = "krx_night_futures_strong_positive_before_or_near_open"
    elif korea_avg <= -2.0 and breadth <= -0.40:
        regime = "risk_off"
        rail = "risk_off_breadth_collapse"
        rationale = "korea_indices_and_breadth_deeply_negative"
    elif korea_avg <= -0.70 and nasdaq_pct >= 0.20:
        regime = "selective_risk"
        rail = "us_tech_risk_on_korea_weak"
        rationale = "us_tech_positive_while_korea_indices_weak"
    elif global_score >= 0.15 and korea_avg >= 0.30 and breadth >= 0.15:
        regime = "risk_on"
        rail = "risk_on_breadth_support"
        rationale = "global_and_korea_breadth_supportive"
    elif global_score <= -0.15 or dxy_pct >= 0.40 or vix_pct >= 5.0:
        regime = "risk_off"
        rail = "global_risk_off_pressure"
        rationale = "global_sentiment_or_volatility_pressure"
    else:
        regime = "neutral"
        rail = "mixed_neutral"
        rationale = "mixed_or_moderate_macro_conditions"

    return {
        "schema_version": "market_regime_rail_shadow.v1",
        "behavior_effect": "observation_only",
        "market_regime": regime,
        "market_regime_rail": rail,
        "rail_source": "deterministic_classifier",
        "rail_confidence": "medium",
        "rail_rationale": rationale,
        "generated_at": str(macro_packet.get("generated_at") or ""),
        "metrics": {
            "global_sentiment_score": global_score,
            "kospi_pct": kospi_pct,
            "kosdaq_pct": kosdaq_pct,
            "kospi200_pct": kospi200_pct,
            "krx_night_futures_pct": krx_night_pct,
            "krx_night_futures_status": str(krx_night_futures.get("status") or ""),
            "krx_night_futures_pressure": str(krx_night_futures.get("direction_pressure") or ""),
            "korea_average_change_pct": korea_avg,
            "korea_breadth": breadth,
            "nasdaq_pct": nasdaq_pct,
            "sp500_pct": sp500_pct,
            "dxy_pct": dxy_pct,
            "vix_pct": vix_pct,
        },
        "market_input_sanity": sanity,
    }


def latest_market_regime_observation(*, day: str = "") -> Dict[str, Any]:
    packet = load_latest_macro_packet(day=day)
    if not packet:
        return {
            "schema_version": "market_regime_rail_shadow.v1",
            "behavior_effect": "observation_only",
            "market_regime": "unknown",
            "market_regime_rail": "macro_packet_unavailable",
            "rail_source": "unavailable",
            "rail_confidence": "none",
            "rail_rationale": "latest_macro_packet_unavailable",
            "metrics": {},
        }
    return classify_market_regime_rail(packet)
