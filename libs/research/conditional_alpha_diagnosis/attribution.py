from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from .metrics import evidence_profile, evidence_status, number, performance


MATERIAL_DELTA_PCT = 0.28


def _delta(after: Any, before: Any) -> float | None:
    after_value = number(after)
    before_value = number(before)
    if after_value is None or before_value is None:
        return None
    return round(after_value - before_value, 4)


def diagnose_stage_attribution(row: Mapping[str, Any]) -> dict[str, Any]:
    intrinsic = number(row.get("intrinsic_30m_net_pct"))
    strategist = number(row.get("strategist_selected_30m_net_pct"))
    monitor = number(row.get("monitor_candidate_30m_net_pct"))
    executed_shadow = number(row.get("executed_30m_net_pct"))
    executed_realized = number(row.get("executed_realized_return_pct"))
    strategist_delta = _delta(strategist, intrinsic)
    monitor_delta = _delta(monitor, strategist)
    commander_decision = str(row.get("commander_decision") or "MISSING").lower()

    if intrinsic is None:
        root_cause = "MISSING_INTRINSIC_FORWARD_EVIDENCE"
    elif intrinsic <= 0:
        root_cause = "NO_INTRINSIC_30M_EDGE"
    elif strategist_delta is not None and strategist_delta <= -MATERIAL_DELTA_PCT:
        root_cause = "STRATEGIST_DEGRADATION"
    elif monitor is None:
        root_cause = "MONITOR_CANDIDATE_MISSING"
    elif monitor_delta is not None and monitor_delta <= -MATERIAL_DELTA_PCT:
        root_cause = "MONITOR_DEGRADATION"
    elif commander_decision in {"reject", "retry_scan"}:
        root_cause = "COMMANDER_FILTERED_POSITIVE"
    elif executed_shadow is None:
        root_cause = "ENTRY_NOT_EXECUTED_POSITIVE"
    elif executed_realized is not None and executed_realized <= 0 < intrinsic:
        root_cause = "EXECUTION_OR_EXIT_GIVEBACK"
    else:
        root_cause = "PIPELINE_PRESERVED_OR_EXECUTED"

    return {
        "root_cause": root_cause,
        "intrinsic_30m_net_pct": intrinsic,
        "strategist_selected_30m_net_pct": strategist,
        "monitor_candidate_30m_net_pct": monitor,
        "executed_shadow_30m_net_pct": executed_shadow,
        "executed_realized_return_pct": executed_realized,
        "strategist_delta_pct": strategist_delta,
        "monitor_delta_pct": monitor_delta,
        "commander_decision": commander_decision,
        "material_delta_threshold_pct": MATERIAL_DELTA_PCT,
    }


def stage_attribution_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    annotated = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        attribution = diagnose_stage_attribution(row)
        item = {
            "decision_id": row.get("decision_id"),
            "day": row.get("day"),
            "symbol": row.get("symbol"),
            "symbol_name": row.get("symbol_name"),
            "cohorts": row.get("conditional_alpha_cohorts") or [],
            "archetype": row.get("opening_archetype"),
            **attribution,
        }
        annotated.append(item)
        grouped[attribution["root_cause"]].append(item)

    summary = []
    for root_cause, group in sorted(grouped.items()):
        metrics = performance(row.get("intrinsic_30m_net_pct") for row in group)
        profile = evidence_profile(group)
        summary.append(
            {
                "root_cause": root_cause,
                **metrics,
                **profile,
                "evidence_status": evidence_status(metrics, profile),
            }
        )
    summary.sort(key=lambda row: (-int(row.get("count") or 0), row["root_cause"]))
    return {
        "schema_version": "conditional_stage_attribution.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "material_delta_threshold_pct": MATERIAL_DELTA_PCT,
        "summary": summary,
        "rows": annotated,
    }
