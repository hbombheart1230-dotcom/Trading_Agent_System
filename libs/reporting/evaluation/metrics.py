from __future__ import annotations

from typing import Iterable


def performance_metrics(values: Iterable[float]) -> dict[str, float | int]:
    rows = [float(value) for value in values]
    gains = [value for value in rows if value > 0]
    losses = [value for value in rows if value < 0]
    gross_gain = sum(gains)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    for value in rows:
        equity += value
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity - peak)
    return {
        "count": len(rows),
        "win_count": len(gains),
        "loss_count": len(losses),
        "flat_count": len(rows) - len(gains) - len(losses),
        "win_rate": round(len(gains) / len(rows), 4) if rows else 0.0,
        "average_return_pct": round(sum(rows) / len(rows), 4) if rows else 0.0,
        "average_gain_pct": round(gross_gain / len(gains), 4) if gains else 0.0,
        "average_loss_pct": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "profit_factor": round(gross_gain / gross_loss, 4) if gross_loss else (999.0 if gross_gain else 0.0),
        "expectancy_pct": round(sum(rows) / len(rows), 4) if rows else 0.0,
        "maximum_drawdown_pct": round(maximum_drawdown, 4),
    }
