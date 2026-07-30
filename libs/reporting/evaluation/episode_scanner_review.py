from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Any, Mapping, Sequence

from libs.reporting.q8_evaluation_contract import candidate_day

from .metrics import performance_metrics
from .scanner_quality import SCANNER_HORIZONS, pre_strategist_candidate_rows


RANK_BUCKETS = ("rank1", "rank2_3", "rank4_plus", "unknown")


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _checkpoint_return(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoints = _mapping(_mapping(row.get("shadow_forward_outcome")).get("checkpoints"))
    checkpoint = _mapping(checkpoints.get(horizon))
    if str(checkpoint.get("status") or "") != "observed":
        return None
    return _number(checkpoint.get("return_pct"))


def _epoch(row: Mapping[str, Any]) -> int:
    base = _mapping(row.get("shadow_forward_base"))
    value = _number(base.get("baseline_epoch"))
    return int(value or 0)


def _setup_key(row: Mapping[str, Any]) -> str:
    lane = _mapping(row.get("entry_lane_observation"))
    return str(
        lane.get("subtype_v2")
        or lane.get("subtype")
        or lane.get("primary_lane")
        or row.get("reason")
        or "unknown"
    )


def _day(row: Mapping[str, Any]) -> str:
    value = candidate_day(row) or str(row.get("day") or "")
    value = value.replace("-", "")
    return value if len(value) == 8 and value.isdigit() else ""


def _rank_bucket(rank: int) -> str:
    if rank == 1:
        return "rank1"
    if 2 <= rank <= 3:
        return "rank2_3"
    if rank >= 4:
        return "rank4_plus"
    return "unknown"


def _episode_representatives(
    rows: Sequence[Mapping[str, Any]],
    *,
    episode_gap_sec: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        day = _day(row)
        symbol = str(row.get("symbol") or "")
        if not day or not symbol:
            continue
        grouped[(day, symbol, _setup_key(row))].append(row)

    episodes: list[dict[str, Any]] = []
    for (day, symbol, setup), candidates in sorted(grouped.items()):
        previous_epoch: int | None = None
        episode_index = 0
        for row in sorted(candidates, key=lambda item: (_epoch(item), int(_number(item.get("rank")) or 999))):
            current_epoch = _epoch(row)
            if (
                previous_epoch is None
                or current_epoch <= 0
                or previous_epoch <= 0
                or current_epoch - previous_epoch > episode_gap_sec
            ):
                episode_index += 1
                rank = int(_number(row.get("rank")) or 0)
                episodes.append(
                    {
                        "episode_id": f"{day}:{symbol}:{setup}:{episode_index}",
                        "day": day,
                        "symbol": symbol,
                        "setup": setup,
                        "baseline_epoch": current_epoch or None,
                        "rank": rank or None,
                        "rank_bucket": _rank_bucket(rank),
                        "score_breakdown": dict(
                            _mapping(row.get("score_breakdown"))
                        ),
                        "sources": [
                            str(value)
                            for value in row.get("q9_candidate_sources")
                            or row.get("sources")
                            or []
                            if str(value)
                        ],
                        "returns": {
                            horizon: _checkpoint_return(row, horizon)
                            for horizon in SCANNER_HORIZONS
                        },
                    }
                )
            previous_epoch = current_epoch
    return episodes


def build_episode_scanner_review(
    payloads: list[dict[str, Any]],
    *,
    mock_drag_pct: float,
    live_drag_pct: float,
    episode_gap_sec: int = 900,
    prepared_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = (
        [dict(row) for row in prepared_rows]
        if prepared_rows is not None
        else pre_strategist_candidate_rows(payloads)
    )
    episodes = _episode_representatives(rows, episode_gap_sec=episode_gap_sec)
    output: list[dict[str, Any]] = []
    for bucket in RANK_BUCKETS:
        bucket_rows = [row for row in episodes if row["rank_bucket"] == bucket]
        for horizon in SCANNER_HORIZONS:
            gross = [
                float(row["returns"][horizon])
                for row in bucket_rows
                if row["returns"].get(horizon) is not None
            ]
            output.append(
                {
                    "rank_bucket": bucket,
                    "horizon": horizon,
                    "episode_count": len(bucket_rows),
                    "observed_count": len(gross),
                    "observed_day_count": len(
                        {
                            row["day"]
                            for row in bucket_rows
                            if row["returns"].get(horizon) is not None
                        }
                    ),
                    "gross": performance_metrics(gross),
                    "live_net": performance_metrics(
                        [value - float(live_drag_pct) for value in gross]
                    ),
                    "mock_net": performance_metrics(
                        [value - float(mock_drag_pct) for value in gross]
                    ),
                }
            )

    observed_30m_episodes = [
        row for row in episodes if row["returns"].get("+30m") is not None
    ]
    component_covered = [
        row for row in observed_30m_episodes if row.get("score_breakdown")
    ]
    component_values: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for row in component_covered:
        outcome = float(row["returns"]["+30m"])
        for key, raw in row["score_breakdown"].items():
            value = _number(raw)
            if value is not None:
                component_values[str(key)].append((value, outcome, row["day"]))

    component_rows: list[dict[str, Any]] = []
    for component, values in component_values.items():
        xs = [value for value, _, _ in values]
        ys = [outcome for _, outcome, _ in values]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        covariance = sum(
            (value - x_mean) * (outcome - y_mean)
            for value, outcome, _ in values
        )
        x_scale = sqrt(sum((value - x_mean) ** 2 for value in xs))
        y_scale = sqrt(sum((outcome - y_mean) ** 2 for outcome in ys))
        correlation = covariance / (x_scale * y_scale) if x_scale and y_scale else None
        component_rows.append(
            {
                "component": component,
                "observed_count": len(values),
                "observed_day_count": len({day for _, _, day in values}),
                "avg_score_contribution": round(x_mean, 6),
                "avg_gross_return_30m_pct": round(y_mean, 4),
                "avg_live_net_return_30m_pct": round(
                    y_mean - float(live_drag_pct), 4
                ),
                "score_return_correlation": (
                    round(correlation, 4) if correlation is not None else None
                ),
            }
        )
    component_rows.sort(
        key=lambda row: (
            int(row["observed_count"]),
            abs(float(row["score_return_correlation"] or 0.0)),
        ),
        reverse=True,
    )
    component_coverage = (
        len(component_covered) / len(observed_30m_episodes)
        if observed_30m_episodes
        else 0.0
    )
    rank1_30m = next(
        (
            row
            for row in output
            if row["rank_bucket"] == "rank1" and row["horizon"] == "+30m"
        ),
        {},
    )
    rank23_30m = next(
        (
            row
            for row in output
            if row["rank_bucket"] == "rank2_3" and row["horizon"] == "+30m"
        ),
        {},
    )
    rank1_value = _number(_mapping(rank1_30m.get("gross")).get("expectancy_pct"))
    rank23_value = _number(_mapping(rank23_30m.get("gross")).get("expectancy_pct"))
    return {
        "schema_version": "episode_scanner_review.v1",
        "behavior_effect": "evaluation_only",
        "episode_gap_sec": int(episode_gap_sec),
        "raw_candidate_row_count": len(rows),
        "episode_count": len(episodes),
        "compression_ratio": round(len(episodes) / len(rows), 4) if rows else 0.0,
        "cost_drag_pct": {
            "mock": round(float(mock_drag_pct), 6),
            "live": round(float(live_drag_pct), 6),
        },
        "rank_horizon_rows": output,
        "score_component_review": {
            "status": (
                "READY"
                if len(component_covered) >= 20 and component_coverage >= 0.70
                else "NOT_READY_MISSING_SCORE_COMPONENT_ARTIFACT"
            ),
            "forward_observed_episode_count": len(observed_30m_episodes),
            "component_covered_episode_count": len(component_covered),
            "coverage": round(component_coverage, 4),
            "rows": component_rows,
        },
        "rank1_minus_rank2_3_gross_30m_pct": (
            round(rank1_value - rank23_value, 4)
            if rank1_value is not None and rank23_value is not None
            else None
        ),
        "episodes": episodes,
        "limitations": [
            "An episode is the first observation after a 15-minute same-symbol/setup gap.",
            "Episodes reduce serial duplication but are not randomized independent trades.",
            "This report does not change Scanner ranking or execution.",
        ],
    }


def build_same_symbol_reentry_review(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    unique: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        trade_id = str(row.get("trade_id") or "")
        if trade_id:
            unique[trade_id] = row

    grouped: dict[tuple[str, str], list[tuple[int, float, str]]] = defaultdict(list)
    for trade_id, row in unique.items():
        parts = trade_id.split("_")
        if len(parts) < 4 or not parts[1].isdigit():
            continue
        value = _number(row.get("net_return_pct"))
        symbol = str(row.get("symbol") or "")
        if value is None or not symbol:
            continue
        try:
            sequence = int(parts[-1])
        except ValueError:
            sequence = 0
        grouped[(parts[1], symbol)].append((sequence, value, trade_id))

    first_values: list[float] = []
    repeat_values: list[float] = []
    repeat_after_loss_values: list[float] = []
    repeat_after_non_loss_values: list[float] = []
    repeated_groups = 0
    for values in grouped.values():
        ordered = sorted(values)
        first_values.append(ordered[0][1])
        for index, (_, value, _) in enumerate(ordered[1:], start=1):
            repeat_values.append(value)
            prior_value = ordered[index - 1][1]
            if prior_value < 0.0:
                repeat_after_loss_values.append(value)
            else:
                repeat_after_non_loss_values.append(value)
        if len(ordered) > 1:
            repeated_groups += 1

    first_metrics = performance_metrics(first_values)
    repeat_metrics = performance_metrics(repeat_values)
    repeat_after_loss_metrics = performance_metrics(repeat_after_loss_values)
    repeat_after_non_loss_metrics = performance_metrics(repeat_after_non_loss_values)
    return {
        "schema_version": "same_symbol_reentry_review.v1",
        "behavior_effect": "evaluation_only",
        "day_symbol_group_count": len(grouped),
        "repeated_day_symbol_group_count": repeated_groups,
        "first_entry": first_metrics,
        "repeat_entry": repeat_metrics,
        "repeat_after_loss": repeat_after_loss_metrics,
        "repeat_after_non_loss": repeat_after_non_loss_metrics,
        "repeat_minus_first_expectancy_pct": round(
            float(repeat_metrics.get("expectancy_pct") or 0.0)
            - float(first_metrics.get("expectancy_pct") or 0.0),
            4,
        ),
        "behavior_candidate_eligible": bool(
            len(repeat_after_loss_values) >= 20
            and float(repeat_after_loss_metrics.get("expectancy_pct") or 0.0)
            < float(first_metrics.get("expectancy_pct") or 0.0) - 0.20
            and float(repeat_after_loss_metrics.get("win_rate") or 0.0)
            < float(first_metrics.get("win_rate") or 0.0)
        ),
        "limitations": [
            "This is an observational prior-outcome-conditioned comparison.",
            "It supports damage reduction, not a claim that a cooldown creates alpha.",
        ],
    }


__all__ = [
    "build_episode_scanner_review",
    "build_same_symbol_reentry_review",
]
