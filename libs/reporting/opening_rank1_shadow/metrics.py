from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.research.post_reclaim_alpha.evaluator import summarize_horizon

from .contracts import HORIZONS, PRIMARY_HORIZON, PROMOTION_GATES


def summarize_episodes(episodes: list[Mapping[str, Any]]) -> dict[str, Any]:
    horizons = {
        horizon: summarize_horizon(episodes, horizon)
        for horizon in HORIZONS
    }
    observed_rows: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    by_day: dict[str, list[float]] = defaultdict(list)
    day_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    subgroup_counts: Counter[str] = Counter()
    observability_counts: Counter[str] = Counter()
    exposure_counts: Counter[str] = Counter()
    execution_evidence_counts: Counter[str] = Counter()
    lane_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    lane_status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in episodes:
        observation = row.get("opening_observability")
        observation = (
            observation
            if isinstance(observation, Mapping)
            else {}
        )
        for key in (
            "exact_opening_09_00_04",
            "opening_chase_7pct",
            "late_09_15_19_no_chase",
        ):
            if observation.get(key) is True:
                subgroup_counts[key] += 1
        observability_counts[
            str(observation.get("completed_volume_status") or "MISSING")
        ] += 1
        quote = observation.get("quote_snapshot")
        quote = quote if isinstance(quote, Mapping) else {}
        observability_counts[
            f"quote:{quote.get('status') or 'MISSING'}"
        ] += 1
        asset = observation.get("asset_observation")
        asset = asset if isinstance(asset, Mapping) else {}
        exposure_counts[str(asset.get("exposure_direction") or "UNKNOWN")] += 1
        execution = observation.get("execution_evidence")
        execution = execution if isinstance(execution, Mapping) else {}
        execution_evidence_counts[
            str(execution.get("status") or "MISSING")
        ] += 1
        lanes = observation.get("conditional_lanes")
        lanes = lanes if isinstance(lanes, Mapping) else {}
        for lane_name, lane_value in lanes.items():
            lane = lane_value if isinstance(lane_value, Mapping) else {}
            lane_status_counts[str(lane_name)][
                str(lane.get("status") or "MISSING")
            ] += 1
            if lane.get("eligible") is True:
                lane_rows[str(lane_name)].append(row)
        checkpoints = row.get("checkpoints")
        checkpoints = checkpoints if isinstance(checkpoints, Mapping) else {}
        checkpoint = checkpoints.get(PRIMARY_HORIZON)
        if not isinstance(checkpoint, Mapping) or checkpoint.get("status") != "observed":
            continue
        observed_rows.append((row, checkpoint))
        day = str(row.get("day") or "")
        symbol = str(row.get("symbol") or "")
        value = float(checkpoint.get("live_net_return_pct") or 0.0)
        by_day[day].append(value)
        day_counts[day] += 1
        symbol_counts[symbol] += 1
    observed_count = len(observed_rows)
    positive_days = sum(
        1
        for values in by_day.values()
        if values and sum(values) / len(values) > 0.0
    )
    return {
        "episode_count": len(episodes),
        "observed_30m_count": observed_count,
        "observed_day_count": len(by_day),
        "positive_day_ratio": (
            round(positive_days / len(by_day), 4)
            if by_day
            else 0.0
        ),
        "largest_day_share": (
            round(max(day_counts.values(), default=0) / observed_count, 4)
            if observed_count
            else 0.0
        ),
        "largest_symbol_share": (
            round(max(symbol_counts.values(), default=0) / observed_count, 4)
            if observed_count
            else 0.0
        ),
        "subgroup_counts": dict(subgroup_counts),
        "observability_counts": dict(observability_counts),
        "exposure_counts": dict(exposure_counts),
        "execution_evidence_counts": dict(execution_evidence_counts),
        "conditional_lane_summaries": {
            lane_name: {
                "eligible_episode_count": len(lane_rows.get(lane_name, [])),
                "evidence_status_counts": dict(lane_status_counts[lane_name]),
                "horizons": {
                    horizon: summarize_horizon(
                        lane_rows.get(lane_name, []),
                        horizon,
                    )
                    for horizon in HORIZONS
                },
            }
            for lane_name in sorted(lane_status_counts)
        },
        "horizons": horizons,
    }


def evaluate_promotion(summary: Mapping[str, Any]) -> dict[str, Any]:
    row = (summary.get("horizons") or {}).get(PRIMARY_HORIZON) or {}
    metrics = row.get("live_net") or {}
    values = {
        "observed_count": int(summary.get("observed_30m_count") or 0),
        "observed_day_count": int(summary.get("observed_day_count") or 0),
        "coverage": float(row.get("coverage") or 0.0),
        "win_rate": float(metrics.get("win_rate") or 0.0),
        "average_net_return_pct": float(metrics.get("average_return_pct") or 0.0),
        "profit_factor": float(metrics.get("profit_factor") or 0.0),
        "positive_day_ratio": float(summary.get("positive_day_ratio") or 0.0),
        "largest_day_share": float(summary.get("largest_day_share") or 0.0),
        "largest_symbol_share": float(summary.get("largest_symbol_share") or 0.0),
    }
    evidence_ready = (
        values["observed_count"] >= PROMOTION_GATES["minimum_observed_count"]
        and values["observed_day_count"]
        >= PROMOTION_GATES["minimum_observed_day_count"]
    )
    checks = {
        "coverage": values["coverage"] >= PROMOTION_GATES["minimum_coverage"],
        "win_rate": values["win_rate"] >= PROMOTION_GATES["minimum_win_rate"],
        "average_net_return": (
            values["average_net_return_pct"]
            > PROMOTION_GATES["minimum_average_net_return_pct"]
        ),
        "profit_factor": (
            values["profit_factor"] >= PROMOTION_GATES["minimum_profit_factor"]
        ),
        "positive_day_ratio": (
            values["positive_day_ratio"]
            >= PROMOTION_GATES["minimum_positive_day_ratio"]
        ),
        "day_concentration": (
            values["largest_day_share"]
            <= PROMOTION_GATES["maximum_largest_day_share"]
        ),
        "symbol_concentration": (
            values["largest_symbol_share"]
            <= PROMOTION_GATES["maximum_largest_symbol_share"]
        ),
    }
    if not evidence_ready:
        status = "COLLECTING"
    elif all(checks.values()):
        status = "ELIGIBLE_FOR_CONTROLLED_SHADOW"
    else:
        status = "REJECTED"
    return {
        "status": status,
        "evidence_ready": evidence_ready,
        "values": values,
        "checks": checks,
        "gates": dict(PROMOTION_GATES),
        "behavior_change_authorized": False,
    }


def net_returns(
    episodes: list[Mapping[str, Any]],
    horizon: str = PRIMARY_HORIZON,
) -> list[float]:
    values = []
    for row in episodes:
        checkpoint = ((row.get("checkpoints") or {}).get(horizon))
        if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed":
            values.append(float(checkpoint.get("live_net_return_pct") or 0.0))
    return values


def compact_performance(
    episodes: list[Mapping[str, Any]],
    horizon: str = PRIMARY_HORIZON,
) -> dict[str, Any]:
    return performance_metrics(net_returns(episodes, horizon))
