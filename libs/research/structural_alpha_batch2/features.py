from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

from libs.research.structural_alpha.features import completed_rows


def _close(row: Mapping[str, Any]) -> float:
    return float(row.get("close") or 0.0)


def _volume_ratio(rows: Sequence[Mapping[str, Any]]) -> float | None:
    if len(rows) < 11:
        return None
    prior = [
        float(row.get("volume") or 0.0)
        for row in rows[-11:-1]
        if float(row.get("volume") or 0.0) > 0.0
    ]
    median = float(statistics.median(prior)) if prior else 0.0
    return float(rows[-1].get("volume") or 0.0) / median if median > 0.0 else None


def market_return_15m(
    rows: Sequence[Mapping[str, Any]],
    *,
    decision_epoch: int,
    day: str,
    timestamps: Sequence[int] | None = None,
) -> float | None:
    usable = completed_rows(
        rows,
        decision_epoch=decision_epoch,
        day=day,
        timestamps=timestamps,
    )
    if len(usable) < 16:
        return None
    current = _close(usable[-1])
    prior = _close(usable[-16])
    if current <= 0.0 or prior <= 0.0:
        return None
    return round((current / prior - 1.0) * 100.0, 6)


def oversold_reversal_features(
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
    if len(usable) < 16:
        return {"available": False, "reason": "insufficient_completed_minutes"}
    closes = [_close(row) for row in usable[-15:]]
    if any(value <= 0.0 for value in closes):
        return {"available": False, "reason": "invalid_close"}
    deltas = [right - left for left, right in zip(closes, closes[1:])]
    average_gain = sum(max(delta, 0.0) for delta in deltas) / 14.0
    average_loss = sum(max(-delta, 0.0) for delta in deltas) / 14.0
    if average_loss == 0.0:
        rsi = 100.0
    else:
        relative_strength = average_gain / average_loss
        rsi = 100.0 - 100.0 / (1.0 + relative_strength)
    volume_ratio = _volume_ratio(usable)
    rebound_pct = (closes[-1] / closes[-2] - 1.0) * 100.0
    return {
        "available": volume_ratio is not None,
        "rsi_14": round(rsi, 6),
        "rebound_1m_pct": round(rebound_pct, 6),
        "volume_ratio": round(volume_ratio, 6)
        if volume_ratio is not None
        else None,
        "oversold_ok": rsi <= 30.0,
        "reversal_ok": closes[-1] > closes[-2],
        "volume_ok": bool(volume_ratio is not None and volume_ratio >= 1.0),
        "feature_epoch": int(usable[-1].get("ts") or 0),
    }


def trend_pullback_features(
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
    if len(usable) < 26:
        return {"available": False, "reason": "insufficient_completed_minutes"}
    closes = [_close(row) for row in usable]
    if any(value <= 0.0 for value in closes[-25:]):
        return {"available": False, "reason": "invalid_close"}
    sma5 = sum(closes[-5:]) / 5.0
    previous_sma5 = sum(closes[-6:-1]) / 5.0
    sma20 = sum(closes[-20:]) / 20.0
    prior_sma20 = sum(closes[-25:-5]) / 20.0
    current = usable[-1]
    previous = usable[-2]
    current_close = closes[-1]
    previous_close = closes[-2]
    previous_high = float(previous.get("high") or previous_close)
    volume_ratio = _volume_ratio(usable)
    trend_spread = (sma5 / sma20 - 1.0) * 100.0
    return {
        "available": volume_ratio is not None,
        "sma5": round(sma5, 6),
        "sma20": round(sma20, 6),
        "prior_sma20": round(prior_sma20, 6),
        "trend_spread_pct": round(trend_spread, 6),
        "trend_ok": sma5 > sma20 and sma20 > prior_sma20,
        "pullback_reclaim_ok": (
            previous_close <= previous_sma5 and current_close > sma5
        ),
        "resume_ok": bool(
            current_close > previous_high
            and volume_ratio is not None
            and volume_ratio >= 1.0
        ),
        "volume_ratio": round(volume_ratio, 6)
        if volume_ratio is not None
        else None,
        "feature_epoch": int(current.get("ts") or 0),
    }
