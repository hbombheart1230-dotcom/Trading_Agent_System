from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Mapping


def _metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "win_rate": None,
            "average_pct": None,
            "median_pct": None,
            "profit_factor": None,
        }
    gains = sum(value for value in values if value > 0.0)
    losses = abs(sum(value for value in values if value < 0.0))
    return {
        "count": len(values),
        "win_rate": round(
            sum(value > 0.0 for value in values) / len(values),
            4,
        ),
        "average_pct": round(sum(values) / len(values), 4),
        "median_pct": round(median(values), 4),
        "profit_factor": round(gains / losses, 4)
        if losses
        else (999.0 if gains else None),
    }


def _values(rows: list[Mapping[str, Any]], field: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(field)
        if value is not None:
            values.append(float(value))
    return values


def _group_metrics(
    rows: list[Mapping[str, Any]],
    group_field: str,
    value_field: str,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(group_field) or "MISSING")].append(row)
    return {
        key: _metrics(_values(group, value_field))
        for key, group in sorted(groups.items())
    }


def _average(rows: list[Mapping[str, Any]], field: str) -> float | None:
    values = _values(rows, field)
    return round(sum(values) / len(values), 4) if values else None


def _cohort_profile(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "decision_from_open_sec_avg": _average(
            rows,
            "decision_from_open_sec",
        ),
        "opening_gap_pct_avg": _average(rows, "opening_gap_pct"),
        "entry_vs_prior_close_pct_avg": _average(
            rows,
            "entry_vs_prior_close_pct",
        ),
        "opening_relative_volume_avg": _average(
            rows,
            "opening_relative_volume",
        ),
        "scanner_score_avg": _average(rows, "scanner_score"),
        "risk_score_avg": _average(rows, "risk_score"),
        "same_day_close_net_pct_avg": _average(
            rows,
            "same_day_close_net_pct",
        ),
        "d1_close_net_pct_avg": _average(rows, "d1_close_net_pct"),
        "d5_close_net_pct_avg": _average(rows, "d5_close_net_pct"),
        "playbooks": dict(
            Counter(str(row.get("playbook") or "MISSING") for row in rows)
        ),
        "scenarios": dict(
            Counter(
                str(row.get("strategist_scenario") or "MISSING")
                for row in rows
            )
        ),
        "path_types": dict(
            Counter(str(row.get("path_type") or "MISSING") for row in rows)
        ),
        "strategist_relations": dict(
            Counter(
                str(row.get("strategist_relation") or "MISSING")
                for row in rows
            )
        ),
        "monitor_relations": dict(
            Counter(
                str(row.get("monitor_relation") or "MISSING")
                for row in rows
            )
        ),
    }


