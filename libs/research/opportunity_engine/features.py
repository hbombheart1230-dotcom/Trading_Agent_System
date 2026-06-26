from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence


def _pct(current: float, base: float) -> float:
    return ((current / base) - 1.0) * 100.0 if current > 0.0 and base > 0.0 else 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def build_market_features(
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
) -> dict[str, Any]:
    kospi200 = float(current.get("kospi200_pct") or 0.0)
    prior_kospi200 = float(previous.get("kospi200_pct") or kospi200)
    breadth = float(current.get("breadth") or 0.0)
    prior_breadth = float(previous.get("breadth") or breadth)
    impulse = kospi200 - prior_kospi200
    breadth_impulse = breadth - prior_breadth
    level_score = _clamp((kospi200 + 2.0) / 5.0, 0.0, 1.0)
    impulse_score = _clamp((impulse + 0.25) / 1.25, 0.0, 1.0)
    breadth_score = _clamp((breadth + 0.50) / 1.0, 0.0, 1.0)
    breadth_impulse_score = _clamp((breadth_impulse + 0.10) / 0.30, 0.0, 1.0)
    transition_score = (
        0.35 * level_score
        + 0.30 * impulse_score
        + 0.20 * breadth_score
        + 0.15 * breadth_impulse_score
    )
    if kospi200 <= -2.0 and impulse <= 0.0:
        state = "risk_off_continuation"
    elif impulse >= 0.75 and kospi200 >= 0.0:
        state = "broad_market_reversal"
    elif kospi200 >= 1.0 and impulse > 0.0:
        state = "risk_on_acceleration"
    elif impulse > 0.25:
        state = "reversal_watch"
    elif impulse < -0.50:
        state = "momentum_fading"
    else:
        state = "neutral"
    return {
        "available": bool(current),
        "state": state,
        "transition_score": round(transition_score, 6),
        "kospi200_pct": round(kospi200, 6),
        "kospi200_impulse_pct": round(impulse, 6),
        "breadth": round(breadth, 6),
        "breadth_impulse": round(breadth_impulse, 6),
        "source_ts": int(current.get("ts") or 0),
    }


def build_symbol_features(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of_epoch: int,
    market_features: Mapping[str, Any],
) -> dict[str, Any]:
    usable = [row for row in rows if int(row.get("ts") or 0) <= as_of_epoch]
    if len(usable) < 6:
        return {"available": False, "reason": "insufficient_candles", "candle_count": len(usable)}
    current = usable[-1]
    close = float(current.get("close") or 0.0)
    session_open = float(usable[0].get("open") or close)
    opening_low = min(float(row.get("low") or close) for row in usable[: min(5, len(usable))])
    current_volume = float(current.get("volume") or 0.0)
    refs = [float(row.get("volume") or 0.0) for row in usable[-6:-1] if float(row.get("volume") or 0.0) > 0.0]
    ref_median = float(statistics.median(refs)) if refs else 0.0
    ref_average = sum(refs) / len(refs) if refs else 0.0
    robust_volume_ratio = current_volume / ref_median if ref_median > 0.0 else 0.0
    raw_volume_ratio = current_volume / ref_average if ref_average > 0.0 else 0.0
    turnover = close * current_volume
    prior_turnovers = [
        float(row.get("close") or 0.0) * float(row.get("volume") or 0.0)
        for row in usable[-6:-1]
        if float(row.get("volume") or 0.0) > 0.0
    ]
    median_turnover = float(statistics.median(prior_turnovers)) if prior_turnovers else 0.0
    turnover_acceleration = turnover / median_turnover if median_turnover > 0.0 else 0.0
    weighted = [row for row in usable if float(row.get("volume") or 0.0) > 0.0]
    total_volume = sum(float(row.get("volume") or 0.0) for row in weighted)
    vwap = (
        sum(float(row.get("close") or 0.0) * float(row.get("volume") or 0.0) for row in weighted)
        / total_volume
        if total_volume > 0.0
        else close
    )
    momentum_1m = _pct(close, float(usable[-2].get("close") or close))
    momentum_3m = _pct(close, float(usable[-4].get("close") or close))
    momentum_5m = _pct(close, float(usable[-6].get("close") or close))
    prior_momentum_1m = _pct(
        float(usable[-2].get("close") or close),
        float(usable[-3].get("close") or close),
    )
    prior_high = max(float(row.get("high") or close) for row in usable[-6:-1])
    market_return = float(market_features.get("kospi200_pct") or 0.0)
    open_return = _pct(close, session_open)
    relative_strength_proxy = open_return - market_return
    ranges = [
        (float(row.get("high") or 0.0) - float(row.get("low") or 0.0))
        / max(float(row.get("close") or 0.0), 1.0)
        * 100.0
        for row in usable[-6:]
    ]
    atr_6_pct = sum(ranges) / len(ranges)
    return {
        "available": True,
        "candle_count": len(usable),
        "ts": int(current.get("ts") or 0),
        "price": close,
        "session_open": session_open,
        "opening_low": opening_low,
        "open_return_pct": round(open_return, 6),
        "momentum_1m_pct": round(momentum_1m, 6),
        "momentum_3m_pct": round(momentum_3m, 6),
        "momentum_5m_pct": round(momentum_5m, 6),
        "price_acceleration_pct": round(momentum_1m - prior_momentum_1m, 6),
        "market_relative_strength_proxy_pct": round(relative_strength_proxy, 6),
        "vwap": round(vwap, 6),
        "vwap_distance_pct": round(_pct(close, vwap), 6),
        "raw_volume_ratio": round(raw_volume_ratio, 6),
        "robust_volume_ratio": round(robust_volume_ratio, 6),
        "reference_volume_average": round(ref_average, 6),
        "reference_volume_median": round(ref_median, 6),
        "current_volume": round(current_volume, 6),
        "turnover_acceleration": round(turnover_acceleration, 6),
        "breakout_5m": bool(close >= prior_high),
        "opening_low_held": bool(close > opening_low),
        "atr_6_pct": round(atr_6_pct, 6),
    }


