from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.research.post_reclaim_alpha.evaluator import evaluate_episodes

from .contracts import (
    GATES,
    HORIZONS,
    LIVE_COST_PCT,
    PRIMARY_HORIZON,
    TRAIN_END,
    TRAIN_START,
    VALIDATION_END,
    VALIDATION_START,
)


def _positive_day_ratio(rows: list[Mapping[str, Any]]) -> float:
    by_day: dict[str, list[float]] = {}
    for row in rows:
        by_day.setdefault(str(row["day"]), []).append(float(row["return_pct"]))
    if not by_day:
        return 0.0
    positive = sum(
        1 for values in by_day.values() if sum(values) / len(values) > 0.0
    )
    return round(positive / len(by_day), 4)


def _split_horizon(
    episodes: list[Mapping[str, Any]],
    *,
    start: str,
    end: str,
    horizon: str,
) -> dict[str, Any]:
    population = [
        row for row in episodes if start <= str(row.get("day") or "") <= end
    ]
    observed: list[dict[str, Any]] = []
    for row in population:
        checkpoint = (row.get("checkpoints") or {}).get(horizon)
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed":
            observed.append(
                {
                    "episode_id": row.get("episode_id"),
                    "day": str(row.get("day") or ""),
                    "symbol": str(row.get("symbol") or ""),
                    "gross_return_pct": float(
                        checkpoint.get("gross_return_pct") or 0.0
                    ),
                    "return_pct": float(
                        checkpoint.get("live_net_return_pct") or 0.0
                    ),
                    "mfe_pct": float(checkpoint.get("mfe_pct") or 0.0),
                    "mae_pct": float(checkpoint.get("mae_pct") or 0.0),
                }
            )
    count = len(observed)
    day_counts = Counter(row["day"] for row in observed)
    symbol_counts = Counter(row["symbol"] for row in observed)
    return {
        "population_count": len(population),
        "observed_count": count,
        "coverage": round(count / len(population), 4) if population else 0.0,
        "metrics": performance_metrics(row["return_pct"] for row in observed),
        "gross_metrics": performance_metrics(
            row["gross_return_pct"] for row in observed
        ),
        "average_mfe_pct": round(
            sum(row["mfe_pct"] for row in observed) / count, 4
        )
        if count
        else None,
        "average_mae_pct": round(
            sum(row["mae_pct"] for row in observed) / count, 4
        )
        if count
        else None,
        "positive_day_ratio": _positive_day_ratio(observed),
        "largest_single_day_share": round(
            max(day_counts.values(), default=0) / count if count else 0.0,
            4,
        ),
        "largest_single_symbol_share": round(
            max(symbol_counts.values(), default=0) / count if count else 0.0,
            4,
        ),
        "observations": observed,
    }


def _gates(
    train: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, bool]:
    train_metrics = train.get("metrics") or {}
    validation_metrics = validation.get("metrics") or {}
    return {
        "train_observed_count": int(train.get("observed_count") or 0)
        >= GATES["minimum_train_observed_count"],
        "validation_observed_count": int(validation.get("observed_count") or 0)
        >= GATES["minimum_validation_observed_count"],
        "train_coverage": float(train.get("coverage") or 0.0)
        >= GATES["minimum_forward_coverage"],
        "validation_coverage": float(validation.get("coverage") or 0.0)
        >= GATES["minimum_forward_coverage"],
        "train_expectancy": float(train_metrics.get("expectancy_pct") or 0.0)
        > GATES["minimum_train_live_expectancy_pct"],
        "validation_expectancy": float(
            validation_metrics.get("expectancy_pct") or 0.0
        )
        > GATES["minimum_validation_live_expectancy_pct"],
        "validation_profit_factor": float(
            validation_metrics.get("profit_factor") or 0.0
        )
        >= GATES["minimum_validation_profit_factor"],
        "validation_positive_day_ratio": float(
            validation.get("positive_day_ratio") or 0.0
        )
        >= GATES["minimum_validation_positive_day_ratio"],
        "validation_mdd": float(
            validation_metrics.get("maximum_drawdown_pct") or 0.0
        )
        >= GATES["minimum_validation_mdd_pct"],
        "validation_day_concentration": float(
            validation.get("largest_single_day_share") or 0.0
        )
        <= GATES["maximum_validation_single_day_share"],
        "validation_symbol_concentration": float(
            validation.get("largest_single_symbol_share") or 0.0
        )
        <= GATES["maximum_validation_single_symbol_share"],
    }


def evaluate_hypothesis(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    evaluated = evaluate_episodes(
        episodes,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    splits: dict[str, Any] = {}
    for split, start, end in (
        ("train", TRAIN_START, TRAIN_END),
        ("validation", VALIDATION_START, VALIDATION_END),
    ):
        splits[split] = {
            horizon: _split_horizon(
                evaluated,
                start=start,
                end=end,
                horizon=horizon,
            )
            for horizon in HORIZONS
        }
    train_primary = splits["train"][PRIMARY_HORIZON]
    validation_primary = splits["validation"][PRIMARY_HORIZON]
    gate_results = _gates(train_primary, validation_primary)
    return {
        "episode_count": len(evaluated),
        "day_count": len({str(row.get("day") or "") for row in evaluated}),
        "symbol_count": len({str(row.get("symbol") or "") for row in evaluated}),
        "cost_pct": LIVE_COST_PCT,
        "primary_horizon": PRIMARY_HORIZON,
        "splits": splits,
        "gate_results": gate_results,
        "decision": (
            "ELIGIBLE_FOR_SHADOW_INTEGRATION"
            if all(gate_results.values())
            else "REJECT"
        ),
        "episodes": evaluated,
    }
