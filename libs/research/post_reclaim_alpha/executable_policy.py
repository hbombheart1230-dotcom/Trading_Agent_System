from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import (
    EXECUTABLE_POLICY,
    EXECUTABLE_POLICY_GATES,
    EXECUTABLE_POLICY_SCHEMA_VERSION,
    LIVE_COST_PCT,
    TARGET_SUBTYPE,
)


KST = timezone(timedelta(hours=9))


def _day_for_epoch(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=KST).date().isoformat()


def _prior_print_minutes(
    *,
    rows: list[Mapping[str, Any]],
    baseline_epoch: int,
    day: str,
    lookback_minutes: int,
) -> int:
    lower = baseline_epoch - lookback_minutes * 60
    return len(
        {
            int(row.get("ts") or 0) // 60
            for row in rows
            if lower <= int(row.get("ts") or 0) < baseline_epoch
            and _day_for_epoch(int(row.get("ts") or 0)) == day
        }
    )


def apply_executable_filter(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    lookback = int(EXECUTABLE_POLICY["lookback_minutes"])
    minimum_prints = int(EXECUTABLE_POLICY["minimum_print_minutes"])
    output: list[dict[str, Any]] = []
    for raw in episodes:
        row = dict(raw)
        symbol = str(row.get("symbol") or "")
        epoch = int(row.get("baseline_epoch") or 0)
        day = str(row.get("day") or "")
        print_minutes = _prior_print_minutes(
            rows=list(minute_rows_by_symbol.get(symbol) or []),
            baseline_epoch=epoch,
            day=day,
            lookback_minutes=lookback,
        )
        row["executable_policy"] = {
            "lookback_minutes": lookback,
            "prior_print_minutes": print_minutes,
            "print_density": round(print_minutes / lookback, 4),
            "minimum_print_minutes": minimum_prints,
            "eligible": print_minutes >= minimum_prints,
            "reason": (
                "eligible"
                if print_minutes >= minimum_prints
                else "insufficient_pre_entry_print_density"
            ),
        }
        output.append(row)
    return output


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


def _day_bootstrap(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_day: dict[str, list[float]] = {}
    for row in rows:
        by_day.setdefault(str(row["day"]), []).append(float(row["return_pct"]))
    days = sorted(by_day)
    sample_count = int(EXECUTABLE_POLICY["bootstrap_samples"])
    if not days:
        return {
            "method": "day_cluster_bootstrap",
            "seed": int(EXECUTABLE_POLICY["bootstrap_seed"]),
            "samples": sample_count,
            "p10_expectancy_pct": None,
            "median_expectancy_pct": None,
            "p90_expectancy_pct": None,
        }
    rng = random.Random(int(EXECUTABLE_POLICY["bootstrap_seed"]))
    estimates: list[float] = []
    for _ in range(sample_count):
        values = [
            value
            for _day in range(len(days))
            for value in by_day[rng.choice(days)]
        ]
        estimates.append(sum(values) / len(values))
    estimates.sort()

    def percentile(fraction: float) -> float:
        index = round((len(estimates) - 1) * fraction)
        return round(estimates[index], 4)

    return {
        "method": "day_cluster_bootstrap",
        "seed": int(EXECUTABLE_POLICY["bootstrap_seed"]),
        "samples": sample_count,
        "p10_expectancy_pct": percentile(0.10),
        "median_expectancy_pct": percentile(0.50),
        "p90_expectancy_pct": percentile(0.90),
    }


def _split_summary(
    episodes: list[Mapping[str, Any]],
    *,
    start: str,
    end: str,
    require_eligible: bool = True,
) -> dict[str, Any]:
    population = [
        row
        for row in episodes
        if start <= str(row.get("day") or "") <= end
        and (
            not require_eligible
            or bool((row.get("executable_policy") or {}).get("eligible"))
        )
    ]
    observed: list[dict[str, Any]] = []
    horizon = str(EXECUTABLE_POLICY["exit_horizon"])
    for row in population:
        checkpoint = (row.get("checkpoints") or {}).get(horizon)
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed":
            observed.append(
                {
                    "episode_id": row.get("episode_id"),
                    "day": str(row.get("day") or ""),
                    "symbol": str(row.get("symbol") or ""),
                    "return_pct": float(
                        checkpoint.get("live_net_return_pct") or 0.0
                    ),
                }
            )
    day_counts = Counter(row["day"] for row in observed)
    symbol_counts = Counter(row["symbol"] for row in observed)
    count = len(observed)
    return {
        "range": {"start": start, "end": end},
        "population": "executable_filter" if require_eligible else "unfiltered",
        "eligible_count": len(population),
        "observed_count": count,
        "coverage": round(count / len(population), 4) if population else 0.0,
        "metrics": performance_metrics(row["return_pct"] for row in observed),
        "positive_day_ratio": _positive_day_ratio(observed),
        "largest_single_day_share": round(
            max(day_counts.values(), default=0) / count if count else 0.0,
            4,
        ),
        "largest_single_symbol_share": round(
            max(symbol_counts.values(), default=0) / count if count else 0.0,
            4,
        ),
        "bootstrap": _day_bootstrap(observed),
        "observations": observed,
    }


def _gate_results(
    train: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, bool]:
    train_metrics = train.get("metrics") or {}
    validation_metrics = validation.get("metrics") or {}
    gates = EXECUTABLE_POLICY_GATES
    return {
        "train_observed_count": int(train.get("observed_count") or 0)
        >= gates["minimum_train_observed_count"],
        "validation_observed_count": int(validation.get("observed_count") or 0)
        >= gates["minimum_validation_observed_count"],
        "train_forward_coverage": float(train.get("coverage") or 0.0)
        >= gates["minimum_forward_coverage"],
        "validation_forward_coverage": float(validation.get("coverage") or 0.0)
        >= gates["minimum_forward_coverage"],
        "train_live_expectancy": float(train_metrics.get("expectancy_pct") or 0.0)
        > gates["minimum_train_live_expectancy_pct"],
        "validation_live_expectancy": float(
            validation_metrics.get("expectancy_pct") or 0.0
        )
        > gates["minimum_validation_live_expectancy_pct"],
        "validation_profit_factor": float(
            validation_metrics.get("profit_factor") or 0.0
        )
        >= gates["minimum_validation_profit_factor"],
        "validation_positive_day_ratio": float(
            validation.get("positive_day_ratio") or 0.0
        )
        >= gates["minimum_validation_positive_day_ratio"],
        "validation_mdd": float(
            validation_metrics.get("maximum_drawdown_pct") or 0.0
        )
        >= gates["minimum_validation_mdd_pct"],
        "validation_day_concentration": float(
            validation.get("largest_single_day_share") or 0.0
        )
        <= gates["maximum_validation_single_day_share"],
        "validation_symbol_concentration": float(
            validation.get("largest_single_symbol_share") or 0.0
        )
        <= gates["maximum_validation_single_symbol_share"],
    }


def evaluate_executable_policy(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    annotated = apply_executable_filter(
        episodes,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    train = _split_summary(
        annotated,
        start=str(EXECUTABLE_POLICY["train_start"]),
        end=str(EXECUTABLE_POLICY["train_end"]),
    )
    validation = _split_summary(
        annotated,
        start=str(EXECUTABLE_POLICY["validation_start"]),
        end=str(EXECUTABLE_POLICY["validation_end"]),
    )
    unfiltered = {
        "train": _split_summary(
            annotated,
            start=str(EXECUTABLE_POLICY["train_start"]),
            end=str(EXECUTABLE_POLICY["train_end"]),
            require_eligible=False,
        ),
        "validation": _split_summary(
            annotated,
            start=str(EXECUTABLE_POLICY["validation_start"]),
            end=str(EXECUTABLE_POLICY["validation_end"]),
            require_eligible=False,
        ),
    }
    gate_results = _gate_results(train, validation)
    decision = "PASS_CONTROLLED_ADOPTION" if all(gate_results.values()) else "REJECT"
    return {
        "schema_version": EXECUTABLE_POLICY_SCHEMA_VERSION,
        "behavior_effect": "research_only",
        "target_subtype": TARGET_SUBTYPE,
        "policy": {
            **EXECUTABLE_POLICY,
            "cost_pct": LIVE_COST_PCT,
            "entry_filter": (
                "at least 12 distinct one-minute prints in the 15 minutes "
                "strictly before the candidate timestamp"
            ),
            "exit_rule": "close at first valid +30m print within 180 seconds",
        },
        "fixed_gates": dict(EXECUTABLE_POLICY_GATES),
        "train": train,
        "validation": validation,
        "unfiltered_comparison": unfiltered,
        "gate_results": gate_results,
        "decision": decision,
        "episodes": annotated,
    }
