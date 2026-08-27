from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Mapping

from .contracts import (
    COHORTS,
    INSUFFICIENT_MEMORY_EVIDENCE,
    MEMORY_CLEAN,
    ROW_SCHEMA_VERSION,
    STALE_OR_CONTRADICTORY_MEMORY,
    SYMBOL_MEMORY_MISMATCH,
)
from .loaders import mapping, normalized_symbol


def _age_days(requested_day: str, resolved_day: str) -> int | None:
    try:
        return max(
            0,
            (date.fromisoformat(requested_day[:10]) - date.fromisoformat(resolved_day[:10])).days,
        )
    except (TypeError, ValueError):
        return None


def _symbol_memory_evidence(strategist: Mapping[str, Any]) -> tuple[str, bool, str]:
    trace = mapping(mapping(strategist.get("memory_usage_trace")).get("symbol_consistency"))
    trace_symbol = normalized_symbol(trace.get("memory_symbol"))
    if trace_symbol:
        return trace_symbol, True, "memory_usage_trace.symbol_consistency"

    visibility = mapping(strategist.get("memory_packet_visibility"))
    selected = mapping(visibility.get("selected_symbol_memory"))
    selected_present = bool(
        selected.get("present")
        or int(float(selected.get("trade_count") or 0)) > 0
        or selected.get("dominant_playbook")
        or selected.get("dominant_monitor_blocker")
    )
    selected_symbol = normalized_symbol(selected.get("symbol"))
    if selected_present and selected_symbol:
        return selected_symbol, True, "memory_packet_visibility.selected_symbol_memory"

    packet = mapping(mapping(visibility.get("memory_packets")).get("symbol"))
    packet_present = bool(
        packet.get("active")
        or packet.get("override_eligible")
        or int(float(packet.get("trade_count") or 0)) > 0
    )
    packet_symbol = normalized_symbol(packet.get("memory_symbol") or packet.get("symbol"))
    if packet_present and packet_symbol:
        return packet_symbol, True, "memory_packet_visibility.memory_packets.symbol"
    return "", bool(visibility), "symbol_memory_absent"


def _strategy_memory_evidence(strategist: Mapping[str, Any], day: str) -> dict[str, Any]:
    snapshot = mapping(strategist.get("strategy_memory_snapshot"))
    visibility = mapping(mapping(strategist.get("memory_packet_visibility")).get("strategy_memory"))
    best = [str(value) for value in snapshot.get("best_playbooks") or [] if str(value).strip()]
    worst = [str(value) for value in snapshot.get("worst_playbooks") or [] if str(value).strip()]
    overlap = sorted({value.lower() for value in best}.intersection(value.lower() for value in worst))
    requested_day = str(snapshot.get("requested_day") or visibility.get("requested_day") or day)
    resolved_day = str(
        snapshot.get("resolved_day")
        or snapshot.get("day")
        or visibility.get("resolved_day")
        or ""
    )
    age_days = _age_days(requested_day, resolved_day) if resolved_day else None
    directional = bool(
        best
        or worst
        or snapshot.get("recent_failures")
        or snapshot.get("recent_success_patterns")
    )
    return {
        "present": bool(snapshot or visibility),
        "status": str(snapshot.get("status") or visibility.get("status") or ""),
        "requested_day": requested_day,
        "resolved_day": resolved_day,
        "age_days": age_days,
        "directional_evidence_present": directional,
        "best_playbooks": best,
        "worst_playbooks": worst,
        "overlap": overlap,
        "stale_directional_evidence": bool(
            directional and age_days is not None and age_days > 7
        ),
    }