def score_opportunity(
    symbol_features: Mapping[str, Any],
    market_features: Mapping[str, Any],
) -> dict[str, Any]:
    if not symbol_features.get("available"):
        return {"score": 0.0, "state": "unavailable", "probe_candidate": False, "components": {}}
    momentum = _clamp((float(symbol_features.get("momentum_3m_pct") or 0.0) + 0.20) / 1.20, 0.0, 1.0)
    acceleration = _clamp((float(symbol_features.get("price_acceleration_pct") or 0.0) + 0.15) / 0.75, 0.0, 1.0)
    relative_strength = _clamp(
        (float(symbol_features.get("market_relative_strength_proxy_pct") or 0.0) + 0.50) / 2.0,
        0.0,
        1.0,
    )
    volume = _clamp(float(symbol_features.get("robust_volume_ratio") or 0.0) / 1.5, 0.0, 1.0)
    turnover = _clamp(float(symbol_features.get("turnover_acceleration") or 0.0) / 1.5, 0.0, 1.0)
    structure = (
        0.50 * float(bool(symbol_features.get("breakout_5m")))
        + 0.25 * float(float(symbol_features.get("vwap_distance_pct") or 0.0) >= -0.15)
        + 0.25 * float(bool(symbol_features.get("opening_low_held")))
    )
    market = float(market_features.get("transition_score") or 0.0)
    components = {
        "market_transition": market,
        "momentum": momentum,
        "price_acceleration": acceleration,
        "relative_strength": relative_strength,
        "robust_volume": volume,
        "turnover_acceleration": turnover,
        "structure": structure,
    }
    score = (
        0.20 * market
        + 0.18 * momentum
        + 0.12 * acceleration
        + 0.18 * relative_strength
        + 0.12 * volume
        + 0.08 * turnover
        + 0.12 * structure
    )
    hard_risk_off = (
        str(market_features.get("state") or "") == "risk_off_continuation"
        and float(symbol_features.get("market_relative_strength_proxy_pct") or 0.0) < 1.0
    )
    probe_fail_reasons: list[str] = []
    if score < 0.68:
        probe_fail_reasons.append("score_below_0.68")
    if hard_risk_off:
        probe_fail_reasons.append("hard_risk_off")
    if float(symbol_features.get("momentum_3m_pct") or 0.0) <= 0.0:
        probe_fail_reasons.append("momentum_3m_not_positive")
    if float(symbol_features.get("robust_volume_ratio") or 0.0) < 0.80:
        probe_fail_reasons.append("robust_volume_lt_0.80")
    if not bool(symbol_features.get("opening_low_held")):
        probe_fail_reasons.append("opening_low_not_held")
    probe_candidate = bool(
        score >= 0.68
        and not hard_risk_off
        and float(symbol_features.get("momentum_3m_pct") or 0.0) > 0.0
        and float(symbol_features.get("robust_volume_ratio") or 0.0) >= 0.80
        and bool(symbol_features.get("opening_low_held"))
    )
    if probe_candidate:
        state = "entry_ready"
    elif score >= 0.55:
        state = "surge_watch"
    elif score <= 0.35:
        state = "weak_or_fading"
    else:
        state = "neutral"
    return {
        "score": round(score, 6),
        "state": state,
        "probe_candidate": probe_candidate,
        "probe_fail_reasons": [] if probe_candidate else probe_fail_reasons,
        "probe_near_miss": bool((not probe_candidate) and score >= 0.65),
        "market_data_missing": not bool(market_features.get("available")),
        "hard_risk_off": hard_risk_off,
        "components": {key: round(value, 6) for key, value in components.items()},
    }