def analyze_stage_fates(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    stage_fields = {
        "intrinsic": "intrinsic_30m_net_pct",
        "strategist_selected": "strategist_selected_30m_net_pct",
        "monitor_candidate": "monitor_candidate_30m_net_pct",
        "executed_shadow_30m": "executed_30m_net_pct",
        "executed_realized": "executed_realized_return_pct",
    }
    paired = {}
    for name, field in (
        ("strategist_vs_intrinsic", "strategist_selected_30m_net_pct"),
        ("monitor_vs_intrinsic", "monitor_candidate_30m_net_pct"),
    ):
        deltas = [
            float(row[field]) - float(row["intrinsic_30m_net_pct"])
            for row in rows
            if row.get(field) is not None
            and row.get("intrinsic_30m_net_pct") is not None
        ]
        paired[name] = {
            **_metrics(deltas),
            "improved_count": sum(value > 0.0 for value in deltas),
            "degraded_count": sum(value < 0.0 for value in deltas),
            "unchanged_count": sum(value == 0.0 for value in deltas),
        }
    rejected_intrinsic = [
        row
        for row in rows
        if row.get("commander_decision") == "reject"
    ]
    return {
        "decision_count": len(rows),
        "stage_performance": {
            name: _metrics(_values(rows, field))
            for name, field in stage_fields.items()
        },
        "strategist_relation": _group_metrics(
            rows,
            "strategist_relation",
            "intrinsic_30m_net_pct",
        ),
        "monitor_relation": _group_metrics(
            rows,
            "monitor_relation",
            "intrinsic_30m_net_pct",
        ),
        "commander_decisions": dict(
            Counter(str(row.get("commander_decision") or "MISSING") for row in rows)
        ),
        "intrinsic_preserved_to_execution_count": sum(
            bool(row.get("intrinsic_preserved_to_execution"))
            for row in rows
        ),
        "paired_stage_delta": paired,
        "rejected_intrinsic_performance": _metrics(
            _values(rejected_intrinsic, "intrinsic_30m_net_pct")
        ),
    }


def analyze_longitudinal(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    labels = Counter(
        str(row.get("selection_horizon_label") or "MISSING")
        for row in events
    )
    observed_d5 = [
        row
        for row in events
        if row.get("d5_status") == "OBSERVED"
    ]
    delayed = [
        row
        for row in events
        if row.get("delayed_high_opportunity")
    ]
    confirmed = [
        row
        for row in events
        if row.get("delayed_close_confirmation")
    ]
    negative_complete = [
        row
        for row in observed_d5
        if float(row.get("net_return_30m_pct") or 0.0) <= 0.0
    ]
    negative_without_delayed_high = [
        row
        for row in negative_complete
        if not row.get("delayed_high_opportunity")
    ]
    immediate_expansion = [
        row
        for row in events
        if float(row.get("net_return_30m_pct") or -10**9) >= 5.0
    ]
    delayed_next_day = [
        row
        for row in delayed
        if row.get("d1_max_high_net_pct") is not None
        and float(row["d1_max_high_net_pct"]) >= 5.0
    ]
    return {
        "event_count": len(events),
        "d5_observed_count": len(observed_d5),
        "label_counts": dict(labels),
        "horizons": {
            field: _metrics(_values(observed_d5, field))
            for field in (
                "same_day_close_net_pct",
                "d1_max_high_net_pct",
                "d1_close_net_pct",
                "d3_max_high_net_pct",
                "d3_close_net_pct",
                "d5_max_high_net_pct",
                "d5_close_net_pct",
            )
        },
        "delayed_high_count": len(delayed),
        "delayed_close_confirmation_count": len(confirmed),
        "negative_d5_complete_count": len(negative_complete),
        "delayed_high_rate_among_negative": round(
            len(delayed) / len(negative_complete),
            4,
        ) if negative_complete else None,
        "delayed_close_rate_among_negative": round(
            len(confirmed) / len(negative_complete),
            4,
        ) if negative_complete else None,
        "delayed_close_retention_rate": round(
            len(confirmed) / len(delayed),
            4,
        ) if delayed else None,
        "delayed_next_day_high_count": len(delayed_next_day),
        "cohort_comparison": {
            "immediate_expansion_30m_ge_5": _cohort_profile(
                immediate_expansion
            ),
            "delayed_high_after_nonpositive_30m": _cohort_profile(delayed),
            "negative_without_delayed_high": _cohort_profile(
                negative_without_delayed_high
            ),
        },
        "delayed_high_by_playbook": dict(
            Counter(str(row.get("playbook") or "MISSING") for row in delayed)
        ),
        "delayed_high_by_scenario": dict(
            Counter(
                str(row.get("strategist_scenario") or "MISSING")
                for row in delayed
            )
        ),
        "delayed_high_cases": sorted(
            delayed,
            key=lambda row: float(row.get("d5_max_high_net_pct") or -10**9),
            reverse=True,
        ),
        "delayed_close_cases": sorted(
            confirmed,
            key=lambda row: float(row.get("d5_close_net_pct") or -10**9),
            reverse=True,
        ),
    }
