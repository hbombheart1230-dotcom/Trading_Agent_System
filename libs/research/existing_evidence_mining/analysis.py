from __future__ import annotations

from collections import defaultdict
from collections import Counter
from statistics import median
from typing import Any, Iterable, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import HORIZONS, LIVE_COST_PCT, PATH_POLICIES, PRIMARY_HORIZON


def _observed_return(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoints = row.get("checkpoints") if isinstance(row.get("checkpoints"), Mapping) else {}
    checkpoint = checkpoints.get(horizon)
    if not isinstance(checkpoint, Mapping) or checkpoint.get("status") != "observed":
        return None
    return float(checkpoint.get("live_net_return_pct") or 0.0)


def summarize_rows(rows: list[Mapping[str, Any]], horizon: str) -> dict[str, Any]:
    observed = []
    for row in rows:
        value = _observed_return(row, horizon)
        if value is None:
            continue
        checkpoint = (row.get("checkpoints") or {}).get(horizon) or {}
        observed.append(
            {
                "return_pct": value,
                "gross_return_pct": float(checkpoint.get("gross_return_pct") or 0.0),
                "mfe_pct": float(checkpoint.get("mfe_pct") or 0.0),
                "mae_pct": float(checkpoint.get("mae_pct") or 0.0),
            }
        )
    by_day: dict[str, list[float]] = defaultdict(list)
    day_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    for row in rows:
        value = _observed_return(row, horizon)
        if value is None:
            continue
        day = str(row.get("day") or "")
        symbol = str(row.get("symbol") or "")
        by_day[day].append(value)
        day_counts[day] += 1
        symbol_counts[symbol] += 1
    positive_days = sum(1 for values in by_day.values() if sum(values) / len(values) > 0.0)
    return {
        "population_count": len(rows),
        "observed_count": len(observed),
        "coverage": round(len(observed) / len(rows), 4) if rows else 0.0,
        "metrics": performance_metrics(item["return_pct"] for item in observed),
        "gross_metrics": performance_metrics(item["gross_return_pct"] for item in observed),
        "average_mfe_pct": round(sum(item["mfe_pct"] for item in observed) / len(observed), 4)
        if observed
        else None,
        "average_mae_pct": round(sum(item["mae_pct"] for item in observed) / len(observed), 4)
        if observed
        else None,
        "day_count": len(by_day),
        "positive_day_ratio": round(positive_days / len(by_day), 4) if by_day else 0.0,
        "largest_day_share": round(max(day_counts.values(), default=0) / len(observed), 4)
        if observed
        else 0.0,
        "largest_symbol_share": round(max(symbol_counts.values(), default=0) / len(observed), 4)
        if observed
        else 0.0,
    }


def grouped_horizon_summary(
    episodes: list[Mapping[str, Any]],
    *,
    field: str,
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in episodes:
        value = row.get(field)
        values: Iterable[Any] = value if isinstance(value, list) else [value]
        for item in values:
            key = str(item or "missing")
            grouped[key].append(row)
    return {
        key: {horizon: summarize_rows(rows, horizon) for horizon in HORIZONS}
        for key, rows in sorted(grouped.items())
    }


def split_summary(
    episodes: list[Mapping[str, Any]],
    *,
    field: str,
    calibration_end: str,
    retrospective_start: str,
) -> dict[str, Any]:
    return {
        "calibration": grouped_horizon_summary(
            [row for row in episodes if str(row.get("day") or "") <= calibration_end],
            field=field,
        ),
        "retrospective": grouped_horizon_summary(
            [row for row in episodes if str(row.get("day") or "") >= retrospective_start],
            field=field,
        ),
    }


def score_component_diagnostics(episodes: list[Mapping[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[tuple[float, Mapping[str, Any]]]] = defaultdict(list)
    for row in episodes:
        if _observed_return(row, PRIMARY_HORIZON) is None:
            continue
        for name, raw in dict(row.get("score_breakdown") or {}).items():
            try:
                values[str(name)].append((float(raw), row))
            except Exception:
                continue
    output: dict[str, Any] = {}
    for name, pairs in sorted(values.items()):
        if len(pairs) < 30:
            continue
        threshold = median(value for value, _ in pairs)
        low = [row for value, row in pairs if value < threshold]
        high = [row for value, row in pairs if value >= threshold]
        if len(low) < 15 or len(high) < 15 or len({value for value, _ in pairs}) < 3:
            continue
        low_summary = summarize_rows(low, PRIMARY_HORIZON)
        high_summary = summarize_rows(high, PRIMARY_HORIZON)
        output[name] = {
            "median": round(float(threshold), 6),
            "low": low_summary,
            "high": high_summary,
            "high_minus_low_expectancy_pct": round(
                float((high_summary.get("metrics") or {}).get("expectancy_pct") or 0.0)
                - float((low_summary.get("metrics") or {}).get("expectancy_pct") or 0.0),
                4,
            ),
        }
    return output


def discovery_cohorts(episodes: list[Mapping[str, Any]]) -> dict[str, Any]:
    cohorts = {
        "opening_all": [row for row in episodes if row.get("time_bucket") == "open_0_20m"],
        "opening_rank1": [
            row
            for row in episodes
            if row.get("time_bucket") == "open_0_20m" and row.get("rank_bucket") == "rank1"
        ],
        "opening_rank2_3": [
            row
            for row in episodes
            if row.get("time_bucket") == "open_0_20m" and row.get("rank_bucket") == "rank2_3"
        ],
    }
    output: dict[str, Any] = {}
    for name, rows in cohorts.items():
        output[name] = {
            "overall": {horizon: summarize_rows(rows, horizon) for horizon in HORIZONS},
            "calibration": {
                horizon: summarize_rows(
                    [row for row in rows if str(row.get("day") or "") <= "2026-07-10"],
                    horizon,
                )
                for horizon in HORIZONS
            },
            "retrospective": {
                horizon: summarize_rows(
                    [row for row in rows if str(row.get("day") or "") >= "2026-07-13"],
                    horizon,
                )
                for horizon in HORIZONS
            },
        }
    return output


def blocked_opportunity_analysis(samples: list[Mapping[str, Any]]) -> dict[str, Any]:
    def checkpoint_for(row: Mapping[str, Any], horizon: str) -> Mapping[str, Any] | None:
        direct = row.get("checkpoints") if isinstance(row.get("checkpoints"), Mapping) else {}
        checkpoint = direct.get(horizon)
        if isinstance(checkpoint, Mapping):
            return checkpoint
        shadow = row.get("shadow_forward_outcome")
        shadow = shadow if isinstance(shadow, Mapping) else {}
        checkpoints = shadow.get("checkpoints") if isinstance(shadow.get("checkpoints"), Mapping) else {}
        checkpoint = checkpoints.get(horizon)
        return checkpoint if isinstance(checkpoint, Mapping) else None

    def classify(field: str) -> dict[str, Any]:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in samples:
            grouped[str(row.get(field) or "missing")].append(row)
        result: dict[str, Any] = {}
        for key, rows in sorted(grouped.items()):
            horizons: dict[str, Any] = {}
            for horizon in HORIZONS[:-1]:
                observed = []
                for row in rows:
                    checkpoint = checkpoint_for(row, horizon)
                    if isinstance(checkpoint, Mapping) and checkpoint.get("status") == "observed":
                        gross = float(
                            checkpoint.get("gross_return_pct")
                            if checkpoint.get("gross_return_pct") is not None
                            else checkpoint.get("return_pct") or 0.0
                        )
                        observed.append(
                            {
                                "net": gross - LIVE_COST_PCT,
                                "gross": gross,
                                "mfe": float(checkpoint.get("mfe_pct") or 0.0),
                                "mae": float(checkpoint.get("mae_pct") or 0.0),
                                "day": str(row.get("q16_day") or ""),
                                "symbol": str(row.get("symbol") or ""),
                            }
                        )
                day_counts = Counter(item["day"] for item in observed)
                symbol_counts = Counter(item["symbol"] for item in observed)
                horizons[horizon] = {
                    "population_count": len(rows),
                    "observed_count": len(observed),
                    "coverage": round(len(observed) / len(rows), 4) if rows else 0.0,
                    "net_metrics": performance_metrics(item["net"] for item in observed),
                    "gross_metrics": performance_metrics(item["gross"] for item in observed),
                    "average_mfe_pct": round(sum(item["mfe"] for item in observed) / len(observed), 4)
                    if observed
                    else None,
                    "average_mae_pct": round(sum(item["mae"] for item in observed) / len(observed), 4)
                    if observed
                    else None,
                    "blocked_net_winner_rate": round(
                        sum(1 for item in observed if item["net"] > 0.0) / len(observed),
                        4,
                    )
                    if observed
                    else 0.0,
                    "day_count": len(day_counts),
                    "symbol_count": len(symbol_counts),
                    "largest_day_share": round(
                        max(day_counts.values(), default=0) / len(observed), 4
                    )
                    if observed
                    else 0.0,
                    "largest_symbol_share": round(
                        max(symbol_counts.values(), default=0) / len(observed), 4
                    )
                    if observed
                    else 0.0,
                }
            result[key] = horizons
        return result

    return {
        "sample_count": len(samples),
        "by_disposition": classify("opportunity_disposition"),
        "by_reason": classify("reason"),
        "by_primary_failure_axis": classify("primary_failure_axis"),
        "by_entry_lane": classify("entry_lane"),
        "by_cost_floor_state": classify("entry_quant_cost_floor_state"),
    }


def simulate_path_policies(
    episodes: list[Mapping[str, Any]],
    *,
    minute_rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    policy_returns: dict[str, list[float]] = defaultdict(list)
    policy_reasons: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for episode in episodes:
        symbol = str(episode.get("symbol") or "")
        day = str(episode.get("day") or "")
        baseline_epoch = int(episode.get("baseline_epoch") or 0)
        baseline_price = float(episode.get("baseline_price") or 0.0)
        rows = [
            row
            for row in minute_rows_by_symbol.get(symbol) or []
            if baseline_epoch <= int(row.get("ts") or 0) <= baseline_epoch + 30 * 60
            and str(row.get("raw_ts") or "")[:8] in ("", day.replace("-", ""))
        ]
        if not rows or baseline_price <= 0.0:
            continue
        for policy in PATH_POLICIES:
            target = baseline_price * (1.0 + float(policy["target_pct"]) / 100.0)
            stop = baseline_price * (1.0 - float(policy["stop_pct"]) / 100.0)
            exit_price = float(rows[-1].get("close") or baseline_price)
            reason = "time_exit"
            for bar in rows:
                low_hit = float(bar.get("low") or exit_price) <= stop
                high_hit = float(bar.get("high") or exit_price) >= target
                if low_hit:
                    exit_price = stop
                    reason = "stop"
                    break
                if high_hit:
                    exit_price = target
                    reason = "target"
                    break
            net = (exit_price / baseline_price - 1.0) * 100.0 - LIVE_COST_PCT
            policy_id = str(policy["policy_id"])
            policy_returns[policy_id].append(net)
            policy_reasons[policy_id][reason] += 1
    return {
        policy_id: {
            "metrics": performance_metrics(values),
            "exit_reasons": dict(policy_reasons[policy_id]),
            "conservative_same_bar_rule": "stop_before_target",
        }
        for policy_id, values in sorted(policy_returns.items())
    }


def actual_trade_analysis(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    realized = []
    eligible = []
    early = 0
    violation = 0
    hold_values = []
    ranks: dict[str, list[float]] = defaultdict(list)
    early_returns: list[float] = []
    compliant_returns: list[float] = []
    horizon_returns: dict[str, list[float]] = defaultdict(list)
    hold_bucket_returns: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        outcome = row.get("realized_outcome") if isinstance(row.get("realized_outcome"), Mapping) else {}
        if outcome.get("net_return_pct") is None:
            continue
        value = float(outcome.get("net_return_pct") or 0.0)
        realized.append(value)
        integrity = row.get("integrity") if isinstance(row.get("integrity"), Mapping) else {}
        if bool(integrity.get("promotion_metric_eligible")):
            eligible.append(value)
        horizon = row.get("horizon_alignment") if isinstance(row.get("horizon_alignment"), Mapping) else {}
        hold = outcome.get("holding_seconds")
        if hold is not None:
            hold_values.append(float(hold))
        if bool(horizon.get("exited_before_min_hold")):
            early += 1
            early_returns.append(value)
        else:
            compliant_returns.append(value)
        if bool(horizon.get("horizon_violation_candidate")):
            violation += 1
        rank = int(((row.get("selection_context") or {}).get("selected_rank")) or 0)
        if rank > 0:
            ranks[f"rank{rank}"].append(value)
        strategy_horizon = str(horizon.get("strategy_horizon") or "missing")
        horizon_returns[strategy_horizon].append(value)
        hold_seconds = float(hold or 0.0)
        if hold_seconds < 60:
            hold_bucket = "under_60s"
        elif hold_seconds < 300:
            hold_bucket = "60_300s"
        elif hold_seconds < 1800:
            hold_bucket = "300_1800s"
        else:
            hold_bucket = "1800s_plus"
        hold_bucket_returns[hold_bucket].append(value)
    count = len(realized)
    return {
        "trade_count": count,
        "all_realized": performance_metrics(realized),
        "promotion_eligible": performance_metrics(eligible),
        "promotion_eligible_rate": round(len(eligible) / count, 4) if count else 0.0,
        "before_min_hold_count": early,
        "before_min_hold_rate": round(early / count, 4) if count else 0.0,
        "horizon_violation_count": violation,
        "horizon_violation_rate": round(violation / count, 4) if count else 0.0,
        "average_holding_seconds": round(sum(hold_values) / len(hold_values), 2) if hold_values else None,
        "by_selected_rank": {key: performance_metrics(values) for key, values in sorted(ranks.items())},
        "early_exit_metrics": performance_metrics(early_returns),
        "min_hold_compliant_metrics": performance_metrics(compliant_returns),
        "by_strategy_horizon": {
            key: performance_metrics(values) for key, values in sorted(horizon_returns.items())
        },
        "by_hold_bucket": {
            key: performance_metrics(values) for key, values in sorted(hold_bucket_returns.items())
        },
    }