def classify_stage2_row(
    stage2: Mapping[str, Any],
    *,
    strategist: Mapping[str, Any],
    q9_window: Mapping[str, Any],
    trade_outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    target_symbol = normalized_symbol(stage2.get("target_symbol"))
    memory_symbol, symbol_evidence_available, symbol_source = _symbol_memory_evidence(strategist)
    strategy_memory = _strategy_memory_evidence(strategist, str(stage2.get("day") or ""))
    mismatch = bool(target_symbol and memory_symbol and target_symbol != memory_symbol)
    stale_or_contradictory = bool(
        strategy_memory.get("stale_directional_evidence") or strategy_memory.get("overlap")
    )
    if mismatch:
        cohort = SYMBOL_MEMORY_MISMATCH
        reason = "stage2_target_and_selected_symbol_memory_differ"
    elif stale_or_contradictory:
        cohort = STALE_OR_CONTRADICTORY_MEMORY
        reason = "directional_strategy_memory_stale_or_contradictory"
    elif strategist and target_symbol and symbol_evidence_available:
        cohort = MEMORY_CLEAN
        reason = "same_run_memory_evidence_has_no_detected_integrity_defect"
    else:
        cohort = INSUFFICIENT_MEMORY_EVIDENCE
        reason = "same_run_memory_or_target_evidence_missing"

    commander = mapping(q9_window.get("commander_final"))
    memory_trace = mapping(strategist.get("memory_usage_trace"))
    application_summary = mapping(memory_trace.get("application_summary"))
    layer_decisions = mapping(memory_trace.get("layer_decisions"))
    packet_ids = {
        str(layer): str(mapping(decision).get("packet_id") or "")
        for layer, decision in layer_decisions.items()
        if mapping(decision).get("packet_id")
    }
    memory_usage = mapping(stage2.get("memory_usage"))
    entry_delta = mapping(stage2.get("entry_policy_delta"))
    normalized_trades: list[dict[str, Any]] = []
    for raw_trade in trade_outcomes:
        trade = dict(raw_trade)
        target_match = normalized_symbol(trade.get("symbol")) == target_symbol
        trade["memory_review_target_match"] = target_match
        trade["trusted_for_memory_review"] = bool(
            trade.get("trusted_for_behavior") and target_match
        )
        normalized_trades.append(trade)
    trusted_trades = [row for row in normalized_trades if row.get("trusted_for_memory_review")]
    return {
        "schema_version": ROW_SCHEMA_VERSION,
        "day": str(stage2.get("day") or ""),
        "timestamp": str(stage2.get("timestamp") or ""),
        "run_id": str(stage2.get("run_id") or ""),
        "cohort": cohort,
        "classification_reason": reason,
        "target_symbol": target_symbol,
        "memory_symbol": memory_symbol,
        "symbol_memory_source": symbol_source,
        "symbol_memory_evidence_available": symbol_evidence_available,
        "symbol_consistent": not mismatch,
        "strategy_memory": strategy_memory,
        "stage2_decision": str(stage2.get("selected_symbol_decision") or ""),
        "target_rank": stage2.get("target_rank"),
        "memory_claimed_status": str(memory_usage.get("status") or ""),
        "memory_claimed_effect": str(memory_usage.get("effect") or ""),
        "memory_claimed_reason": str(memory_usage.get("reason") or ""),
        "memory_packet_ids": packet_ids,
        "applied_memory_packet_ids": [
            str(value)
            for value in list(application_summary.get("applied_packet_ids") or [])
            if str(value).strip()
        ],
        "memory_packet_provenance_available": bool(packet_ids),
        "entry_policy_delta": entry_delta,
        "entry_policy_tightened": bool(entry_delta.get("tighten_confidence_threshold")),
        "q9_linked": bool(q9_window),
        "q9_decision_id": str(q9_window.get("decision_id") or ""),
        "commander_decision": str(commander.get("decision") or ""),
        "commander_veto": bool(commander.get("veto")),
        "commander_no_trade": bool(commander.get("no_trade")),
        "commander_reason": str(commander.get("reason") or ""),
        "trade_outcomes": normalized_trades,
        "trusted_trade_count": len(trusted_trades),
    }


def _profit_factor(returns: list[float]) -> float | None:
    gains = sum(value for value in returns if value > 0)
    losses = abs(sum(value for value in returns if value < 0))
    if losses <= 1e-12:
        return None if gains <= 1e-12 else float("inf")
    return round(gains / losses, 4)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cohorts: dict[str, Any] = {}
    for cohort in COHORTS:
        selected = [row for row in rows if row.get("cohort") == cohort]
        trade_rows = [
            trade
            for row in selected
            for trade in row.get("trade_outcomes") or []
            if trade.get("trusted_for_memory_review")
        ]
        returns = [float(row.get("net_return_pct") or 0.0) for row in trade_rows]
        cohorts[cohort] = {
            "stage2_call_count": len(selected),
            "day_count": len({row.get("day") for row in selected}),
            "q9_linked_count": sum(bool(row.get("q9_linked")) for row in selected),
            "commander_approve_count": sum(
                str(row.get("commander_decision")) == "approve" for row in selected
            ),
            "commander_veto_count": sum(bool(row.get("commander_veto")) for row in selected),
            "commander_no_trade_count": sum(bool(row.get("commander_no_trade")) for row in selected),
            "entry_policy_delta_count": sum(bool(row.get("entry_policy_delta")) for row in selected),
            "entry_policy_tightened_count": sum(
                bool(row.get("entry_policy_tightened")) for row in selected
            ),
            "memory_effect_counts": dict(
                Counter(str(row.get("memory_claimed_effect") or "not_reported") for row in selected)
            ),
            "memory_packet_provenance_count": sum(
                bool(row.get("memory_packet_provenance_available")) for row in selected
            ),
            "trusted_trade_count": len(trade_rows),
            "trade_win_rate": (
                round(sum(value > 0 for value in returns) / len(returns), 4) if returns else None
            ),
            "trade_avg_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
            "trade_profit_factor": _profit_factor(returns),
        }
    return cohorts


def aggregate_by_month(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    months = sorted({str(row.get("day") or "")[:7] for row in rows if row.get("day")})
    out: list[dict[str, Any]] = []
    for month in months:
        selected = [row for row in rows if str(row.get("day") or "").startswith(month)]
        cohort_counts = Counter(str(row.get("cohort") or "") for row in selected)
        out.append(
            {
                "month": month,
                "stage2_call_count": len(selected),
                "q9_linked_count": sum(bool(row.get("q9_linked")) for row in selected),
                "cohort_counts": dict(cohort_counts),
                "mismatch_tightened_count": sum(
                    row.get("cohort") == SYMBOL_MEMORY_MISMATCH
                    and bool(row.get("entry_policy_tightened"))
                    for row in selected
                ),
            }
        )
    return out
