from __future__ import annotations

from statistics import median
from typing import Any, Iterable


def number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def performance(values: Iterable[Any]) -> dict[str, Any]:
    finite = [value for raw in values if (value := number(raw)) is not None]
    if not finite:
        return {
            "trade_count": 0,
            "win_rate": None,
            "average_return_pct": None,
            "median_return_pct": None,
            "profit_factor": None,
            "cumulative_return_pct": None,
            "max_drawdown_pct": None,
        }
    gains = sum(value for value in finite if value > 0)
    losses = abs(sum(value for value in finite if value < 0))
    equity = peak = 0.0
    drawdown = 0.0
    for value in finite:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return {
        "trade_count": len(finite),
        "win_rate": round(sum(value > 0 for value in finite) / len(finite), 4),
        "average_return_pct": round(sum(finite) / len(finite), 4),
        "median_return_pct": round(median(finite), 4),
        "profit_factor": round(gains / losses, 4)
        if losses
        else (999.0 if gains else None),
        "cumulative_return_pct": round(sum(finite), 4),
        "max_drawdown_pct": round(drawdown, 4),
    }
