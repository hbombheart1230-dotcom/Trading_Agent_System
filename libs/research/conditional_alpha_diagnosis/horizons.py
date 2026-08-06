from __future__ import annotations

from collections import defaultdict
from typing import Any

from .analysis import HORIZONS
from .metrics import evidence_profile, evidence_status, number, performance


def conditional_horizon_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for cohort in row.get("conditional_alpha_cohorts") or []:
            grouped[f"COHORT:{cohort}"].append(row)
        grouped[f"ARCHETYPE:{row.get('opening_archetype') or 'UNKNOWN'}"].append(row)

    matrix = []
    recommendations = []
    for group_id, group in sorted(grouped.items()):
        horizon_rows = []
        for horizon, field in HORIZONS.items():
            values = [value for row in group if (value := number(row.get(field))) is not None]
            metrics = performance(values)
            profile = evidence_profile(group)
            sorted_values = sorted(values, reverse=True)
            remainder = sorted_values[3:]
            horizon_rows.append(
                {
                    "group_id": group_id,
                    "horizon": horizon,
                    **metrics,
                    **profile,
                    "average_without_top3_pct": (
                        round(sum(remainder) / len(remainder), 4) if remainder else None
                    ),
                    "evidence_status": evidence_status(metrics, profile),
                }
            )
        matrix.extend(horizon_rows)
        eligible = [
            row
            for row in horizon_rows
            if row["evidence_status"] != "INSUFFICIENT_EVIDENCE"
            and number(row.get("average_without_top3_pct")) is not None
        ]
        best = max(
            eligible,
            key=lambda row: (
                number(row.get("average_without_top3_pct")) or -999.0,
                number(row.get("average_pct")) or -999.0,
            ),
            default=None,
        )
        recommendations.append(
            {
                "group_id": group_id,
                "best_robust_horizon": best.get("horizon") if best else None,
                "evidence_status": best.get("evidence_status") if best else "INSUFFICIENT_EVIDENCE",
                "average_pct": best.get("average_pct") if best else None,
                "average_without_top3_pct": (
                    best.get("average_without_top3_pct") if best else None
                ),
                "note": "Cohort aggregate comparison; not a per-trade oracle exit.",
            }
        )
    return {
        "schema_version": "conditional_horizon_report.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "matrix": matrix,
        "recommendations": recommendations,
    }
