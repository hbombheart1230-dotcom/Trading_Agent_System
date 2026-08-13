from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .contracts import CORE_FEATURE_PATHS, OUTCOME_LABELS


def value_at(row: Mapping[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _present(value: Any) -> bool:
    return value not in (None, "", "MISSING", "INSUFFICIENT_HISTORY")


def audit(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [str(value_at(row, "identity.episode_id") or "") for row in rows]
    duplicates = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    time_leaks = []
    symbol_mismatches = []
    for row in rows:
        episode_id = str(value_at(row, "identity.episode_id") or "")
        decision_epoch = int(value_at(row, "identity.decision_epoch") or 0)
        feature_epoch = int(value_at(row, "chart.feature_max_epoch") or 0)
        if feature_epoch and decision_epoch and feature_epoch > decision_epoch:
            time_leaks.append(episode_id)
        symbol = str(value_at(row, "identity.symbol") or "")
        if symbol and len(symbol) != 6:
            symbol_mismatches.append(episode_id)
    feature_coverage = {}
    for path in CORE_FEATURE_PATHS:
        eligible = rows
        eligibility = "ALL_EPISODES"
        if path in {"chart.above_vwap", "chart.support_state", "chart.resistance_state"}:
            eligible = [row for row in rows if int(value_at(row, "chart.completed_bar_count") or 0) >= 1]
            eligibility = "AT_LEAST_1_COMPLETED_BAR"
        elif path == "chart.intraday_ma2_5_cross_state":
            eligible = [row for row in rows if int(value_at(row, "chart.completed_bar_count") or 0) >= 6]
            eligibility = "AT_LEAST_6_COMPLETED_BARS"
        present = sum(_present(value_at(row, path)) for row in rows)
        eligible_present = sum(_present(value_at(row, path)) for row in eligible)
        feature_coverage[path] = {
            "present": present,
            "total": len(rows),
            "coverage": round(present / len(rows), 4) if rows else 0.0,
            "eligibility": eligibility,
            "eligible_present": eligible_present,
            "eligible_total": len(eligible),
            "eligible_coverage": round(eligible_present / len(eligible), 4) if eligible else 1.0,
        }
    horizon_coverage = {}
    for label in OUTCOME_LABELS:
        statuses = Counter(
            str(value_at(row, f"outcomes.checkpoints.{label}.status") or "MISSING")
            for row in rows
        )
        observed = sum(count for status, count in statuses.items() if status.startswith("OBSERVED"))
        horizon_coverage[label] = {
            "observed": observed,
            "total": len(rows),
            "coverage": round(observed / len(rows), 4) if rows else 0.0,
            "status_counts": dict(statuses),
        }
    critical = bool(duplicates or time_leaks or symbol_mismatches)
    return {
        "schema_version": "rank1_feature_mart_integrity.v1",
        "status": "FAIL" if critical else "PASS_WITH_COVERAGE_GAPS" if any(value["eligible_coverage"] < 0.9 for value in feature_coverage.values()) else "PASS",
        "episode_count": len(rows),
        "day_count": len({value_at(row, "identity.day") for row in rows}),
        "symbol_count": len({value_at(row, "identity.symbol") for row in rows}),
        "duplicate_episode_ids": duplicates,
        "point_in_time_violations": time_leaks,
        "symbol_format_violations": symbol_mismatches,
        "feature_coverage": feature_coverage,
        "horizon_coverage": horizon_coverage,
    }
