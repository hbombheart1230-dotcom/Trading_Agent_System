from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Mapping, Sequence

from .contracts import HORIZONS, PRIMARY_COHORT_ID, PROSPECTIVE_START_DAY
from .metrics import checkpoint_return, number, performance


Predicate = Callable[[Mapping[str, Any]], bool]


def join_opening_to_feature_mart(
    opening_episodes: Sequence[Mapping[str, Any]],
    feature_episodes: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_decision_id = {
        str(dict(row.get("identity", {})).get("decision_id")): row
        for row in feature_episodes
        if dict(row.get("identity", {})).get("decision_id")
    }
    joined: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw in opening_episodes:
        episode = dict(raw)
        decision_id = str(episode.get("decision_id") or "")
        feature = by_decision_id.get(decision_id)
        if not feature:
            missing.append(decision_id)
            continue
        observability = dict(episode.get("opening_observability", {}))
        asset = dict(observability.get("asset_observation", {}))
        scanner = dict(feature.get("scanner", {}))
        strategy = dict(feature.get("strategy", {}))
        joined.append(
            {
                "episode": episode,
                "feature": dict(feature),
                "day": str(episode.get("day") or ""),
                "symbol": str(episode.get("symbol") or ""),
                "decision_id": decision_id,
                "asset_class": str(asset.get("asset_class") or "UNKNOWN"),
                "risk_band": str(scanner.get("risk_band") or "MISSING"),
                "candidate_setup": str(scanner.get("candidate_setup") or "MISSING"),
                "entry_horizon": str(strategy.get("entry_horizon") or "MISSING"),
                "tactic_id": str(strategy.get("tactic_id") or "MISSING"),
                "sources": sorted(str(value) for value in scanner.get("sources") or []),
                "score_total": number(scanner.get("score_total")),
            }
        )
    return joined, {
        "opening_episode_count": len(opening_episodes),
        "feature_episode_count": len(feature_episodes),
        "joined_episode_count": len(joined),
        "missing_join_count": len(missing),
        "missing_decision_ids": missing,
    }


def _cohort_rows(
    joined: Sequence[Mapping[str, Any]], predicate: Predicate
) -> list[Mapping[str, Any]]:
    return [row for row in joined if predicate(row)]


def independent_day_symbol_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    first: dict[tuple[str, str], Mapping[str, Any]] = {}
    ordered = sorted(
        rows,
        key=lambda row: int(dict(row.get("episode", {})).get("decision_epoch") or 0),
    )
    for row in ordered:
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""))
        if key[0] and key[1]:
            first.setdefault(key, row)
    return list(first.values())


def summarize_cohort(
    cohort_id: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    conditions: Sequence[str],
) -> dict[str, Any]:
    independent = independent_day_symbol_rows(rows)
    days = Counter(str(row.get("day")) for row in independent)
    symbols = Counter(str(row.get("symbol")) for row in independent)
    return {
        "cohort_id": cohort_id,
        "conditions": list(conditions),
        "episode_count": len(rows),
        "independent_day_symbol_count": len(independent),
        "day_count": len(days),
        "largest_day_share": (
            round(max(days.values()) / len(independent), 4) if independent else None
        ),
        "largest_symbol_share": (
            round(max(symbols.values()) / len(independent), 4) if independent else None
        ),
        "horizons": {
            horizon: performance(
                [
                    checkpoint_return(dict(row.get("episode", {})), horizon)
                    for row in independent
                ]
            )
            for horizon in HORIZONS
        },
    }


