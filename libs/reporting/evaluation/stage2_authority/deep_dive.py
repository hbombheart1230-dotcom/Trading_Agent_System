from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from .contracts import EVALUATION_HORIZONS, LIVE_ROUND_TRIP_COST_PCT


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = "missing") -> str:
    text = str(value or "").strip()
    return text or default


def _horizon_values(row: Mapping[str, Any], horizon: str) -> tuple[float | None, float | None, float | None]:
    values = _mapping(_mapping(row.get("horizon_returns")).get(horizon))
    before = values.get("before_return_pct")
    after = values.get("after_return_pct")
    delta = values.get("delta_pct")
    return (
        float(before) if before is not None else None,
        float(after) if after is not None else None,
        float(delta) if delta is not None else None,
    )


def _metrics(records: Sequence[Mapping[str, Any]], horizon: str) -> dict[str, Any]:
    comparable: list[tuple[Mapping[str, Any], float, float, float]] = []
    for row in records:
        before, after, delta = _horizon_values(row, horizon)
        if before is not None and after is not None and delta is not None:
            comparable.append((row, before, after, delta))
    if not comparable:
        return {
            "observation_count": len(records),
            "comparison_count": 0,
            "day_count": 0,
            "before_average_return_pct": None,
            "after_average_return_pct": None,
            "average_delta_pct": None,
        }
    before_values = [item[1] for item in comparable]
    after_values = [item[2] for item in comparable]
    deltas = [item[3] for item in comparable]
    by_day: dict[str, list[float]] = defaultdict(list)
    for row, _before, _after, delta in comparable:
        by_day[_text(row.get("day"))].append(delta)
    day_averages = [sum(values) / len(values) for values in by_day.values()]
    largest_day = max(len(values) for values in by_day.values())
    return {
        "observation_count": len(records),
        "comparison_count": len(comparable),
        "day_count": len(by_day),
        "before_average_return_pct": round(sum(before_values) / len(before_values), 4),
        "before_positive_rate": round(sum(value > 0 for value in before_values) / len(before_values), 4),
        "after_average_return_pct": round(sum(after_values) / len(after_values), 4),
        "after_positive_rate": round(sum(value > 0 for value in after_values) / len(after_values), 4),
        "average_delta_pct": round(sum(deltas) / len(deltas), 4),
        "median_delta_pct": round(median(deltas), 4),
        "positive_delta_rate": round(sum(value > 0 for value in deltas) / len(deltas), 4),
        "negative_day_rate": round(sum(value < 0 for value in day_averages) / len(day_averages), 4),
        "positive_day_rate": round(sum(value > 0 for value in day_averages) / len(day_averages), 4),
        "max_single_day_share": round(largest_day / len(comparable), 4),
    }


def _single_role_metrics(
    records: Sequence[Mapping[str, Any]], horizon: str, *, role: str
) -> dict[str, Any]:
    index = 0 if role == "R1" else 1
    observed: list[tuple[Mapping[str, Any], float]] = []
    for row in records:
        value = _horizon_values(row, horizon)[index]
        if value is not None:
            observed.append((row, value))
    if not observed:
        return {"observation_count": len(records), "observed_count": 0, "day_count": 0}
    values = [value for _row, value in observed]
    net_values = [value - LIVE_ROUND_TRIP_COST_PCT for value in values]
    gross_profit = sum(value for value in net_values if value > 0)
    gross_loss = abs(sum(value for value in net_values if value < 0))
    by_day: dict[str, list[float]] = defaultdict(list)
    for row, value in observed:
        by_day[_text(row.get("day"))].append(value)
    largest_day = max(len(day_values) for day_values in by_day.values())
    return {
        "observation_count": len(records),
        "observed_count": len(values),
        "day_count": len(by_day),
        "average_return_pct": round(sum(values) / len(values), 4),
        "median_return_pct": round(median(values), 4),
        "positive_rate": round(sum(value > 0 for value in values) / len(values), 4),
        "average_live_net_return_pct": round(
            sum(value - LIVE_ROUND_TRIP_COST_PCT for value in values) / len(values), 4
        ),
        "median_live_net_return_pct": round(median(values) - LIVE_ROUND_TRIP_COST_PCT, 4),
        "live_net_positive_rate": round(
            sum(value > LIVE_ROUND_TRIP_COST_PCT for value in values) / len(values), 4
        ),
        "live_net_profit_factor": (
            round(gross_profit / gross_loss, 4)
            if gross_loss > 0
            else None
        ),
        "max_single_day_share": round(largest_day / len(values), 4),
    }


