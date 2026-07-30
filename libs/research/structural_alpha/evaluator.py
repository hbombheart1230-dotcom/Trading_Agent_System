from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.research.post_reclaim_alpha.evaluator import evaluate_episodes

from .contracts import (
    CALIBRATION_END,
    CALIBRATION_START,
    GATES,
    HORIZONS,
    PRIMARY_HORIZON,
    RETROSPECTIVE_END,
    RETROSPECTIVE_START,
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


def _summary(
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
                    "day": str(row.get("day") or ""),
                    "symbol": str(row.get("symbol") or ""),
                    "return_pct": float(
                        checkpoint.get("live_net_return_pct") or 0.0
                    ),
                    "gross_return_pct": float(
                        checkpoint.get("gross_return_pct") or 0.0
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


def _gate_results(
    calibration: Mapping[str, Any],
    retrospective: Mapping[str, Any],
) -> dict[str, bool]:
    calibration_metrics = calibration.get("metrics") or {}
    retrospective_metrics = retrospective.get("metrics") or {}
    return {
        "calibration_observed_count": int(
            calibration.get("observed_count") or 0
        )
        >= GATES["minimum_calibration_observed_count"],
        "retrospective_observed_count": int(
            retrospective.get("observed_count") or 0
        )
        >= GATES["minimum_retrospective_observed_count"],
        "calibration_coverage": float(calibration.get("coverage") or 0.0)
        >= GATES["minimum_forward_coverage"],
        "retrospective_coverage": float(retrospective.get("coverage") or 0.0)
        >= GATES["minimum_forward_coverage"],
        "calibration_expectancy": float(
            calibration_metrics.get("expectancy_pct") or 0.0
        )
        > GATES["minimum_calibration_expectancy_pct"],
        "retrospective_expectancy": float(
            retrospective_metrics.get("expectancy_pct") or 0.0
        )
        > GATES["minimum_retrospective_expectancy_pct"],
        "retrospective_profit_factor": float(
            retrospective_metrics.get("profit_factor") or 0.0
        )
        >= GATES["minimum_retrospective_profit_factor"],
        "retrospective_positive_day_ratio": float(
            retrospective.get("positive_day_ratio") or 0.0
        )
        >= GATES["minimum_retrospective_positive_day_ratio"],
        "retrospective_mdd": float(
            retrospective_metrics.get("maximum_drawdown_pct") or 0.0
        )
        >= GATES["minimum_retrospective_mdd_pct"],
        "retrospective_day_concentration": float(
            retrospective.get("largest_single_day_share") or 0.0
        )
        <= GATES["maximum_retrospective_single_day_share"],
        "retrospective_symbol_concentration": float(
            retrospective.get("largest_single_symbol_share") or 0.0
        )
        <= GATES["maximum_retrospective_single_symbol_share"],
    }


def evaluate_strategy(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    evaluated = evaluate_episodes(
        episodes,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    splits = {
        "calibration": {
            horizon: _summary(
                evaluated,
                start=CALIBRATION_START,
                end=CALIBRATION_END,
                horizon=horizon,
            )
            for horizon in HORIZONS
        },
        "retrospective": {
            horizon: _summary(
                evaluated,
                start=RETROSPECTIVE_START,
                end=RETROSPECTIVE_END,
                horizon=horizon,
            )
            for horizon in HORIZONS
        },
    }
    gates = _gate_results(
        splits["calibration"][PRIMARY_HORIZON],
        splits["retrospective"][PRIMARY_HORIZON],
    )
    return {
        "episode_count": len(evaluated),
        "day_count": len({str(row.get("day") or "") for row in evaluated}),
        "symbol_count": len({str(row.get("symbol") or "") for row in evaluated}),
        "primary_horizon": PRIMARY_HORIZON,
        "splits": splits,
        "gate_results": gates,
        "decision": (
            "FUTURE_CONFIRMATION_REQUIRED" if all(gates.values()) else "REJECT"
        ),
        "episodes": evaluated,
    }


def sector_not_testable_result() -> dict[str, Any]:
    return {
        "decision": "NOT_TESTABLE_MISSING_POINT_IN_TIME_SECTOR_MEMBERSHIP",
        "reason": (
            "Historical Q9 artifacts do not retain point-in-time sector/theme "
            "membership and breadth. Current mappings cannot be backfilled."
        ),
        "episode_count": 0,
        "day_count": 0,
        "symbol_count": 0,
        "splits": {},
        "gate_results": {},
    }
