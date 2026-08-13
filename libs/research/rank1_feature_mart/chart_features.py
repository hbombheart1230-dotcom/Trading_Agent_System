from __future__ import annotations

from typing import Any, Mapping, Sequence

from libs.runtime.chart_structure_features import build_chart_structure_features


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _day(row: Mapping[str, Any]) -> str:
    raw = str(row.get("raw_ts") or "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return str(row.get("day") or "")


def _sma(values: Sequence[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def _cross_state(values: Sequence[float], fast: int, slow: int) -> str:
    if len(values) < slow + 1:
        return "INSUFFICIENT_HISTORY"
    fast_now, slow_now = _sma(values, fast), _sma(values, slow)
    fast_before, slow_before = _sma(values[:-1], fast), _sma(values[:-1], slow)
    if None in (fast_now, slow_now, fast_before, slow_before):
        return "INSUFFICIENT_HISTORY"
    if fast_before <= slow_before and fast_now > slow_now:
        return "CROSS_NOW"
    if fast_before >= slow_before and fast_now < slow_now:
        return "DEATH_CROSS_NOW"
    if fast_now > slow_now:
        extension = (fast_now / slow_now - 1.0) if slow_now else 0.0
        return "POST_CROSS_EXTENDED" if extension >= 0.02 else "POST_CROSS_HEALTHY"
    if fast_now < slow_now:
        return "BEARISH_ALIGNMENT"
    return "PRE_CROSS"


def _vwap(rows: Sequence[Mapping[str, Any]]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for row in rows:
        volume = max(0.0, _number(row.get("volume")) or 0.0)
        high = _number(row.get("high"))
        low = _number(row.get("low"))
        close = _number(row.get("close"))
        if volume <= 0.0 or None in (high, low, close):
            continue
        numerator += ((high + low + close) / 3.0) * volume
        denominator += volume
    return numerator / denominator if denominator > 0.0 else None


def _daily_cross(rows: Sequence[Mapping[str, Any]], day: str) -> str:
    closes = [
        _number(row.get("close"))
        for row in rows
        if _day(row) < day and _number(row.get("close")) is not None
    ]
    return _cross_state([float(value) for value in closes], 5, 20)


def build_rank1_chart_snapshot(
    *,
    day: str,
    decision_epoch: int,
    minute_rows: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    day_rows = [row for row in minute_rows if _day(row) == day]
    completed = [row for row in day_rows if int(row.get("ts") or 0) + 60 <= decision_epoch]
    prior_days = sorted({_day(row) for row in daily_rows if _day(row) < day})
    prior_day = prior_days[-1] if prior_days else ""
    prior = next((row for row in reversed(list(daily_rows)) if _day(row) == prior_day), {})
    if not completed:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "completed_bar_count": 0,
            "feature_max_epoch": None,
            "intraday_ma2_5_cross_state": "INSUFFICIENT_HISTORY",
            "daily_ma5_20_cross_state": _daily_cross(daily_rows, day),
            "above_vwap": None,
            "support_state": "INSUFFICIENT_HISTORY",
            "resistance_state": "INSUFFICIENT_HISTORY",
            "structure": {},
        }
    closes = [float(row.get("close") or 0.0) for row in completed]
    current = closes[-1]
    current_vwap = _vwap(completed)
    prior_high = _number(prior.get("high"))
    prior_low = _number(prior.get("low"))
    opening_high = max(float(row.get("high") or 0.0) for row in completed)
    opening_low = min(float(row.get("low") or current) for row in completed)
    structure = build_chart_structure_features(
        completed,
        current_price=current,
        current_vwap=current_vwap,
        recent_high=max(float(row.get("high") or 0.0) for row in completed[:-1]) if len(completed) > 1 else opening_high,
        volume_ratio=None,
    )
    support_state = "TESTING"
    if prior_low and current < prior_low:
        support_state = "PRIOR_LOW_LOST"
    elif current_vwap and current >= current_vwap and opening_low >= current_vwap * 0.995:
        support_state = "VWAP_SUPPORT"
    elif prior_low and current >= prior_low:
        support_state = "PRIOR_LOW_HOLD"
    resistance_state = "BELOW_RESISTANCE"
    if prior_high and current > prior_high:
        resistance_state = "PRIOR_HIGH_BREAK"
    elif len(completed) > 1 and current >= max(float(row.get("high") or 0.0) for row in completed[:-1]):
        resistance_state = "OPENING_RANGE_BREAK"
    elif prior_high and current >= prior_high * 0.995:
        resistance_state = "PRIOR_HIGH_TEST"
    return {
        "status": "OBSERVED",
        "completed_bar_count": len(completed),
        "feature_max_epoch": max(int(row.get("ts") or 0) + 60 for row in completed),
        "current_price": current,
        "session_vwap": current_vwap,
        "above_vwap": None if current_vwap is None else current >= current_vwap,
        "intraday_ma2_5_cross_state": _cross_state(closes, 2, 5),
        "intraday_ma5_20_cross_state": _cross_state(closes, 5, 20),
        "daily_ma5_20_cross_state": _daily_cross(daily_rows, day),
        "prior_day_high": prior_high,
        "prior_day_low": prior_low,
        "opening_range_high": opening_high,
        "opening_range_low": opening_low,
        "support_state": support_state,
        "resistance_state": resistance_state,
        "structure": structure,
    }
