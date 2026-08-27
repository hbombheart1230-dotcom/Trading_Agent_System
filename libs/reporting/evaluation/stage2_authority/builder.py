from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Mapping, Sequence

from libs.reporting.q8_evaluation_contract import candidate_day

from .contracts import (
    EVALUATION_HORIZONS,
    PRIMARY_HORIZON,
    SCHEMA_VERSION,
    classify_paired_effect,
    classify_promotion_eligibility,
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _role_row(roles: Mapping[str, Sequence[Mapping[str, Any]]], role: str) -> dict[str, Any]:
    rows = list(roles.get(role) or [])
    return min(
        (dict(row) for row in rows),
        key=lambda row: int(float(row.get("rank") or 999)),
        default={},
    )


def _ranked_role_rows(
    roles: Mapping[str, Sequence[Mapping[str, Any]]], role: str
) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in roles.get(role) or []),
        key=lambda row: int(float(row.get("rank") or 999)),
    )


def _score(row: Mapping[str, Any]) -> float | None:
    try:
        return float(row.get("score_total"))
    except (TypeError, ValueError):
        return None


def _symbol_rank(rows: Sequence[Mapping[str, Any]], symbol: str) -> int | None:
    match = next((row for row in rows if str(row.get("symbol") or "") == symbol), None)
    try:
        return int(float(match.get("rank"))) if match else None
    except (TypeError, ValueError):
        return None


def _checkpoint_return(row: Mapping[str, Any], horizon: str) -> float | None:
    outcome = _mapping(row.get("shadow_forward_outcome"))
    checkpoint = _mapping(_mapping(outcome.get("checkpoints")).get(horizon))
    if str(checkpoint.get("status") or "") != "observed":
        return None
    try:
        return float(checkpoint.get("return_pct"))
    except (TypeError, ValueError):
        return None


def _candidate_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    lane = _mapping(row.get("entry_lane_observation"))
    features = _mapping(lane.get("features"))
    rail = _mapping(lane.get("market_regime_rail_shadow"))
    return {
        "symbol": str(row.get("symbol") or ""),
        "name": str(row.get("name") or ""),
        "rank": row.get("rank"),
        "score_total": row.get("score_total"),
        "risk_score": row.get("risk_score"),
        "confidence": row.get("confidence"),
        "theme": str(row.get("theme") or ""),
        "quant_tactic_id": str(row.get("quant_tactic_id") or ""),
        "sources": list(row.get("q9_candidate_sources") or row.get("sources") or [])[:8],
        "score_breakdown": _mapping(row.get("score_breakdown")),
        "entry_lane": {
            "primary_lane": str(lane.get("primary_lane") or ""),
            "time_bucket": str(lane.get("time_bucket") or ""),
            "minutes_since_open": lane.get("minutes_since_open"),
            "market_regime": str(lane.get("market_regime") or ""),
            "market_regime_rail": str(lane.get("market_regime_rail") or ""),
            "features": features,
        },
        "market_metrics": _mapping(rail.get("metrics")),
    }


def _stage2_snapshot(parsed: Mapping[str, Any]) -> dict[str, Any]:
    instruction = _mapping(parsed.get("monitor_instruction"))
    entry_delta = _mapping(parsed.get("entry_policy_delta"))
    memory = _mapping(parsed.get("memory_usage"))
    return {
        "selected_symbol_decision": str(parsed.get("selected_symbol_decision") or ""),
        "target_symbol": str(parsed.get("target_symbol") or ""),
        "target_rank": parsed.get("target_rank"),
        "runner_up_order": list(parsed.get("runner_up_order") or [])[:8],
        "watch_intensity": str(instruction.get("watch_intensity") or ""),
        "required_confirmations": list(instruction.get("required_confirmations") or [])[:12],
        "avoid_if": list(instruction.get("avoid_if") or [])[:12],
        "entry_policy_delta": entry_delta,
        "market_regime_rail": str(parsed.get("market_regime_rail") or ""),
        "commander_actionability": str(parsed.get("commander_actionability") or ""),
        "confidence": parsed.get("confidence"),
        "memory_status": str(memory.get("status") or ""),
        "memory_confidence": str(memory.get("confidence") or ""),
        "memory_effect": str(memory.get("effect") or ""),
    }


