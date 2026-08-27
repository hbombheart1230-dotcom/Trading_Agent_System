from __future__ import annotations

from bisect import bisect_right
from statistics import fmean, pstdev
from typing import Any, Mapping


DIRECT_SOURCES = ("btc_krw", "btc_usd")


def _mean(values: list[float]) -> float | None:
    return round(fmean(values), 6) if values else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _prior_price(rows: list[Mapping[str, Any]], epoch: int) -> float | None:
    epochs = [int(row.get("ts") or 0) for row in rows]
    index = bisect_right(epochs, epoch) - 1
    if index < 0:
        return None
    price = float(rows[index].get("price") or rows[index].get("close") or 0.0)
    return price if price > 0.0 else None


def _source_context(rows: list[Mapping[str, Any]], *, epoch: int) -> dict[str, Any]:
    eligible = sorted(
        (row for row in rows if 0 < int(row.get("ts") or 0) <= epoch),
        key=lambda row: int(row.get("ts") or 0),
    )
    if not eligible:
        return {"available": False}
    latest = eligible[-1]
    latest_epoch = int(latest.get("ts") or 0)
    current = float(latest.get("price") or latest.get("close") or 0.0)
    recent_60m = [row for row in eligible if int(row.get("ts") or 0) >= epoch - 3600]
    recent_6h = [row for row in eligible if int(row.get("ts") or 0) >= epoch - 6 * 3600]
    recent_24h = [row for row in eligible if int(row.get("ts") or 0) >= epoch - 24 * 3600]
    returns_5m = [
        float(row["momentum_5m_pct"])
        for row in recent_60m
        if row.get("momentum_5m_pct") is not None
    ]
    positive_ratio = (
        sum(1 for value in returns_5m if value > 0.0) / len(returns_5m)
        if returns_5m
        else None
    )
    prior_4h = _prior_price(eligible, epoch - 4 * 3600)
    momentum_4h = (
        ((current / prior_4h) - 1.0) * 100.0
        if current > 0.0 and prior_4h
        else None
    )
    high_6h = max(
        (float(row.get("price") or row.get("close") or 0.0) for row in recent_6h),
        default=0.0,
    )
    high_24h = max(
        (float(row.get("price") or row.get("close") or 0.0) for row in recent_24h),
        default=0.0,
    )
    drawdown_6h = ((current / high_6h) - 1.0) * 100.0 if current > 0.0 and high_6h else None
    drawdown_24h = ((current / high_24h) - 1.0) * 100.0 if current > 0.0 and high_24h else None
    prior_15m_rows = [row for row in eligible if int(row.get("ts") or 0) <= epoch - 15 * 60]
    prior_momentum_15m = (
        float(prior_15m_rows[-1]["momentum_15m_pct"])
        if prior_15m_rows and prior_15m_rows[-1].get("momentum_15m_pct") is not None
        else None
    )
    latest_momentum_15m = (
        float(latest["momentum_15m_pct"])
        if latest.get("momentum_15m_pct") is not None
        else None
    )
    return {
        "available": current > 0.0,
        "latest_epoch": latest_epoch,
        "age_sec": max(0, epoch - latest_epoch),
        "momentum_4h_pct": round(momentum_4h, 6) if momentum_4h is not None else None,
        "positive_5m_ratio_60m": round(positive_ratio, 6) if positive_ratio is not None else None,
        "realized_5m_volatility_60m": round(pstdev(returns_5m), 6) if len(returns_5m) >= 2 else None,
        "drawdown_from_6h_high_pct": round(drawdown_6h, 6) if drawdown_6h is not None else None,
        "drawdown_from_24h_high_pct": round(drawdown_24h, 6) if drawdown_24h is not None else None,
        "momentum_15m_delta_pct": (
            round(latest_momentum_15m - prior_momentum_15m, 6)
            if latest_momentum_15m is not None and prior_momentum_15m is not None
            else None
        ),
        "observation_count_60m": len(recent_60m),
    }


