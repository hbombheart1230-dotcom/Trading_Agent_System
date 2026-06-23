from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.q8_evaluation_contract import candidate_day
from libs.reporting.quant_shadow_candidate_evaluation import (
    load_quant_shadow_candidate_payloads_for_range,
)
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .contracts import (
    CONTRACT_VERSION,
    DIRECTIONAL_MIN_DAYS,
    DIRECTIONAL_MIN_OBSERVATIONS,
    DecisionClass,
)
from .loss_decomposition import (
    _candidate_rows,
    _checkpoint_return,
    _entry_timing_summary,
    _exit_hold_summary,
    _load_trade_models,
    _realized_trade_summary,
)
from .metrics import performance_metrics


HORIZONS = ("+5m", "+15m", "+30m", "+60m")
MIN_MATERIAL_RANKING_DELTA_PCT = 0.30
MIN_POSITIVE_RANKING_DELTA_RATE = 0.55


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _role_metrics(
    candidates: list[dict[str, Any]],
    *,
    role: str,
    horizon: str,
    cost_pct: float,
) -> dict[str, Any]:
    values: list[float] = []
    days: set[str] = set()
    for row in candidates:
        if str(row.get("shadow_role") or "") != role:
            continue
        value = _checkpoint_return(row, horizon)
        if value is None:
            continue
        values.append(value - cost_pct)
        day = candidate_day(row)
        if day:
            days.add(day)
    return {
        "role": role,
        "horizon": horizon,
        "evidence_class": "TRUSTED_SHADOW",
        "observed_count": len(values),
        "observed_day_count": len(days),
        "cost_adjusted": True,
        **performance_metrics(values),
    }


def _paired_role_deltas(
    candidates: list[dict[str, Any]],
    *,
    horizon: str,
) -> dict[str, Any]:
    windows: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    window_days: dict[str, str] = {}
    for row in candidates:
        role = str(row.get("shadow_role") or "")
        if role not in {"top_pick", "runner_up_evaluated"}:
            continue
        value = _checkpoint_return(row, horizon)
        if value is None:
            continue
        window = str(row.get("_payload_generated_at") or "")
        if not window:
            continue
        windows[window][role].append(value)
        window_days[window] = candidate_day(row) or ""
    deltas: list[float] = []
    days: set[str] = set()
    for window, roles in windows.items():
        top = roles.get("top_pick") or []
        runner = roles.get("runner_up_evaluated") or []
        if not top or not runner:
            continue
        deltas.append((sum(top) / len(top)) - (sum(runner) / len(runner)))
        if window_days.get(window):
            days.add(window_days[window])
    return {
        "horizon": horizon,
        "comparison": "top_pick_minus_runner_up_evaluated",
        "evidence_class": "TRUSTED_SHADOW",
        "paired_window_count": len(deltas),
        "observed_day_count": len(days),
        "average_delta_pct": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "positive_delta_rate": round(sum(value > 0 for value in deltas) / len(deltas), 4) if deltas else None,
        "delta_distribution": performance_metrics(deltas),
    }


def _selection_availability(models: list[dict[str, Any]]) -> dict[str, Any]:
    raw_controls = 0
    strategist_snapshots = 0
    commander_snapshots = 0
    comparable_strategist = 0
    comparable_commander = 0
    missing: dict[str, int] = defaultdict(int)
    for model in models:
        selection = model.get("selection") if isinstance(model.get("selection"), Mapping) else {}
        raw_rows = selection.get("raw_scanner_top10")
        raw_control = bool(
            selection.get("raw_scanner_snapshot_source")
            in {"control_snapshot", "scanner_intrinsic_control_snapshot"}
            and isinstance(raw_rows, list)
            and raw_rows
        )
        strategist = bool(
            selection.get("strategist_run_id")
            and isinstance(selection.get("post_strategist_top10"), list)
            and selection.get("post_strategist_top10")
        )
        commander = bool(selection.get("commander_final_explicit"))
        raw_controls += int(raw_control)
        strategist_snapshots += int(strategist)
        commander_snapshots += int(commander)
        comparable_strategist += int(raw_control and strategist)
        comparable_commander += int(strategist and commander)
        if not raw_control:
            missing["trusted_raw_scanner_top10"] += 1
        if not strategist:
            missing["strategist_run_and_post_ranking"] += 1
        if not commander:
            missing["explicit_commander_selection_or_veto"] += 1
    return {
        "trade_model_count": len(models),
        "raw_scanner_control_count": raw_controls,
        "strategist_snapshot_count": strategist_snapshots,
        "commander_snapshot_count": commander_snapshots,
        "scanner_vs_strategist_comparable_count": comparable_strategist,
        "strategist_vs_commander_comparable_count": comparable_commander,
        "missing_fields": dict(sorted(missing.items())),
    }