def _elapsed_seconds(start: Any, end: Any) -> float | None:
    try:
        start_dt = datetime.fromisoformat(str(start or "").replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(end or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return round(max(0.0, (end_dt - start_dt).total_seconds()), 3)
def _authority_flags(parsed: Mapping[str, Any]) -> dict[str, bool]:
    decision = str(parsed.get("selected_symbol_decision") or "").strip().lower()
    entry_delta = _mapping(parsed.get("entry_policy_delta"))
    instruction = _mapping(parsed.get("monitor_instruction"))
    tightening = bool(
        decision in {"watch_rank1_with_tighter_gates", "avoid_rank1", "no_trade"}
        or entry_delta.get("tighten_confidence_threshold")
        or str(instruction.get("watch_intensity") or "").lower() == "strict"
    )
    return {
        "entry_tightening": tightening,
        "no_trade": decision == "no_trade",
    }


def build_stage2_authority_records(
    *,
    candidate_rows: Sequence[Mapping[str, Any]],
    windows: Mapping[str, Mapping[str, Any]],
    responses: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in candidate_rows:
        decision_id = str(row.get("q9_decision_id") or "").strip()
        role = str(row.get("q9_decision_role") or "").strip()
        if decision_id and role:
            grouped[decision_id][role].append(row)

    records: list[dict[str, Any]] = []
    for decision_id, roles in grouped.items():
        before_rows = _ranked_role_rows(roles, "R1_PRE_REFRESH_SCANNER")
        after_rows = _ranked_role_rows(roles, "R2_POST_REFRESH_SCANNER")
        before = before_rows[0] if before_rows else {}
        after = after_rows[0] if after_rows else {}
        if not before or not after:
            continue
        window = _mapping(windows.get(decision_id))
        raw_day = str(
            window.get("_day")
            or candidate_day(after)
            or candidate_day(before)
            or after.get("day")
            or before.get("day")
            or ""
        )
        day = (
            f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:8]}"
            if len(raw_day) == 8 and raw_day.isdigit()
            else raw_day[:10]
        )
        run_id = str(window.get("run_id") or "").strip()
        response = _mapping(responses.get((day, run_id)))
        parsed = _mapping(response.get("parsed"))
        before_symbol = str(before.get("symbol") or "").strip()
        after_symbol = str(after.get("symbol") or "").strip()
        first_score = _score(before)
        second_score = _score(before_rows[1]) if len(before_rows) > 1 else None
        before_return = _checkpoint_return(before, PRIMARY_HORIZON)
        after_return = _checkpoint_return(after, PRIMARY_HORIZON)
        horizon_returns = {
            horizon: {
                "before_return_pct": _checkpoint_return(before, horizon),
                "after_return_pct": _checkpoint_return(after, horizon),
            }
            for horizon in EVALUATION_HORIZONS
        }
        for values in horizon_returns.values():
            before_value = values["before_return_pct"]
            after_value = values["after_return_pct"]
            values["delta_pct"] = (
                round(float(after_value) - float(before_value), 6)
                if before_value is not None and after_value is not None
                else None
            )
        delta = (
            round(after_return - before_return, 6)
            if before_return is not None and after_return is not None
            else None
        )
        flags = _authority_flags(parsed)
        commander = _mapping(window.get("commander_final"))
        records.append(
            {
                "day": day,
                "decision_id": decision_id,
                "run_id": run_id,
                "before_symbol": before_symbol,
                "after_symbol": after_symbol,
                "candidate_changed": bool(before_symbol and after_symbol and before_symbol != after_symbol),
                "before_return_pct": before_return,
                "after_return_pct": after_return,
                "delta_pct": delta,
                "forward_evidence_available": delta is not None,
                "stage2_response_available": bool(parsed),
                "stage2_response_path": str(response.get("artifact_path") or ""),
                "selected_symbol_decision": str(parsed.get("selected_symbol_decision") or ""),
                "commander_actionability": str(parsed.get("commander_actionability") or ""),
                "entry_tightening": flags["entry_tightening"],
                "no_trade_recommended": flags["no_trade"],
                "downstream_no_trade": bool(commander.get("no_trade")),
                "downstream_reason": str(commander.get("reason") or ""),
                "decision_epoch": window.get("decision_epoch"),
                "window_generated_at": str(window.get("generated_at") or ""),
                "stage2_response_saved_at": str(response.get("saved_at") or ""),
                "stage2_response_delay_sec": _elapsed_seconds(
                    window.get("generated_at"), response.get("saved_at")
                ),
                "r1_score_margin": (
                    round(first_score - second_score, 6)
                    if first_score is not None and second_score is not None
                    else None
                ),
                "r1_rank_after_refresh": _symbol_rank(after_rows, before_symbol),
                "r2_rank_before_refresh": _symbol_rank(before_rows, after_symbol),
                "before_candidate": _candidate_snapshot(before),
                "after_candidate": _candidate_snapshot(after),
                "horizon_returns": horizon_returns,
                "stage2": _stage2_snapshot(parsed),
            }
        )
    return records


def _paired_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in records if row.get("delta_pct") is not None]
    values = [float(row["delta_pct"]) for row in comparable]
    days = {str(row.get("day") or "") for row in comparable if row.get("day")}
    by_day: dict[str, list[float]] = defaultdict(list)
    for row in comparable:
        day = str(row.get("day") or "")
        if day:
            by_day[day].append(float(row["delta_pct"]))
    day_averages = [sum(day_values) / len(day_values) for day_values in by_day.values()]
    largest_day = max((len(day_values) for day_values in by_day.values()), default=0)
    return {
        "observation_count": len(records),
        "comparison_count": len(values),
        "day_count": len(days),
        "average_delta_pct": round(sum(values) / len(values), 4) if values else None,
        "median_delta_pct": round(median(values), 4) if values else None,
        "positive_delta_rate": round(sum(value > 0 for value in values) / len(values), 4) if values else None,
        "zero_delta_rate": round(sum(value == 0 for value in values) / len(values), 4) if values else None,
        "positive_day_rate": round(sum(value > 0 for value in day_averages) / len(day_averages), 4) if day_averages else None,
        "negative_day_rate": round(sum(value < 0 for value in day_averages) / len(day_averages), 4) if day_averages else None,
        "max_single_day_share": round(largest_day / len(values), 4) if values else None,
    }


