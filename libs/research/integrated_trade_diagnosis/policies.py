from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .metrics import number, performance


def _opening_minute(row: Mapping[str, Any]) -> float | None:
    seconds = number(row.get("decision_from_open_sec"))
    return seconds / 60.0 if seconds is not None else None


def opening_policy_rows(
    stage_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for row in stage_rows:
        minute = _opening_minute(row)
        if minute is None or minute > 30:
            continue
        playbook = str(row.get("playbook") or "").lower()
        completed = int(number(row.get("completed_bar_count_before_decision")) or 0)
        pre_return = number(row.get("precompleted_return_1m_pct"))
        relative_volume = number(row.get("opening_relative_volume"))
        entry_vs_prior = number(row.get("entry_vs_prior_close_pct"))
        intrinsic_return = number(row.get("intrinsic_30m_net_pct"))
        monitor_return = number(row.get("monitor_candidate_30m_net_pct"))
        current_enter = (
            str(row.get("monitor_intent") or "").upper() == "BUY"
            and str(row.get("commander_decision") or "").lower() == "approve"
        )
        policy_flags = {
            "CURRENT_PIPELINE": current_enter and monitor_return is not None,
            "OPENING_PROBE": bool(
                minute <= 5
                and playbook == "breakout"
            ),
            "WAIT_CONFIRM": bool(
                minute <= 15
                and completed >= 1
                and pre_return is not None
                and pre_return > 0
                and relative_volume is not None
                and relative_volume >= 0.8
            ),
            "NO_CHASE": bool(
                minute <= 5
                and playbook == "breakout"
                and entry_vs_prior is not None
                and entry_vs_prior <= 5.0
            ),
        }
        for policy, would_enter in policy_flags.items():
            result.append(
                {
                    "decision_id": row.get("decision_id"),
                    "day": row.get("day"),
                    "symbol": row.get("symbol"),
                    "policy": policy,
                    "would_enter": would_enter,
                    "return_30m_pct": monitor_return
                    if policy == "CURRENT_PIPELINE"
                    else intrinsic_return,
                    "evidence_status": "OBSERVED"
                    if (monitor_return if policy == "CURRENT_PIPELINE" else intrinsic_return)
                    is not None
                    else "INSUFFICIENT_EVIDENCE",
                    "minutes_from_open": round(minute, 2),
                    "point_in_time_rule": True,
                    # None of the v0 policy predicates depends on VWAP. Missing
                    # VWAP must not make otherwise complete rule evidence partial.
                    "rule_evidence_status": "COMPLETE",
                }
            )
    return result


def opening_policy_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("policy") or "UNKNOWN")].append(row)
    return {
        policy: {
            "candidate_count": len(group),
            "would_enter_count": sum(bool(row.get("would_enter")) for row in group),
            "coverage": round(
                sum(row.get("evidence_status") == "OBSERVED" for row in group)
                / len(group),
                4,
            )
            if group
            else 0.0,
            "performance": performance(
                row.get("return_30m_pct")
                for row in group
                if row.get("would_enter")
                and row.get("evidence_status") == "OBSERVED"
            ),
        }
        for policy, group in sorted(groups.items())
    }


def reentry_policy_summary(
    sequences: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = list(sequences)
    current = [row.get("cumulative_return_pct") for row in rows]
    first_only = [row.get("first_return_pct") for row in rows]
    repeated = [row for row in rows if int(row.get("trade_count") or 0) > 1]
    return {
        "CURRENT": {
            "performance": performance(current),
            "repeated_sequence_count": len(repeated),
        },
        "STOP_AFTER_FIRST_EXIT": {
            "performance": performance(first_only),
            "reconstructable_count": len(rows),
        },
        "FRESH_EPISODE_ONLY": {
            "performance": performance([]),
            "evidence_status": "INSUFFICIENT_EVIDENCE",
            "reason": "historical independent-setup provenance was not persisted",
        },
        "PROFIT_LOCK": {
            "performance": performance([]),
            "evidence_status": "INSUFFICIENT_EVIDENCE",
            "reason": "intrasequence executable profit-lock prices were not persisted",
        },
    }


def horizon_summary(trades: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(trades)
    violations = [row for row in rows if row.get("horizon_violation_candidate") is True]
    improved = [row for row in rows if row.get("target_hold_would_improve_exit") is True]
    return {
        "CURRENT": performance(row.get("net_return_pct") for row in rows),
        "horizon_contract_available_count": sum(bool(row.get("strategy_horizon")) for row in rows),
        "violation_candidate_count": len(violations),
        "target_hold_improvement_count": len(improved),
        "EXIT_TOO_EARLY_SUPPORTED": performance(
            row.get("net_return_pct") for row in improved
        ),
        "policy_counterfactual_status": "PARTIAL_EVIDENCE",
        "note": (
            "Only persisted target checkpoints are used. Missing checkpoints are not "
            "treated as failed hold extensions."
        ),
    }


def reactivation_summary(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(events)
    labels: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        labels[str(row.get("selection_horizon_label") or "MISSING")].append(row)
    return {
        "labels": {
            label: {
                "count": len(group),
                "d5_close": performance(row.get("d5_close_net_pct") for row in group),
                "d5_high": performance(row.get("d5_max_high_net_pct") for row in group),
            }
            for label, group in sorted(labels.items())
        },
        "fresh_reactivation_trigger_status": "INSUFFICIENT_EVIDENCE",
        "note": (
            "D+ highs prove later movement, not that a point-in-time reactivation signal "
            "was available before the move."
        ),
    }