def build_cohort_review(joined: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    predicates: list[tuple[str, tuple[str, ...], Predicate]] = [
        (
            PRIMARY_COHORT_ID,
            ("asset_class=common_stock", "risk_band=HIGH"),
            lambda row: row.get("asset_class") == "common_stock"
            and row.get("risk_band") == "HIGH",
        ),
        (
            "HIGH_NON_COMMON_CONTROL",
            ("asset_class!=common_stock", "risk_band=HIGH"),
            lambda row: row.get("asset_class") != "common_stock"
            and row.get("risk_band") == "HIGH",
        ),
        (
            "NON_HIGH_COMMON_CONTROL",
            ("asset_class=common_stock", "risk_band!=HIGH"),
            lambda row: row.get("asset_class") == "common_stock"
            and row.get("risk_band") != "HIGH",
        ),
        (
            "HIGH_COMMON_DIRECTIONAL",
            (
                "asset_class=common_stock",
                "risk_band=HIGH",
                "candidate_setup=DIRECTIONAL_BREADTH",
            ),
            lambda row: row.get("asset_class") == "common_stock"
            and row.get("risk_band") == "HIGH"
            and row.get("candidate_setup") == "DIRECTIONAL_BREADTH",
        ),
        (
            "IMMEDIATE_COMMON",
            ("asset_class=common_stock", "decision_from_open_sec<=60"),
            lambda row: row.get("asset_class") == "common_stock"
            and int(
                dict(row.get("episode", {}))
                .get("opening_observability", {})
                .get("decision_from_open_sec")
                or 999999
            )
            <= 60,
        ),
        (
            "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1",
            ("sources=top_value+top_volume",),
            lambda row: row.get("sources") == ["top_value", "top_volume"],
        ),
    ]
    cohorts = [
        summarize_cohort(cohort_id, _cohort_rows(joined, predicate), conditions=conditions)
        for cohort_id, conditions, predicate in predicates
    ]
    primary_rows = _cohort_rows(
        joined,
        lambda row: row.get("asset_class") == "common_stock"
        and row.get("risk_band") == "HIGH",
    )
    prospective_rows = [
        row for row in primary_rows if str(row.get("day")) >= PROSPECTIVE_START_DAY
    ]
    historical_rows = [
        row for row in primary_rows if str(row.get("day")) < PROSPECTIVE_START_DAY
    ]
    independent_historical = independent_day_symbol_rows(historical_rows)
    symbol_values = sorted({str(row.get("symbol")) for row in independent_historical})
    day_values = sorted({str(row.get("day")) for row in independent_historical})

    def leave_one(field: str, values: Sequence[str]) -> list[dict[str, Any]]:
        output = []
        for value in values:
            remaining = [row for row in independent_historical if str(row.get(field)) != value]
            output.append(
                {
                    f"excluded_{field}": value,
                    "+5m": performance(
                        [
                            checkpoint_return(dict(row.get("episode", {})), "+5m")
                            for row in remaining
                        ]
                    ),
                    "+30m": performance(
                        [
                            checkpoint_return(dict(row.get("episode", {})), "+30m")
                            for row in remaining
                        ]
                    ),
                }
            )
        return output

    best = max(
        independent_historical,
        key=lambda row: checkpoint_return(dict(row.get("episode", {})), "+5m")
        or -999.0,
        default=None,
    )
    without_best = [row for row in independent_historical if row is not best]
    return {
        "prospective_contract": {
            "candidate_id": PRIMARY_COHORT_ID,
            "first_eligible_day": PROSPECTIVE_START_DAY,
            "selection_rule_frozen": True,
            "conditions": ["asset_class=common_stock", "risk_band=HIGH"],
            "behavior_effect": "NONE_OBSERVATION_ONLY",
        },
        "cohorts": cohorts,
        "historical_reference": summarize_cohort(
            PRIMARY_COHORT_ID,
            historical_rows,
            conditions=("asset_class=common_stock", "risk_band=HIGH"),
        ),
        "historical_sensitivity": {
            "by_symbol_leave_one_out": leave_one("symbol", symbol_values),
            "by_day_leave_one_out": leave_one("day", day_values),
            "without_best_observation": {
                "excluded_day": best.get("day") if best else None,
                "excluded_symbol": best.get("symbol") if best else None,
                "+5m": performance(
                    [
                        checkpoint_return(dict(row.get("episode", {})), "+5m")
                        for row in without_best
                    ]
                ),
                "+30m": performance(
                    [
                        checkpoint_return(dict(row.get("episode", {})), "+30m")
                        for row in without_best
                    ]
                ),
            },
        },
        "prospective": summarize_cohort(
            PRIMARY_COHORT_ID,
            prospective_rows,
            conditions=("asset_class=common_stock", "risk_band=HIGH"),
        ),
    }


def group_feature_metrics(
    joined: Sequence[Mapping[str, Any]], field: str, horizon: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[float | None]] = defaultdict(list)
    for row in joined:
        groups[str(row.get(field) or "MISSING")].append(
            checkpoint_return(dict(row.get("episode", {})), horizon)
        )
    return [
        {field: key, **performance(values)} for key, values in sorted(groups.items())
    ]