def _cohort_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [row for row in records if row.get("after_return_pct") is not None]
    returns = [float(row["after_return_pct"]) for row in observed]
    return {
        "observation_count": len(records),
        "forward_observed_count": len(observed),
        "day_count": len({str(row.get("day") or "") for row in observed if row.get("day")}),
        "average_after_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "positive_after_rate": round(sum(value > 0 for value in returns) / len(returns), 4) if returns else None,
        "downstream_no_trade_count": sum(bool(row.get("downstream_no_trade")) for row in records),
    }


def build_stage2_authority_review(
    *,
    start: str,
    end: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    pipeline_metrics = _paired_metrics(records)
    attributable = [row for row in records if bool(row.get("stage2_response_available"))]
    rerank_metrics = _paired_metrics(attributable)
    changed = [row for row in attributable if bool(row.get("candidate_changed"))]
    change_metrics = _paired_metrics(changed)
    tightening = [row for row in records if bool(row.get("entry_tightening"))]
    no_trade = [row for row in records if bool(row.get("no_trade_recommended"))]
    rerank = {**rerank_metrics, **classify_paired_effect(rerank_metrics)}
    candidate_change = {**change_metrics, **classify_paired_effect(change_metrics)}
    rerank_promotion = classify_promotion_eligibility(
        rerank_metrics, effect_state=str(rerank.get("state") or "")
    )
    candidate_change_promotion = classify_promotion_eligibility(
        change_metrics, effect_state=str(candidate_change.get("state") or "")
    )
    response_count = sum(bool(row.get("stage2_response_available")) for row in records)
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "evaluation_only",
        "range": {"start": start, "end": end},
        "primary_horizon": PRIMARY_HORIZON,
        "integrity": {
            "refresh_record_count": len(records),
            "forward_comparable_count": pipeline_metrics["comparison_count"],
            "stage2_attributable_comparable_count": rerank_metrics["comparison_count"],
            "stage2_response_count": response_count,
            "stage2_response_coverage": round(response_count / len(records), 4) if records else 0.0,
        },
        "authorities": {
            "refresh_pipeline_all": {
                **pipeline_metrics,
                "state": "OBSERVATIONAL_ONLY",
                "reason": "Includes refresh windows without a directly linked Stage-2 response; it cannot authorize an authority change.",
                "advisory_candidate_eligible": False,
            },
            "rerank": {
                **rerank,
                "causal_scope": "first Scanner Top-1 versus post-refresh Scanner Top-1 with a directly linked Stage-2 response",
                "promotion_eligibility": rerank_promotion,
                "advisory_candidate_eligible": bool(rerank_promotion["eligible"]),
            },
            "candidate_change": {
                **candidate_change,
                "causal_scope": "windows where the post-refresh Top-1 symbol changed",
                "promotion_eligibility": candidate_change_promotion,
                "advisory_candidate_eligible": bool(candidate_change_promotion["eligible"]),
            },
            "entry_tightening": {
                **_cohort_metrics(tightening),
                "state": "NOT_MEASURABLE",
                "reason": "Stage-2 recommendation is captured, but an explicit downstream adoption trace and untreated paired control are absent.",
                "missing_control": "applied Stage-2 tightening versus identical untreated Monitor decision",
                "advisory_candidate_eligible": False,
            },
            "no_trade": {
                **_cohort_metrics(no_trade),
                "state": "NOT_MEASURABLE",
                "reason": "Stage-2 no-trade recommendation is captured, but Commander/Monitor may independently veto the same candidate.",
                "missing_control": "Stage-2-attributed veto versus identical Commander/Monitor decision without the recommendation",
                "advisory_candidate_eligible": False,
            },
        },
        "records": [dict(row) for row in records],
        "behavior_change_authorized": False,
        "decision_rule": "A material paired effect is only a signal. A behavior patch also requires distributed and directionally stable evidence under the promotion stability contract.",
    }
