from __future__ import annotations

import statistics
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


KST = timezone(timedelta(hours=9))


def _same_day(epoch: int, day: str) -> bool:
    return datetime.fromtimestamp(epoch, tz=KST).date().isoformat() == day


def completed_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
    day: str,
    timestamps: Sequence[int] | None = None,
) -> list[Mapping[str, Any]]:
    current_minute = (int(decision_epoch) // 60) * 60
    epochs = (
        timestamps
        if timestamps is not None
        else [int(row.get("ts") or 0) for row in rows]
    )
    try:
        day_start = int(
            datetime.fromisoformat(f"{day}T00:00:00").replace(tzinfo=KST).timestamp()
        )
    except Exception:
        return []
    start_index = bisect_left(epochs, day_start)
    end_index = bisect_left(epochs, current_minute)
    return list(rows[start_index:end_index])


def entry_bar(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
    day: str,
    timestamps: Sequence[int] | None = None,
) -> Mapping[str, Any] | None:
    epochs = (
        timestamps
        if timestamps is not None
        else [int(row.get("ts") or 0) for row in rows]
    )
    # A point-in-time decision cannot be filled at the open of a candle that
    # has already started. Use the first complete timestamp after the decision.
    index = bisect_right(epochs, int(decision_epoch))
    if index >= len(rows):
        return None
    row = rows[index]
    return row if _same_day(int(row.get("ts") or 0), day) else None


def relative_strength_features(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
    day: str,
    timestamps: Sequence[int] | None = None,
) -> dict[str, Any]:
    usable = completed_rows(
        rows,
        decision_epoch=decision_epoch,
        day=day,
        timestamps=timestamps,
    )
    if len(usable) < 12:
        return {"available": False, "reason": "insufficient_completed_minutes"}
    current = usable[-1]
    close = float(current.get("close") or 0.0)
    close_5m = float(usable[-6].get("close") or 0.0)
    volumes = [
        float(row.get("volume") or 0.0)
        for row in usable[-11:-1]
        if float(row.get("volume") or 0.0) > 0.0
    ]
    median_volume = float(statistics.median(volumes)) if volumes else 0.0
    current_volume = float(current.get("volume") or 0.0)
    session = [
        row
        for row in usable
        if float(row.get("volume") or 0.0) > 0.0
    ]
    total_volume = sum(float(row.get("volume") or 0.0) for row in session)
    vwap = (
        sum(
            float(row.get("close") or 0.0) * float(row.get("volume") or 0.0)
            for row in session
        )
        / total_volume
        if total_volume > 0.0
        else close
    )
    return {
        "available": bool(close > 0.0 and close_5m > 0.0),
        "return_5m_pct": round((close / close_5m - 1.0) * 100.0, 6)
        if close > 0.0 and close_5m > 0.0
        else None,
        "volume_ratio": round(current_volume / median_volume, 6)
        if median_volume > 0.0
        else None,
        "turnover": round(close * current_volume, 6),
        "close": close,
        "vwap": round(vwap, 6),
        "above_vwap": close >= vwap,
        "feature_epoch": int(current.get("ts") or 0),
    }


def contraction_breakout_features(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
    day: str,
    timestamps: Sequence[int] | None = None,
) -> dict[str, Any]:
    usable = completed_rows(
        rows,
        decision_epoch=decision_epoch,
        day=day,
        timestamps=timestamps,
    )
    if len(usable) < 21:
        return {"available": False, "reason": "insufficient_completed_minutes"}
    latest_five = usable[-5:]
    prior_fifteen = usable[-20:-5]
    current = usable[-1]
    prior_ten = usable[-11:-1]

    def range_pct(row: Mapping[str, Any]) -> float:
        close = max(float(row.get("close") or 0.0), 1.0)
        return (
            float(row.get("high") or close) - float(row.get("low") or close)
        ) / close * 100.0

    latest_range = sum(range_pct(row) for row in latest_five) / 5.0
    prior_range = sum(range_pct(row) for row in prior_fifteen) / 15.0
    close = float(current.get("close") or 0.0)
    prior_high = max(float(row.get("high") or 0.0) for row in prior_ten)
    prior_volumes = [
        float(row.get("volume") or 0.0)
        for row in prior_ten
        if float(row.get("volume") or 0.0) > 0.0
    ]
    median_volume = float(statistics.median(prior_volumes)) if prior_volumes else 0.0
    current_volume = float(current.get("volume") or 0.0)
    contraction_ratio = latest_range / prior_range if prior_range > 0.0 else None
    volume_ratio = current_volume / median_volume if median_volume > 0.0 else None
    breakout_pct = (
        (close / prior_high - 1.0) * 100.0 if close > 0.0 and prior_high > 0.0 else None
    )
    return {
        "available": bool(
            contraction_ratio is not None
            and volume_ratio is not None
            and breakout_pct is not None
        ),
        "contraction_ratio": round(contraction_ratio, 6)
        if contraction_ratio is not None
        else None,
        "volume_ratio": round(volume_ratio, 6)
        if volume_ratio is not None
        else None,
        "breakout_pct": round(breakout_pct, 6)
        if breakout_pct is not None
        else None,
        "contraction_ok": bool(
            contraction_ratio is not None and contraction_ratio <= 0.75
        ),
        "breakout_ok": bool(breakout_pct is not None and breakout_pct > 0.0),
        "volume_ok": bool(volume_ratio is not None and volume_ratio >= 1.50),
        "feature_epoch": int(current.get("ts") or 0),
    }