def _market_direction(row: Mapping[str, Any]) -> str:
    metrics = _mapping(_mapping(row.get("before_candidate")).get("market_metrics"))
    values = [metrics.get("kospi_pct"), metrics.get("kosdaq_pct")]
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return "missing"
    average = sum(numeric) / len(numeric)
    if average >= 1.0:
        return "strong_up"
    if average >= 0.3:
        return "up"
    if average <= -1.0:
        return "strong_down"
    if average <= -0.3:
        return "down"
    return "flat_mixed"


def _source_signature(row: Mapping[str, Any]) -> str:
    sources = list(_mapping(row.get("before_candidate")).get("sources") or [])
    return "+".join(sorted(str(value) for value in sources if str(value))) or "missing"


def _source_family(row: Mapping[str, Any]) -> str:
    sources = {
        str(value)
        for value in list(_mapping(row.get("before_candidate")).get("sources") or [])
        if str(value)
    }
    if "top_change_rate" in sources:
        return "contains_top_change_rate"
    activity = bool(sources & {"top_value", "top_volume"})
    theme = "sector_theme" in sources
    if theme and activity:
        return "theme_plus_activity"
    if theme:
        return "sector_theme_only"
    if activity:
        return "liquidity_activity"
    return "other_or_missing"


def _target_alignment(row: Mapping[str, Any]) -> str:
    target = _text(_mapping(row.get("stage2")).get("target_symbol"), "")
    before = _text(row.get("before_symbol"), "")
    after = _text(row.get("after_symbol"), "")
    if not target:
        return "target_missing"
    if target == before == after:
        return "target_r1_r2_same"
    if target == before:
        return "target_matches_r1"
    if target == after:
        return "target_matches_r2"
    return "target_matches_neither"


def _latency_bucket(row: Mapping[str, Any]) -> str:
    value = row.get("stage2_response_delay_sec")
    if not isinstance(value, (int, float)):
        return "missing"
    seconds = float(value)
    if seconds <= 30:
        return "lte_30s"
    if seconds <= 60:
        return "31_60s"
    if seconds <= 120:
        return "61_120s"
    return "gt_120s"


def _score_margin_bucket(row: Mapping[str, Any]) -> str:
    value = row.get("r1_score_margin")
    if not isinstance(value, (int, float)):
        return "missing"
    margin = float(value)
    if margin <= 0.05:
        return "lte_0.05"
    if margin <= 0.15:
        return "0.05_0.15"
    if margin <= 0.30:
        return "0.15_0.30"
    return "gt_0.30"


def _rank_bucket(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "dropped_or_missing"
    rank = int(value)
    if rank == 1:
        return "rank1"
    if rank <= 3:
        return "rank2_3"
    if rank <= 10:
        return "rank4_10"
    return "rank11_plus"


def _r1_risk_bucket(row: Mapping[str, Any]) -> str:
    value = _mapping(row.get("before_candidate")).get("risk_score")
    if not isinstance(value, (int, float)):
        return "missing"
    risk = float(value)
    if risk < 0.70:
        return "lt_0.70"
    if risk < 0.90:
        return "0.70_0.90"
    return "gte_0.90"


def _r1_feature_state(row: Mapping[str, Any], key: str) -> str:
    value = _mapping(_mapping(row.get("before_candidate")).get("score_breakdown")).get(key)
    if not isinstance(value, (int, float)):
        return "missing"
    return "positive" if float(value) > 0 else "zero_or_negative"


DIMENSIONS: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "candidate_relation": lambda row: "same" if not row.get("candidate_changed") else "changed",
    "time_bucket": lambda row: _text(
        _mapping(_mapping(row.get("before_candidate")).get("entry_lane")).get("time_bucket")
    ),
    "market_regime_rail": lambda row: _text(
        _mapping(_mapping(row.get("before_candidate")).get("entry_lane")).get("market_regime_rail")
    ),
    "market_direction": _market_direction,
    "stage2_decision": lambda row: _text(_mapping(row.get("stage2")).get("selected_symbol_decision")),
    "watch_intensity": lambda row: _text(_mapping(row.get("stage2")).get("watch_intensity")),
    "memory_effect": lambda row: _text(_mapping(row.get("stage2")).get("memory_effect")),
    "r1_source_signature": _source_signature,
    "r1_source_family": _source_family,
    "target_alignment": _target_alignment,
    "stage2_latency": _latency_bucket,
    "r1_score_margin": _score_margin_bucket,
    "r1_rank_after_refresh": lambda row: _rank_bucket(row.get("r1_rank_after_refresh")),
    "r2_rank_before_refresh": lambda row: _rank_bucket(row.get("r2_rank_before_refresh")),
    "r1_risk": _r1_risk_bucket,
    "r1_volume_surge": lambda row: _r1_feature_state(row, "volume_surge"),
    "r1_vwap_alignment": lambda row: _r1_feature_state(row, "vwap_alignment"),
    "r1_trading_value": lambda row: _r1_feature_state(row, "trading_value"),
}