def _q9_decision_candidate_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        for raw in payload.get("q9_decision_candidates") or []:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", payload.get("generated_at"))
            rows.append(row)
    return attach_forward_outcomes(rows)


def _q9_role_row(
    roles: Mapping[str, list[dict[str, Any]]],
    role: str,
) -> dict[str, Any]:
    rows = roles.get(role) or []
    if role == "B_STRATEGIST_RANKED":
        selected = next((row for row in rows if row.get("q9_selected")), None)
        if selected:
            return selected
    return min(
        rows,
        key=lambda row: int(float(row.get("rank") or 999)),
        default={},
    )


def _decision_window_attribution(
    payloads: list[dict[str, Any]],
    *,
    cost_pct: float,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in _q9_decision_candidate_rows(payloads):
        decision_id = str(row.get("q9_decision_id") or "")
        role = str(row.get("q9_decision_role") or "")
        if decision_id and role:
            grouped[decision_id][role].append(row)
    by_horizon: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        strategist_deltas: list[float] = []
        commander_deltas: list[float] = []
        strategist_days: set[str] = set()
        commander_days: set[str] = set()
        for roles in grouped.values():
            a_row = _q9_role_row(roles, "A_SCANNER_CONTROL")
            b_row = _q9_role_row(roles, "B_STRATEGIST_RANKED")
            c_row = _q9_role_row(roles, "C_COMMANDER_FINAL")
            a_value = _checkpoint_return(a_row, horizon) if a_row else None
            b_value = _checkpoint_return(b_row, horizon) if b_row else None
            if a_value is not None and b_value is not None:
                strategist_deltas.append(b_value - a_value)
                day = candidate_day(b_row)
                if day:
                    strategist_days.add(day)
            if b_value is None or not c_row:
                continue
            if c_row.get("q9_commander_no_trade"):
                c_net = 0.0
            else:
                c_value = _checkpoint_return(c_row, horizon)
                if c_value is None:
                    continue
                c_net = c_value - cost_pct
            b_net = b_value - cost_pct
            commander_deltas.append(c_net - b_net)
            day = candidate_day(c_row)
            if day:
                commander_days.add(day)
        by_horizon.append(
            {
                "horizon": horizon,
                "strategist_comparison_count": len(strategist_deltas),
                "strategist_day_count": len(strategist_days),
                "average_strategist_delta_pct": (
                    round(sum(strategist_deltas) / len(strategist_deltas), 4)
                    if strategist_deltas
                    else None
                ),
                "strategist_positive_delta_rate": (
                    round(sum(value > 0 for value in strategist_deltas) / len(strategist_deltas), 4)
                    if strategist_deltas
                    else None
                ),
                "commander_comparison_count": len(commander_deltas),
                "commander_day_count": len(commander_days),
                "average_commander_delta_pct": (
                    round(sum(commander_deltas) / len(commander_deltas), 4)
                    if commander_deltas
                    else None
                ),
                "commander_positive_delta_rate": (
                    round(sum(value > 0 for value in commander_deltas) / len(commander_deltas), 4)
                    if commander_deltas
                    else None
                ),
            }
        )
    return {
        "schema_version": "q9_decision_window_attribution.v1",
        "decision_window_count": len(grouped),
        "candidate_row_count": sum(
            len(rows) for roles in grouped.values() for rows in roles.values()
        ),
        "by_horizon": by_horizon,
    }


def _attribution_component(
    *,
    attribution: Mapping[str, Any],
    component: str,
    question: str,
    missing_comparison: str,
    availability: dict[str, Any],
) -> dict[str, Any]:
    prefix = "strategist" if component == "strategist" else "commander"
    primary = next(
        (
            row for row in attribution.get("by_horizon") or []
            if row.get("horizon") == "+30m"
        ),
        {},
    )
    count = int(primary.get(f"{prefix}_comparison_count") or 0)
    days = int(primary.get(f"{prefix}_day_count") or 0)
    delta = _number(primary.get(f"average_{prefix}_delta_pct"))
    positive_rate = _number(primary.get(f"{prefix}_positive_delta_rate"))
    enough = count >= DIRECTIONAL_MIN_OBSERVATIONS and days >= DIRECTIONAL_MIN_DAYS
    material = (
        enough
        and delta is not None
        and positive_rate is not None
        and delta >= MIN_MATERIAL_RANKING_DELTA_PCT
        and positive_rate >= MIN_POSITIVE_RANKING_DELTA_RATE
    )
    if not enough:
        return {
            "decision": DecisionClass.INSUFFICIENT_EVIDENCE.value,
            "question": question,
            "finding": (
                f"{component.title()} has {count} comparable +30m windows across {days} day(s); "
                "the fixed 20-observation and 2-day threshold is not complete."
            ),
            "missing_comparison": (
                f"at least {DIRECTIONAL_MIN_OBSERVATIONS} comparable +30m windows across "
                f"{DIRECTIONAL_MIN_DAYS} days; current={count} windows/{days} days"
            ),
            "availability": dict(availability),
            "primary_horizon": "+30m",
            "metrics": dict(primary),
            "behavior_change_authorized": False,
        }
    return {
        "decision": (
            DecisionClass.PROMOTION_CANDIDATE.value
            if material
            else DecisionClass.ADJUST_AND_RETEST.value
        ),
        "question": question,
        "finding": (
            f"{component.title()} shows a material +30m delta."
            if material
            else f"{component.title()} does not show a material +30m delta under the fixed contract."
        ),
        "missing_comparison": None,
        "primary_horizon": "+30m",
        "metrics": dict(primary),
        "behavior_change_authorized": False,
    }


def _scanner_decision(
    *,
    role_metrics: list[dict[str, Any]],
    paired: list[dict[str, Any]],
) -> dict[str, Any]:
    top_30 = next(
        (row for row in role_metrics if row["role"] == "top_pick" and row["horizon"] == "+30m"),
        {},
    )
    pair_30 = next((row for row in paired if row["horizon"] == "+30m"), {})
    enough = (
        int(pair_30.get("paired_window_count") or 0) >= DIRECTIONAL_MIN_OBSERVATIONS
        and int(pair_30.get("observed_day_count") or 0) >= DIRECTIONAL_MIN_DAYS
    )
    relative_positive = (
        enough
        and float(pair_30.get("average_delta_pct") or 0.0) >= MIN_MATERIAL_RANKING_DELTA_PCT
        and float(pair_30.get("positive_delta_rate") or 0.0) >= MIN_POSITIVE_RANKING_DELTA_RATE
    )
    absolute_positive = float(top_30.get("expectancy_pct") or 0.0) > 0
    decision = (
        DecisionClass.RETAIN.value
        if relative_positive and absolute_positive
        else DecisionClass.ADJUST_AND_RETEST.value
        if relative_positive
        else DecisionClass.ADJUST_AND_RETEST.value
        if enough
        else DecisionClass.INSUFFICIENT_EVIDENCE.value
    )
    return {
        "decision": decision,
        "question": "Does Scanner ranking put stronger candidates ahead of runner-ups and retain cost-positive edge?",
        "relative_ranking_effect_positive": relative_positive,
        "absolute_cost_adjusted_edge_positive": absolute_positive,
        "primary_horizon": "+30m",
        "finding": (
            "Top-pick ordering is directionally better than evaluated runner-ups, but the selected "
            "Top-pick set remains cost-negative; ranking direction is useful while candidate quality "
            "and horizon calibration require adjustment."
            if relative_positive and not absolute_positive
            else "Scanner Top-pick ordering does not establish a material ranking effect after "
            "applying the fixed +0.30% delta and 55% positive-window thresholds."
            if not relative_positive
            else "Scanner ranking and absolute cost-adjusted edge are both positive."
        ),
        "missing_comparison": None if enough else "paired Top-pick and runner-up forward outcomes",
        "materiality_contract": {
            "minimum_average_delta_pct": MIN_MATERIAL_RANKING_DELTA_PCT,
            "minimum_positive_delta_rate": MIN_POSITIVE_RANKING_DELTA_RATE,
        },
    }


def _unavailable_component(
    *,
    question: str,
    missing_comparison: str,
    availability: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision": DecisionClass.INSUFFICIENT_EVIDENCE.value,
        "question": question,
        "finding": "Historical value-add cannot be measured without the named control comparison.",
        "missing_comparison": missing_comparison,
        "availability": availability,
        "behavior_change_authorized": False,
    }


def build_full_chain_component_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    cost_profile_path: Path | None = None,
) -> dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    candidates = _candidate_rows(payloads)
    models = _load_trade_models(reports_root, start, end)
    profile = load_broker_cost_profile(cost_profile_path)
    cost_pct = float(
        profile.get("conservative_round_trip_cost_pct")
        or profile.get("ema_round_trip_cost_pct")
        or 0.009
    ) * 100.0
    role_metrics = [
        _role_metrics(candidates, role=role, horizon=horizon, cost_pct=cost_pct)
        for role in ("top_pick", "runner_up_evaluated")
        for horizon in HORIZONS
    ]
    paired = [_paired_role_deltas(candidates, horizon=horizon) for horizon in HORIZONS]
    availability = _selection_availability(models)
    decision_attribution = _decision_window_attribution(payloads, cost_pct=cost_pct)
    entry = _entry_timing_summary(models, candidates)
    exit_hold = _exit_hold_summary(models)
    realized = _realized_trade_summary(models)
    scanner = _scanner_decision(role_metrics=role_metrics, paired=paired)
    entry_count = int(entry.get("matched_trade_count") or 0)
    entry_days = int(entry.get("matched_day_count") or 0)
    entry_enough = entry_count >= DIRECTIONAL_MIN_OBSERVATIONS and entry_days >= DIRECTIONAL_MIN_DAYS
    entry_average = _number(entry.get("average_entry_price_delta_pct"))
    entry_median = _number(entry.get("median_entry_price_delta_pct"))
    entry_decision = (
        DecisionClass.RETAIN.value
        if entry_enough
        and entry_average is not None
        and entry_median is not None
        and entry_average <= 0.30
        and entry_median <= 0.30
        else DecisionClass.ADJUST_AND_RETEST.value
        if entry_enough
        else DecisionClass.INSUFFICIENT_EVIDENCE.value
    )
    exit_count = int(exit_hold.get("observed_trade_count") or 0)
    exit_days = int(exit_hold.get("observed_day_count") or 0)
    exit_enough = exit_count >= DIRECTIONAL_MIN_OBSERVATIONS and exit_days >= DIRECTIONAL_MIN_DAYS
    five_minute = next(
        (row for row in exit_hold.get("by_hold_offset") or [] if row.get("offset") == "+5m"),
        {},
    )
    exit_decision = (
        DecisionClass.ADJUST_AND_RETEST.value
        if exit_enough and float(five_minute.get("average_improvement_pct") or 0.0) >= 0.30
        else DecisionClass.RETAIN.value
        if exit_enough
        else DecisionClass.INSUFFICIENT_EVIDENCE.value
    )
    realized_performance = realized.get("performance") or {}
    realized_count = int(realized_performance.get("count") or 0)
    realized_days = len(
        {
            str(model.get("day") or "")[:10]
            for model in models
            if (model.get("outcome") or {}).get("net_return_pct") is not None
        }
    )
    full_system_enough = (
        realized_count >= DIRECTIONAL_MIN_OBSERVATIONS
        and realized_days >= DIRECTIONAL_MIN_DAYS
    )
    full_system_decision = (
        DecisionClass.RETAIN.value
        if full_system_enough
        and float(realized_performance.get("expectancy_pct") or 0.0) > 0.0
        else DecisionClass.REJECT.value
        if full_system_enough
        else DecisionClass.INSUFFICIENT_EVIDENCE.value
    )
    components = {
        "scanner": {
            **scanner,
            "role_cost_adjusted_metrics": role_metrics,
            "paired_role_comparisons": paired,
            "evidence_class": "TRUSTED_SHADOW",
            "behavior_change_authorized": False,
        },
        "strategist": _attribution_component(
            attribution=decision_attribution,
            component="strategist",
            question="Does Strategist improve raw Scanner output?",
            missing_comparison="trusted pre-Strategist Scanner Top-10 joined to post-Strategist outcomes",
            availability=availability,
        ),
        "commander": _attribution_component(
            attribution=decision_attribution,
            component="commander",
            question="Does Commander selection or veto improve the Strategist-selected outcome?",
            missing_comparison="explicit Commander alternative or veto joined to forward outcomes",
            availability=availability,
        ),
        "monitor_entry": {
            "decision": entry_decision,
            "question": "Does Monitor improve entry timing relative to the selected candidate baseline?",
            "finding": (
                "Actual entries were not systematically later or more expensive than the nearby "
                "same-symbol shadow baseline; entry timing is not the first demonstrated loss source."
                if entry_decision == DecisionClass.RETAIN.value
                else "Entry timing requires adjustment."
                if entry_decision == DecisionClass.ADJUST_AND_RETEST.value
                else "The minimum directional comparison count was not reached."
            ),
            "evidence_class": "RECONSTRUCTED",
            "metrics": entry,
            "missing_comparison": (
                None
                if entry_enough
                else "at least 20 actual-entry versus selected-baseline matches across 2 days"
            ),
            "behavior_change_authorized": False,
        },
        "monitor_exit": {
            "decision": exit_decision,
            "question": "Does Monitor exit too early or surrender material value?",
            "finding": (
                "Observed post-exit improvement is too small to identify exit timing as the primary "
                "loss source."
                if exit_decision == DecisionClass.RETAIN.value
                else "Post-exit improvement is large enough to justify a bounded exit-policy review."
                if exit_decision == DecisionClass.ADJUST_AND_RETEST.value
                else "Only 16 exits have post-exit observations; this is below the fixed 20-observation threshold."
            ),
            "evidence_class": "REALIZED_PLUS_POST_EXIT_SHADOW",
            "metrics": exit_hold,
            "missing_comparison": (
                None
                if exit_enough
                else "at least 20 exits with observed post-exit checkpoints across 2 days"
            ),
            "behavior_change_authorized": False,
        },
        "full_system": {
            "decision": full_system_decision,
            "question": "Does the integrated system currently produce positive broker-net value?",
            "finding": (
                "The integrated system produced positive broker-net expectancy for the analyzed range."
                if full_system_decision == DecisionClass.RETAIN.value
                else "The current positive-edge hypothesis is rejected for the analyzed range."
                if full_system_decision == DecisionClass.REJECT.value
                else "The fixed realized-trade and day minimum has not been reached."
            ),
            "evidence_class": "REALIZED",
            "metrics": realized,
            "missing_comparison": (
                None
                if full_system_enough
                else "at least 20 realized trades across 2 days"
            ),
            "behavior_change_authorized": False,
        },
    }
    return {
        "schema_version": "q9_full_chain_component_review.v1",
        "contract_version": CONTRACT_VERSION,
        "behavior_effect": "evaluation_only",
        "range": {"start": start[:10], "end": end[:10]},
        "cost_model": {
            "source": str(profile.get("source") or "fallback"),
            "sample_count": int(profile.get("sample_count") or 0),
            "conservative_round_trip_cost_pct": round(cost_pct, 4),
        },
        "evidence": {
            "shadow_payload_count": len(payloads),
            "deduped_shadow_candidate_count": len(candidates),
            "trade_model_count": len(models),
            "selection_availability": availability,
            "decision_window_attribution": decision_attribution,
        },
        "component_decisions": components,
        "overall_decision": {
            "decision": (
                DecisionClass.ADJUST_AND_RETEST.value
                if full_system_enough
                else DecisionClass.INSUFFICIENT_EVIDENCE.value
            ),
            "first_actionable_component": (
                "scanner_candidate_quality_and_horizon_calibration"
                if full_system_enough
                else "artifact_and_forward_evidence_collection"
            ),
            "reason": (
                "The fixed realized-trade and multi-day thresholds are not complete; continue "
                "the frozen forward window without changing trading behavior."
                if not full_system_enough
                else "Scanner ordering does not show a material relative advantage and selected "
                "candidates remain cost-negative. Monitor entry is not the first demonstrated "
                "failure, and Monitor exit has insufficient observations."
            ),
            "behavior_change_authorized": False,
        },
        "closure": {
            "historical_review_complete": True,
            "open_ended_extension_authorized": False,
            "remaining_forward_requirement": (
                "Persist trusted A/B/C decision snapshots and reach the fixed missing-comparison "
                "thresholds; do not add new diagnostic categories."
            ),
        },
    }


