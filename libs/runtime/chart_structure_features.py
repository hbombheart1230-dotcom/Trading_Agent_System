from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence


SCHEMA_VERSION = "chart_structure_features.v1"
CHART_STRUCTURE_FEATURE_ALLOWED_STATES: Dict[str, tuple[str, ...]] = {
    "structure_hh_hl": ("intact", "weakening", "broken"),
    "structure_range_compression": ("none", "moderate", "tight"),
    "structure_breakout_attempt": ("none", "forming", "attempting", "confirmed", "rejected"),
    "ma_alignment_state": ("bullish", "mixed", "bearish", "neutral"),
    "ma_slope_strength": ("rising_strong", "rising_weak", "flat", "falling_weak", "falling_strong"),
    "trend_regime": ("trending", "transition", "ranging"),
    "support_holding": ("holding", "testing", "lost"),
    "resistance_break_confirmed": ("none", "attempting", "confirmed", "failed"),
    "failed_breakout": ("none", "suspected", "confirmed"),
    "momentum_follow_through": ("none", "weak", "moderate", "strong"),
    "volume_sustain": ("absent", "fading", "adequate", "strong"),
    "momentum_decay": ("none", "mild", "strong"),
}
CHART_STRUCTURE_FEATURE_NAMES = tuple(CHART_STRUCTURE_FEATURE_ALLOWED_STATES.keys())


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _moving_average(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / float(period)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(float(denominator)) <= 1e-9:
        return 0.0
    return float(numerator) / float(denominator)


def _empty_feature_groups() -> Dict[str, Dict[str, Any]]:
    return {
        "structure": {
            "structure_hh_hl": None,
            "structure_range_compression": None,
            "structure_breakout_attempt": None,
        },
        "trend_alignment": {
            "ma_alignment_state": None,
            "ma_slope_strength": None,
            "trend_regime": None,
        },
        "support_resistance": {
            "support_holding": None,
            "resistance_break_confirmed": None,
            "failed_breakout": None,
        },
        "continuity_momentum": {
            "momentum_follow_through": None,
            "volume_sustain": None,
            "momentum_decay": None,
        },
    }


def empty_chart_structure_features(*, notes: Sequence[Any] | None = None) -> Dict[str, Any]:
    out = {
        "schema_version": SCHEMA_VERSION,
        "available": False,
        **_empty_feature_groups(),
        "notes": [],
    }
    if notes:
        out["notes"] = [str(value).strip() for value in list(notes or []) if str(value).strip()]
    return out


def build_chart_structure_features(
    candles: Sequence[Mapping[str, Any]] | None,
    *,
    current_price: Any = None,
    current_vwap: Any = None,
    recent_high: Any = None,
    breakout_ok: bool | None = None,
    pullback_ok: bool | None = None,
    reclaim_ok: bool | None = None,
    volume_ok: bool | None = None,
    confidence_ok: bool | None = None,
    volume_ratio: Any = None,
    too_extended: bool | None = None,
) -> Dict[str, Any]:
    rows = [row for row in list(candles or []) if isinstance(row, Mapping)]
    if len(rows) < 4:
        return empty_chart_structure_features(notes=["insufficient_candles"])

    closes = [_to_float(row.get("close")) for row in rows]
    highs = [_to_float(row.get("high")) for row in rows]
    lows = [_to_float(row.get("low")) for row in rows]
    volumes = [max(0.0, _to_float(row.get("volume"))) for row in rows]
    ranges = [max(0.0, high - low) for high, low in zip(highs, lows)]

    if not any(price > 0.0 for price in closes):
        return empty_chart_structure_features(notes=["invalid_candle_series"])

    current_close = _to_float(current_price, closes[-1])
    current_high = highs[-1]
    current_low = lows[-1]
    prior_close = closes[-2]
    prior_high = highs[-2]
    prior_low = lows[-2]
    current_range = max(0.0, current_high - current_low)
    current_vwap_value = _to_float(current_vwap, _to_float(rows[-1].get("vwap")))
    recent_high_value = _to_float(recent_high, max(highs[:-1]))
    recent_low_value = min(lows[-4:-1]) if len(lows) >= 4 else min(lows[:-1] or lows)
    volume_ratio_value = _to_float(volume_ratio, 0.0)

    out = empty_chart_structure_features()
    out["available"] = True

    structure = out["structure"]
    trend_alignment = out["trend_alignment"]
    support_resistance = out["support_resistance"]
    continuity_momentum = out["continuity_momentum"]

    last3_highs = highs[-3:]
    last3_lows = lows[-3:]
    if last3_highs[-1] > last3_highs[-2] and last3_lows[-1] > last3_lows[-2]:
        structure["structure_hh_hl"] = "intact"
    elif last3_highs[-1] >= last3_highs[-2] or last3_lows[-1] >= last3_lows[-2]:
        structure["structure_hh_hl"] = "weakening"
    else:
        structure["structure_hh_hl"] = "broken"

    recent_ranges = ranges[-5:] if len(ranges) >= 5 else ranges
    early_ranges = recent_ranges[: max(1, len(recent_ranges) // 2)]
    late_ranges = recent_ranges[max(1, len(recent_ranges) // 2) :]
    early_avg_range = sum(early_ranges) / float(len(early_ranges)) if early_ranges else 0.0
    late_avg_range = sum(late_ranges) / float(len(late_ranges)) if late_ranges else 0.0
    compression_ratio = _safe_ratio(late_avg_range, early_avg_range)
    if early_avg_range <= 0.0:
        structure["structure_range_compression"] = "none"
    elif compression_ratio <= 0.65:
        structure["structure_range_compression"] = "tight"
    elif compression_ratio <= 0.85:
        structure["structure_range_compression"] = "moderate"
    else:
        structure["structure_range_compression"] = "none"

    broke_recent_high = current_high > recent_high_value * 1.0005 if recent_high_value > 0.0 else False
    close_above_recent_high = current_close > recent_high_value * 1.0005 if recent_high_value > 0.0 else False
    if bool(breakout_ok) and close_above_recent_high:
        structure["structure_breakout_attempt"] = "confirmed"
    elif broke_recent_high and not close_above_recent_high:
        structure["structure_breakout_attempt"] = "rejected"
    elif broke_recent_high or bool(breakout_ok):
        structure["structure_breakout_attempt"] = "attempting"
    elif recent_high_value > 0.0 and current_close >= recent_high_value * 0.998:
        structure["structure_breakout_attempt"] = "forming"
    else:
        structure["structure_breakout_attempt"] = "none"

    ma2 = _moving_average(closes, 2)
    ma3 = _moving_average(closes, 3)
    ma5 = _moving_average(closes, 5)
    if ma2 is None or ma3 is None or ma5 is None:
        trend_alignment["ma_alignment_state"] = None
    elif ma2 > ma3 > ma5:
        trend_alignment["ma_alignment_state"] = "bullish"
    elif ma2 < ma3 < ma5:
        trend_alignment["ma_alignment_state"] = "bearish"
    elif max(abs(ma2 - ma3), abs(ma3 - ma5)) <= max(0.001 * max(current_close, 1.0), 0.05):
        trend_alignment["ma_alignment_state"] = "neutral"
    else:
        trend_alignment["ma_alignment_state"] = "mixed"

    prev_ma3 = _moving_average(closes[:-1], 3) if len(closes) >= 4 else None
    ma3_delta_pct = _safe_ratio((ma3 or 0.0) - (prev_ma3 or 0.0), max(current_close, 1.0))
    if prev_ma3 is None:
        trend_alignment["ma_slope_strength"] = None
    elif ma3_delta_pct >= 0.003:
        trend_alignment["ma_slope_strength"] = "rising_strong"
    elif ma3_delta_pct >= 0.001:
        trend_alignment["ma_slope_strength"] = "rising_weak"
    elif ma3_delta_pct <= -0.003:
        trend_alignment["ma_slope_strength"] = "falling_strong"
    elif ma3_delta_pct <= -0.001:
        trend_alignment["ma_slope_strength"] = "falling_weak"
    else:
        trend_alignment["ma_slope_strength"] = "flat"

    if trend_alignment["ma_alignment_state"] in {"bullish", "bearish"} and trend_alignment["ma_slope_strength"] not in {None, "flat"}:
        trend_alignment["trend_regime"] = "trending"
    elif structure["structure_range_compression"] in {"moderate", "tight"} and trend_alignment["ma_alignment_state"] in {"mixed", "neutral", None}:
        trend_alignment["trend_regime"] = "ranging"
    else:
        trend_alignment["trend_regime"] = "transition"

    support_buffer = recent_low_value * 0.006 if recent_low_value > 0.0 else 0.0
    if recent_low_value <= 0.0:
        support_resistance["support_holding"] = None
    elif current_low < recent_low_value - support_buffer:
        support_resistance["support_holding"] = "lost"
    elif current_close >= recent_low_value and (bool(reclaim_ok) or bool(pullback_ok) or current_close >= current_vwap_value):
        support_resistance["support_holding"] = "holding"
    else:
        support_resistance["support_holding"] = "testing"

    if recent_high_value > 0.0 and close_above_recent_high:
        support_resistance["resistance_break_confirmed"] = "confirmed"
    elif broke_recent_high and current_close < recent_high_value * 0.997:
        support_resistance["resistance_break_confirmed"] = "failed"
    elif broke_recent_high or current_close >= recent_high_value * 0.998:
        support_resistance["resistance_break_confirmed"] = "attempting"
    else:
        support_resistance["resistance_break_confirmed"] = "none"

    if recent_high_value > 0.0 and broke_recent_high and current_close < recent_high_value * 0.997:
        support_resistance["failed_breakout"] = "confirmed"
    elif recent_high_value > 0.0 and current_high > recent_high_value and current_close < recent_high_value:
        support_resistance["failed_breakout"] = "suspected"
    else:
        support_resistance["failed_breakout"] = "none"

    close_delta = current_close - prior_close
    prev_close_delta = prior_close - closes[-3]
    closes_near_high = current_close >= current_high - (current_range * 0.35 if current_range > 0.0 else 0.0)
    if bool(breakout_ok) and bool(volume_ok) and close_delta > 0.0 and prev_close_delta > 0.0 and closes_near_high:
        continuity_momentum["momentum_follow_through"] = "strong"
    elif bool(breakout_ok) and close_delta > 0.0:
        continuity_momentum["momentum_follow_through"] = "moderate"
    elif close_delta > 0.0:
        continuity_momentum["momentum_follow_through"] = "weak"
    else:
        continuity_momentum["momentum_follow_through"] = "none"

    if volume_ratio_value >= 1.5:
        continuity_momentum["volume_sustain"] = "strong"
    elif volume_ratio_value >= 1.0:
        continuity_momentum["volume_sustain"] = "adequate"
    elif volume_ratio_value >= 0.75:
        continuity_momentum["volume_sustain"] = "fading"
    else:
        continuity_momentum["volume_sustain"] = "absent"

    if close_delta < 0.0 and (not bool(confidence_ok) or volume_ratio_value < 0.9):
        continuity_momentum["momentum_decay"] = "strong"
    elif bool(too_extended) or close_delta < 0.0 or (not bool(breakout_ok) and volume_ratio_value < 1.0):
        continuity_momentum["momentum_decay"] = "mild"
    else:
        continuity_momentum["momentum_decay"] = "none"

    notes: List[str] = []
    if len(rows) < 5:
        notes.append("reduced_lookback")
    if current_vwap_value <= 0.0:
        notes.append("vwap_reference_missing")
    if recent_high_value <= 0.0:
        notes.append("breakout_reference_missing")
    if not any(volume > 0.0 for volume in volumes):
        notes.append("volume_series_missing")
    out["notes"] = notes
    return out
