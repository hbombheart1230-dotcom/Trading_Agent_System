from __future__ import annotations

from collections import Counter
from math import isfinite
from statistics import median
from typing import Any, Iterable, Mapping


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def performance(values: Iterable[Any]) -> dict[str, Any]:
    observed = [value for item in values if (value := number(item)) is not None]
    wins = [value for value in observed if value > 0]
    losses = [value for value in observed if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    running = peak = max_drawdown = 0.0
    for value in observed:
        running += value
        peak = max(peak, running)
        max_drawdown = min(max_drawdown, running - peak)
    return {
        "count": len(observed),
        "win_rate": round(len(wins) / len(observed), 4) if observed else None,
        "average_pct": round(sum(observed) / len(observed), 4) if observed else None,
        "median_pct": round(median(observed), 4) if observed else None,
        "profit_factor": round(gross_profit / gross_loss, 4)
        if gross_loss
        else (999.0 if gross_profit else None),
        "max_drawdown_pct": round(max_drawdown, 4) if observed else None,
    }


def evidence_profile(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    days = Counter(str(row.get("day") or "") for row in rows)
    symbols = Counter(str(row.get("symbol") or "") for row in rows)
    count = len(rows)
    return {
        "day_count": len([key for key in days if key]),
        "symbol_count": len([key for key in symbols if key]),
        "largest_day_share": round(max(days.values()) / count, 4) if count else None,
        "largest_symbol_share": round(max(symbols.values()) / count, 4)
        if count
        else None,
    }


def positive_day_rate(rows: list[Mapping[str, Any]], field: str) -> float | None:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        value = number(row.get(field))
        day = str(row.get("day") or "")
        if value is not None and day:
            grouped.setdefault(day, []).append(value)
    if not grouped:
        return None
    positive = sum(sum(values) / len(values) > 0 for values in grouped.values())
    return round(positive / len(grouped), 4)


def evidence_status(
    metrics: Mapping[str, Any], profile: Mapping[str, Any]
) -> str:
    count = int(metrics.get("count") or 0)
    days = int(profile.get("day_count") or 0)
    symbols = int(profile.get("symbol_count") or 0)
    if count < 5 or days < 3:
        return "INSUFFICIENT_EVIDENCE"
    if count < 10 or days < 5 or symbols < 5:
        return "DESCRIPTIVE_ONLY"
    return "SCREENABLE"
