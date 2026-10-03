from __future__ import annotations

import math
from statistics import mean, median
from typing import Any, Mapping, Sequence


def number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def performance(values: Sequence[Any]) -> dict[str, Any]:
    observed = [value for raw in values if (value := number(raw)) is not None]
    wins = [value for value in observed if value > 0.0]
    losses = [value for value in observed if value < 0.0]
    gross_loss = abs(sum(losses))
    equity = peak = max_drawdown = 0.0
    for value in observed:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "sample_count": len(observed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(observed), 4) if observed else None,
        "avg_net_return_pct": round(mean(observed), 4) if observed else None,
        "median_net_return_pct": round(median(observed), 4) if observed else None,
        "profit_factor": (
            round(sum(wins) / gross_loss, 4)
            if gross_loss
            else 999.0 if wins else 0.0
        ),
        "max_drawdown_pct": round(max_drawdown, 4) if observed else None,
        "total_gain_pct": round(sum(wins), 4),
        "total_loss_pct": round(sum(losses), 4),
    }


def pearson(pairs: Sequence[tuple[Any, Any]]) -> float | None:
    clean = [
        (x, y)
        for raw_x, raw_y in pairs
        if (x := number(raw_x)) is not None and (y := number(raw_y)) is not None
    ]
    if len(clean) < 2:
        return None
    xs = [row[0] for row in clean]
    ys = [row[1] for row in clean]
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in clean)
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs)
        * sum((y - y_mean) ** 2 for y in ys)
    )
    return round(numerator / denominator, 4) if denominator else None


def checkpoint_return(episode: Mapping[str, Any], horizon: str) -> float | None:
    checkpoint = dict(episode.get("checkpoints", {}).get(horizon, {}))
    return number(checkpoint.get("live_net_return_pct"))


def feature_outcome(episode: Mapping[str, Any], horizon: str) -> float | None:
    outcomes = dict(episode.get("outcomes", {}))
    checkpoint = dict(outcomes.get("checkpoints", {}).get(horizon, {}))
    if checkpoint.get("status") != "OBSERVED":
        return None
    return number(checkpoint.get("net_return_pct"))