def _grouped(records: Sequence[Mapping[str, Any]], key_fn: Callable[[Mapping[str, Any]], str]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        groups[key_fn(row)].append(row)
    output = []
    for value, rows in groups.items():
        metrics = {horizon: _metrics(rows, horizon) for horizon in EVALUATION_HORIZONS}
        output.append({"value": value, "observation_count": len(rows), "by_horizon": metrics})
    return sorted(output, key=lambda item: (-int(item["observation_count"]), str(item["value"])))


def _extremes(records: Sequence[Mapping[str, Any]], *, limit: int = 15) -> dict[str, list[dict[str, Any]]]:
    rows = []
    for row in records:
        before, after, delta = _horizon_values(row, "+30m")
        if delta is None:
            continue
        rows.append(
            {
                "day": row.get("day"),
                "decision_id": row.get("decision_id"),
                "before_symbol": row.get("before_symbol"),
                "after_symbol": row.get("after_symbol"),
                "before_return_pct": before,
                "after_return_pct": after,
                "delta_pct": delta,
                "time_bucket": DIMENSIONS["time_bucket"](row),
                "market_regime_rail": DIMENSIONS["market_regime_rail"](row),
                "stage2_decision": DIMENSIONS["stage2_decision"](row),
                "target_alignment": _target_alignment(row),
            }
        )
    ordered = sorted(rows, key=lambda item: float(item["delta_pct"]))
    return {"worst": ordered[:limit], "best": list(reversed(ordered[-limit:]))}


def _independent_episodes(
    records: Sequence[Mapping[str, Any]], *, cooldown_sec: int = 1800
) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    last_epoch: dict[tuple[str, str], int] = {}
    seen_without_epoch: set[tuple[str, str]] = set()
    ordered = sorted(
        records,
        key=lambda row: (
            _text(row.get("day")),
            int(row.get("decision_epoch") or 0),
            _text(row.get("decision_id")),
        ),
    )
    for row in ordered:
        key = (_text(row.get("day")), _text(row.get("before_symbol")))
        epoch = int(row.get("decision_epoch") or 0)
        if epoch <= 0:
            if key in seen_without_epoch:
                continue
            seen_without_epoch.add(key)
            selected.append(row)
            continue
        prior = last_epoch.get(key)
        if prior is not None and epoch - prior < cooldown_sec:
            continue
        last_epoch[key] = epoch
        selected.append(row)
    return selected


def build_stage2_effectiveness_deep_dive(
    *, start: str, end: str, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    attributable = [row for row in records if bool(row.get("stage2_response_available"))]
    changed = [row for row in attributable if bool(row.get("candidate_changed"))]
    same = [row for row in attributable if not bool(row.get("candidate_changed"))]
    independent_attributable = _independent_episodes(attributable)
    independent_changed = _independent_episodes(changed)
    independent_same = _independent_episodes(same)
    independent_all_refresh = _independent_episodes(records)
    independent_without_top_change = [
        row
        for row in independent_all_refresh
        if "top_change_rate" not in _source_signature(row)
    ]

    def without_extreme_r1(horizon: str) -> list[Mapping[str, Any]]:
        return [
            row
            for row in independent_all_refresh
            if (value := _horizon_values(row, horizon)[0]) is not None and abs(value) < 15.0
        ]
    dimensions = {
        name: {
            "all_attributable": _grouped(attributable, key_fn),
            "candidate_changed_only": _grouped(changed, key_fn),
        }
        for name, key_fn in DIMENSIONS.items()
    }
    return {
        "schema_version": "strategist_stage2_effectiveness_deep_dive.v1",
        "behavior_effect": "evaluation_only",
        "range": {"start": start, "end": end},
        "role_definition": {
            "R1": "first Scanner Top-1 after Stage-1 and before Stage-2 tactical refresh",
            "R2": "Scanner Top-1 after Stage-2 tactical refresh and Scanner rerun",
            "important_boundary": "R2 is a Scanner result under Stage-2 policy, not necessarily an LLM-explicit symbol replacement.",
        },
        "coverage": {
            "refresh_records": len(records),
            "stage2_attributable_records": len(attributable),
            "same_symbol_records": len(same),
            "changed_symbol_records": len(changed),
            "independent_stage2_episodes_30m": len(independent_attributable),
            "independent_same_symbol_episodes_30m": len(independent_same),
            "independent_changed_symbol_episodes_30m": len(independent_changed),
        },
        "stage1_r1_absolute_all_refresh": {
            "return_basis": "gross forward return before trading cost",
            "live_round_trip_cost_pct": LIVE_ROUND_TRIP_COST_PCT,
            "by_horizon": {
                horizon: _single_role_metrics(records, horizon, role="R1")
                for horizon in EVALUATION_HORIZONS
            },
        },
        "stage1_r1_absolute_independent_30m": {
            "return_basis": "gross forward return before trading cost",
            "live_round_trip_cost_pct": LIVE_ROUND_TRIP_COST_PCT,
            "definition": "first decision per day and R1 symbol, then a 30-minute cooldown",
            "by_horizon": {
                horizon: _single_role_metrics(independent_all_refresh, horizon, role="R1")
                for horizon in EVALUATION_HORIZONS
            },
        },
        "stage1_r1_sensitivity": {
            "exclude_top_change_rate_source": {
                horizon: _single_role_metrics(
                    independent_without_top_change, horizon, role="R1"
                )
                for horizon in EVALUATION_HORIZONS
            },
            "exclude_abs_gross_return_gte_15pct": {
                horizon: _single_role_metrics(
                    without_extreme_r1(horizon), horizon, role="R1"
                )
                for horizon in EVALUATION_HORIZONS
            },
        },
        "overall_by_horizon": {
            horizon: _metrics(attributable, horizon) for horizon in EVALUATION_HORIZONS
        },
        "same_symbol_by_horizon": {
            horizon: _metrics(same, horizon) for horizon in EVALUATION_HORIZONS
        },
        "changed_symbol_by_horizon": {
            horizon: _metrics(changed, horizon) for horizon in EVALUATION_HORIZONS
        },
        "independent_30m_cooldown": {
            "definition": "first decision per day and R1 symbol, then a 30-minute cooldown",
            "all_by_horizon": {
                horizon: _metrics(independent_attributable, horizon)
                for horizon in EVALUATION_HORIZONS
            },
            "same_symbol_by_horizon": {
                horizon: _metrics(independent_same, horizon)
                for horizon in EVALUATION_HORIZONS
            },
            "changed_symbol_by_horizon": {
                horizon: _metrics(independent_changed, horizon)
                for horizon in EVALUATION_HORIZONS
            },
            "changed_dimensions": {
                name: _grouped(independent_changed, key_fn)
                for name, key_fn in DIMENSIONS.items()
            },
        },
        "dimensions": dimensions,
        "extreme_changed_cases_30m": _extremes(changed),
        "interpretation_contract": [
            "Same-symbol R1/R2 outcomes measure consensus quality, not Stage-2 causal alpha.",
            "Changed-symbol paired deltas measure the refresh path, but only directly linked Stage-2 responses are attributable.",
            "A subgroup is exploratory until it passes sample distribution, day consistency, and out-of-sample validation.",
            "Overlapping windows are not independent; promotion decisions must use the 30-minute cooldown episode view.",
            "Entry tightening and no-trade effectiveness remain unidentifiable without explicit adoption and untreated controls.",
        ],
    }
