from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ReturnStatistics:
    trade_count: int
    resolved_count: int
    unresolved_count: int
    win_count: int
    loss_count: int
    flat_count: int
    average_return: float | None
    average_gain: float | None
    average_loss: float | None
    profit_factor: float | None
    max_drawdown: float | None


def trusted_net_return(row: dict[str, Any]) -> float | None:
    value = row.get("return")
    if row.get("return_basis") != "truth_surface_net":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def trusted_net_pnl(row: dict[str, Any]) -> float | None:
    value = row.get("pnl")
    if row.get("return_basis") != "truth_surface_net":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def calculate_return_statistics(rows: Iterable[dict[str, Any]]) -> ReturnStatistics:
    materialized = list(rows)
    values = [value for row in materialized if (value := trusted_net_return(row)) is not None]
    gains = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    flat_count = len(values) - len(gains) - len(losses)
    return ReturnStatistics(
        trade_count=len(materialized),
        resolved_count=len(values),
        unresolved_count=len(materialized) - len(values),
        win_count=len(gains),
        loss_count=len(losses),
        flat_count=flat_count,
        average_return=_mean(values),
        average_gain=_mean(gains),
        average_loss=_mean(losses),
        profit_factor=_profit_factor(gains, losses),
        max_drawdown=_max_drawdown(values),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _profit_factor(gains: list[float], losses: list[float]) -> float | None:
    if not gains or not losses:
        return None
    return sum(gains) / abs(sum(losses))


def _max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown
