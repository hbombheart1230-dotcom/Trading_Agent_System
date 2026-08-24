from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .cohorts import independent_day_symbol_rows
from .metrics import checkpoint_return, pearson, performance


def _group_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_fn,
    horizons: Sequence[str],
) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(key_fn(row) or "MISSING")].append(row)
    result = []
    for key, values in sorted(groups.items()):
        result.append(
            {
                "value": key,
                "sample_count": len(values),
                "horizons": {
                    horizon: performance(
                        [
                            checkpoint_return(dict(row.get("episode", {})), horizon)
                            for row in values
                        ]
                    )
                    for horizon in horizons
                },
            }
        )
    return result


def _score_quartiles(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    observed = sorted(
        [row for row in rows if row.get("score_total") is not None],
        key=lambda row: float(row["score_total"]),
    )
    result = []
    for index in range(4):
        start = index * len(observed) // 4
        end = (index + 1) * len(observed) // 4
        values = observed[start:end]
        if not values:
            continue
        result.append(
            {
                "quartile": index + 1,
                "sample_count": len(values),
                "score_min": round(float(values[0]["score_total"]), 4),
                "score_max": round(float(values[-1]["score_total"]), 4),
                "+30m": performance(
                    [
                        checkpoint_return(dict(row.get("episode", {})), "+30m")
                        for row in values
                    ]
                ),
            }
        )
    return result


def build_scanner_diagnostics(
    joined: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = independent_day_symbol_rows(joined)
    correlations = {}
    for horizon in ("+5m", "+15m", "+30m", "EOD"):
        correlations[horizon] = pearson(
            [
                (
                    row.get("score_total"),
                    checkpoint_return(dict(row.get("episode", {})), horizon),
                )
                for row in rows
            ]
        )
    market_known = 0
    fresh_market = 0
    for row in rows:
        feature_market = dict(dict(row.get("feature", {})).get("market", {}))
        if feature_market.get("snapshot_epoch") is not None:
            market_known += 1
            age = feature_market.get("snapshot_age_sec")
            if age is not None and float(age) <= 300.0:
                fresh_market += 1
    return {
        "evaluation_unit": "first_day_symbol",
        "sample_count": len(rows),
        "score_return_correlation": correlations,
        "score_quartiles": _score_quartiles(rows),
        "by_candidate_setup": _group_metrics(
            rows,
            key_fn=lambda row: row.get("candidate_setup"),
            horizons=("+15m", "+30m", "EOD"),
        ),
        "by_candidate_source": _group_metrics(
            rows,
            key_fn=lambda row: "+".join(row.get("sources") or []) or "MISSING",
            horizons=("+5m", "+30m", "EOD"),
        ),
        "market_snapshot_coverage": {
            "observed_count": market_known,
            "fresh_within_300s_count": fresh_market,
            "total_count": len(rows),
            "coverage": round(market_known / len(rows), 4) if rows else 0.0,
            "fresh_coverage": round(fresh_market / len(rows), 4) if rows else 0.0,
        },
        "behavior_change_authorized": False,
    }