def build_recent_btc_trend_context(
    payload: Mapping[str, Any],
    *,
    epoch: int,
    momentum_15m: float | None,
    momentum_60m: float | None,
    momentum_24h: float | None,
) -> dict[str, Any]:
    sources = payload.get("sources") if isinstance(payload.get("sources"), Mapping) else {}
    contexts: dict[str, dict[str, Any]] = {}
    for name in DIRECT_SOURCES:
        rows = sources.get(name) if isinstance(sources.get(name), list) else []
        context = _source_context(rows, epoch=epoch)
        if context.get("available"):
            contexts[name] = context
    basis = list(contexts.values())

    def aggregate(field: str) -> float | None:
        return _mean([float(row[field]) for row in basis if row.get(field) is not None])

    momentum_4h = aggregate("momentum_4h_pct")
    positive_ratio = aggregate("positive_5m_ratio_60m")
    volatility = aggregate("realized_5m_volatility_60m")
    drawdown_6h = aggregate("drawdown_from_6h_high_pct")
    drawdown_24h = aggregate("drawdown_from_24h_high_pct")
    acceleration = aggregate("momentum_15m_delta_pct")
    direction_values = (momentum_15m, momentum_60m, momentum_4h, momentum_24h)
    observed_directions = [value for value in direction_values if value is not None]
    alignment_ratio = (
        sum(1 for value in observed_directions if value > 0.0) / len(observed_directions)
        if observed_directions
        else None
    )
    location_score = (
        _clamp(1.0 - abs(min(0.0, drawdown_6h)) / 3.0)
        if drawdown_6h is not None
        else 0.0
    )
    acceleration_score = (
        _clamp((acceleration + 0.5) / 1.0) if acceleration is not None else 0.0
    )
    trend_score = (
        0.40 * float(alignment_ratio or 0.0)
        + 0.30 * float(positive_ratio or 0.0)
        + 0.15 * location_score
        + 0.15 * acceleration_score
    )
    persistent = bool(
        momentum_15m is not None
        and momentum_15m > 0.0
        and momentum_60m is not None
        and momentum_60m >= 0.5
        and momentum_4h is not None
        and momentum_4h > 0.0
        and positive_ratio is not None
        and positive_ratio >= 0.60
        and drawdown_6h is not None
        and drawdown_6h >= -1.5
    )
    accelerating = bool(
        momentum_15m is not None
        and momentum_15m > 0.0
        and momentum_60m is not None
        and momentum_60m > 0.0
        and acceleration is not None
        and acceleration >= 0.20
        and positive_ratio is not None
        and positive_ratio >= 0.55
    )
    extended_fading = bool(
        momentum_24h is not None
        and momentum_24h >= 3.0
        and momentum_15m is not None
        and momentum_15m <= 0.0
        and acceleration is not None
        and acceleration <= 0.0
    )
    state = (
        "extended_fading"
        if extended_fading
        else "persistent_uptrend"
        if persistent
        else "accelerating_uptrend"
        if accelerating
        else "mixed_or_unconfirmed"
        if basis
        else "insufficient_evidence"
    )
    return {
        "schema_version": "q12_btc_recent_trend_context.v1",
        "behavior_effect": "observation_only",
        "available": bool(basis),
        "source_count": len(basis),
        "state": state,
        "trend_score": round(trend_score, 6),
        "alignment_ratio": round(alignment_ratio, 6) if alignment_ratio is not None else None,
        "positive_5m_ratio_60m": positive_ratio,
        "momentum_4h_pct": momentum_4h,
        "momentum_15m_delta_pct": acceleration,
        "realized_5m_volatility_60m": volatility,
        "drawdown_from_6h_high_pct": drawdown_6h,
        "drawdown_from_24h_high_pct": drawdown_24h,
        "persistent_uptrend": persistent,
        "accelerating_uptrend": accelerating,
        "extended_fading": extended_fading,
        "sources": contexts,
    }