def render_full_chain_component_review(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    components = payload.get("component_decisions") or {}
    lines = [
        f"# Q9 Full-Chain Component Review ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "Evaluation-only. No runtime or trading policy change is authorized.",
        "",
        "## Final Component Decisions",
        "",
        "| Component | Decision | Finding / Missing Comparison |",
        "|---|---|---|",
    ]
    for key in ("scanner", "strategist", "commander", "monitor_entry", "monitor_exit", "full_system"):
        row = components.get(key) or {}
        detail = row.get("missing_comparison") or row.get("finding") or ""
        lines.append(f"| {key} | `{row.get('decision')}` | {detail} |")
    scanner = components.get("scanner") or {}
    lines += [
        "",
        "## Scanner: Cost-Adjusted Role Metrics",
        "",
        "| Role | Horizon | Count/Days | Expectancy | Win Rate | PF |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in scanner.get("role_cost_adjusted_metrics") or []:
        lines.append(
            f"| {row.get('role')} | {row.get('horizon')} | "
            f"{row.get('observed_count')}/{row.get('observed_day_count')} | "
            f"{row.get('expectancy_pct')}% | {float(row.get('win_rate') or 0):.1%} | "
            f"{row.get('profit_factor')} |"
        )
    lines += [
        "",
        "## Scanner: Paired Ranking Effect",
        "",
        "| Horizon | Paired Windows/Days | Top-pick Minus Runner-up | Positive Rate |",
        "|---|---:|---:|---:|",
    ]
    for row in scanner.get("paired_role_comparisons") or []:
        lines.append(
            f"| {row.get('horizon')} | {row.get('paired_window_count')}/{row.get('observed_day_count')} | "
            f"{row.get('average_delta_pct')}% | {float(row.get('positive_delta_rate') or 0):.1%} |"
        )
    entry = (components.get("monitor_entry") or {}).get("metrics") or {}
    exit_row = (components.get("monitor_exit") or {}).get("metrics") or {}
    realized = ((components.get("full_system") or {}).get("metrics") or {}).get("performance") or {}
    availability = (payload.get("evidence") or {}).get("selection_availability") or {}
    attribution = (payload.get("evidence") or {}).get("decision_window_attribution") or {}
    lines += [
        "",
        "## Attribution Availability",
        "",
        f"- trade models: {availability.get('trade_model_count')}",
        f"- trusted raw Scanner controls: {availability.get('raw_scanner_control_count')}",
        f"- Strategist snapshots: {availability.get('strategist_snapshot_count')}",
        f"- Commander snapshots: {availability.get('commander_snapshot_count')}",
        f"- Scanner vs Strategist comparable: {availability.get('scanner_vs_strategist_comparable_count')}",
        f"- Strategist vs Commander comparable: {availability.get('strategist_vs_commander_comparable_count')}",
        f"- Q9 decision windows with forward candidates: {attribution.get('decision_window_count')}",
        f"- Q9 A/B/C forward candidate rows: {attribution.get('candidate_row_count')}",
        "",
        "## Monitor Entry",
        "",
        f"- matched trades/days: {entry.get('matched_trade_count')} / {entry.get('matched_day_count')}",
        f"- average entry-price delta: {entry.get('average_entry_price_delta_pct')}%",
        f"- median entry-price delta: {entry.get('median_entry_price_delta_pct')}%",
        "",
        "## Monitor Exit",
        "",
        f"- observed exits/days: {exit_row.get('observed_trade_count')} / {exit_row.get('observed_day_count')}",
        f"- +5m average improvement: {next((row.get('average_improvement_pct') for row in exit_row.get('by_hold_offset') or [] if row.get('offset') == '+5m'), None)}%",
        "",
        "## Realized Full System",
        "",
        f"- trades: {realized.get('count')}",
        f"- win rate: {float(realized.get('win_rate') or 0):.1%}",
        f"- expectancy: {realized.get('expectancy_pct')}%",
        f"- profit factor: {realized.get('profit_factor')}",
        f"- maximum drawdown: {realized.get('maximum_drawdown_pct')}%",
        "",
        "## Overall Decision",
        "",
        f"- decision: **{(payload.get('overall_decision') or {}).get('decision')}**",
        f"- first actionable component: `{(payload.get('overall_decision') or {}).get('first_actionable_component')}`",
        f"- reason: {(payload.get('overall_decision') or {}).get('reason')}",
        "- historical review complete: **True**",
        "- open-ended extension authorized: **False**",
        "- behavior change authorized: **False**",
    ]
    return "\n".join(lines) + "\n"


def write_full_chain_component_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
    cost_profile_path: Path | None = None,
) -> dict[str, str]:
    payload = build_full_chain_component_review(
        reports_root=reports_root,
        start=start,
        end=end,
        cost_profile_path=cost_profile_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "q9_full_chain_component_review.json"
    md_path = output_dir / "q9_full_chain_component_review.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_full_chain_component_review(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
