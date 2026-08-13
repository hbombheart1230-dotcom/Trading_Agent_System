from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, Mapping, Sequence

from .integrity import value_at


SCANNER_FEATURES = (
    "scanner.score_band",
    "scanner.risk_band",
    "scanner.relative_volume_band",
    "scanner.source_top_volume",
    "scanner.source_top_value",
    "scanner.source_top_change_rate",
    "market.exposure_alignment",
    "market.engine_regime",
)
ENTRY_FEATURES = (
    "chart.above_vwap",
    "chart.intraday_ma2_5_cross_state",
    "chart.intraday_ma5_20_cross_state",
    "chart.daily_ma5_20_cross_state",
    "chart.support_state",
    "chart.resistance_state",
    "scanner.relative_volume_band",
)
HORIZON_FEATURES = (
    "strategy.entry_horizon",
    "chart.intraday_ma2_5_cross_state",
    "chart.daily_ma5_20_cross_state",
    "chart.support_state",
    "chart.resistance_state",
    "market.engine_regime",
)
HORIZONS = ("+15m", "+30m", "+60m", "+120m", "+180m", "EOD", "NEXT_OPEN", "D+1_EOD", "D+3_EOD", "D+5_EOD")


def _target(row: Mapping[str, Any], label: str) -> float | None:
    value = value_at(row, f"outcomes.checkpoints.{label}.net_return_pct")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _metrics(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, Any]:
    values = [value for row in rows if (value := _target(row, label)) is not None]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "sample_count": len(values),
        "win_rate": round(len(wins) / len(values), 4) if values else None,
        "avg_net_return_pct": round(mean(values), 4) if values else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
    }


def _category(value: Any) -> str:
    if value in (None, "", "MISSING", "INSUFFICIENT_HISTORY"):
        return "MISSING"
    return str(value)


def _sse(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = mean(values)
    return sum((value - center) ** 2 for value in values)


def _split_gain(rows: Sequence[Mapping[str, Any]], feature: str, label: str, min_leaf: int) -> float | None:
    groups: dict[str, list[float]] = {}
    for row in rows:
        target = _target(row, label)
        category = _category(value_at(row, feature))
        if target is not None and category != "MISSING":
            groups.setdefault(category, []).append(target)
    if len(groups) < 2 or len(groups) > 12 or any(len(values) < min_leaf for values in groups.values()):
        return None
    all_values = [value for values in groups.values() for value in values]
    return _sse(all_values) - sum(_sse(values) for values in groups.values())


def _node(
    rows: Sequence[Mapping[str, Any]],
    features: Sequence[str],
    *,
    label: str,
    depth: int,
    max_depth: int,
    min_leaf: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {"depth": depth, "metrics": _metrics(rows, label)}
    candidates = [(gain, feature) for feature in features if (gain := _split_gain(rows, feature, label, min_leaf)) is not None]
    if depth >= max_depth or not candidates:
        result["leaf_reason"] = "MAX_DEPTH" if depth >= max_depth else "NO_STABLE_SPLIT"
        return result
    gain, feature = max(candidates, key=lambda item: (item[0], item[1]))
    result.update({"split_feature": feature, "split_gain": round(gain, 6), "branches": {}})
    remaining = tuple(candidate for candidate in features if candidate != feature)
    result["excluded_missing_count"] = sum(_category(value_at(row, feature)) == "MISSING" for row in rows)
    categories = sorted({_category(value_at(row, feature)) for row in rows} - {"MISSING"})
    for category in categories:
        subset = [row for row in rows if _category(value_at(row, feature)) == category]
        result["branches"][category] = _node(
            subset,
            remaining,
            label=label,
            depth=depth + 1,
            max_depth=max_depth,
            min_leaf=min_leaf,
        )
    return result


def build_regression_tree(
    rows: Sequence[Mapping[str, Any]],
    *,
    name: str,
    features: Sequence[str],
    target_horizon: str = "+30m",
    validation_start: str = "2026-08-01",
    min_leaf: int = 3,
) -> dict[str, Any]:
    train = [row for row in rows if str(value_at(row, "identity.day") or "") < validation_start]
    validation = [row for row in rows if str(value_at(row, "identity.day") or "") >= validation_start]
    return {
        "schema_version": "rank1_explainable_tree.v1",
        "name": name,
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "target": f"net_return_{target_horizon}",
        "training_period": f"before {validation_start}",
        "tree": _node(train, features, label=target_horizon, depth=0, max_depth=2, min_leaf=min_leaf),
        "train_metrics": _metrics(train, target_horizon),
        "validation_metrics": _metrics(validation, target_horizon),
        "feature_paths": list(features),
    }


def build_horizon_matrix(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = " | ".join(
            (
                _category(value_at(row, "strategy.entry_horizon")),
                _category(value_at(row, "chart.intraday_ma2_5_cross_state")),
                _category(value_at(row, "chart.above_vwap")),
            )
        )
        groups.setdefault(key, []).append(row)
    branches = []
    for key, subset in sorted(groups.items()):
        horizon_metrics = {horizon: _metrics(subset, horizon) for horizon in HORIZONS}
        eligible = [
            (metrics["avg_net_return_pct"], horizon)
            for horizon, metrics in horizon_metrics.items()
            if metrics["sample_count"] >= 3 and metrics["avg_net_return_pct"] is not None
        ]
        branches.append(
            {
                "branch": key,
                "episode_count": len(subset),
                "best_horizon": max(eligible)[1] if eligible else "INSUFFICIENT_EVIDENCE",
                "horizons": horizon_metrics,
            }
        )
    return {
        "schema_version": "rank1_horizon_matrix.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "branch_definition": "strategy.entry_horizon | intraday_ma2_5_cross_state | above_vwap",
        "branches": branches,
        "best_horizon_counts": dict(Counter(row["best_horizon"] for row in branches)),
    }


def build_all_trees(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "scanner": build_regression_tree(rows, name="SCANNER_SUITABILITY", features=SCANNER_FEATURES),
        "entry": build_regression_tree(rows, name="ENTRY_TIMING", features=ENTRY_FEATURES, target_horizon="+15m"),
        "horizon": build_regression_tree(rows, name="HORIZON_SUITABILITY", features=HORIZON_FEATURES, target_horizon="EOD"),
        "horizon_matrix": build_horizon_matrix(rows),
    }
