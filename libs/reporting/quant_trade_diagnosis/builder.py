from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return _mapping(value)
    except Exception:
        return {}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _candidate_symbol(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("symbol") or value.get("code"))
    return _text(value)


def _strategy_candidate_scores(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    strategist = _mapping(lifecycle.get("strategist_summary") or lifecycle.get("strategist"))
    parsed = _mapping(strategist.get("llm_parsed_output"))
    candidate_keys = (
        "strategy_candidates",
        "strategy_options",
        "candidate_strategies",
        "tactical_options",
        "tactic_candidates",
        "scenario_scores",
    )
    candidates: list[dict[str, Any]] = []
    source = ""
    for key in candidate_keys:
        value = parsed.get(key)
        if not isinstance(value, list):
            continue
        for row in _rows(value):
            name = _first_text(
                row.get("strategy"),
                row.get("tactic"),
                row.get("name"),
                row.get("scenario"),
                row.get("id"),
            )
            if not name:
                continue
            candidates.append(
                {
                    "name": name,
                    "score": _number(
                        row.get("score")
                        if row.get("score") is not None
                        else row.get("suitability_score")
                    ),
                    "result": _first_text(
                        row.get("result"),
                        row.get("status"),
                        row.get("decision"),
                    ),
                    "reason": _text(row.get("reason")),
                }
            )
        if candidates:
            source = f"lifecycle.strategist_summary.llm_parsed_output.{key}"
            break
    return {
        "available": bool(candidates),
        "source": source,
        "rows": candidates,
        "status": "AVAILABLE" if candidates else "INSUFFICIENT_EVIDENCE",
    }


def _market_context(
    lifecycle: Mapping[str, Any],
    summary_input: Mapping[str, Any],
) -> dict[str, Any]:
    strategist = _mapping(lifecycle.get("strategist_summary") or lifecycle.get("strategist"))
    human = _mapping(lifecycle.get("market_context_human"))
    market_strategy = _mapping(summary_input.get("market_and_strategy"))
    korea_indices = _first_mapping(
        strategist.get("korea_indices"),
        human.get("korea_indices"),
    )
    return {
        "market_regime": _first_text(
            strategist.get("market_regime"),
            human.get("regime"),
        ),
        "market_regime_rail": _first_text(
            strategist.get("market_regime_rail"),
            human.get("market_regime_rail"),
        ),
        "market_sentiment": _first_text(
            strategist.get("market_sentiment"),
            human.get("market_sentiment"),
            market_strategy.get("market_sentiment"),
        ),
        "global_sentiment_score": _number(
            strategist.get("global_sentiment_score")
            if strategist.get("global_sentiment_score") is not None
            else human.get("global_sentiment_score")
        ),
        "vix_level": _number(
            human.get("vix_level")
            if human.get("vix_level") is not None
            else market_strategy.get("vix")
        ),
        "korea_indices": korea_indices,
        "playbook": _first_text(
            strategist.get("playbook"),
            market_strategy.get("playbook"),
        ),
        "risk_tone": _first_text(
            strategist.get("risk_tone"),
            _mapping(lifecycle.get("strategist_trace_summary")).get("risk_tone"),
        ),
        "trade_aggressiveness": _first_text(
            strategist.get("trade_aggressiveness"),
            _mapping(lifecycle.get("strategist_trace_summary")).get(
                "trade_aggressiveness"
            ),
        ),
        "themes": list(
            strategist.get("themes")
            or market_strategy.get("themes")
            or human.get("themes")
            or []
        ),
    }


def _selection_chain(
    model: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> dict[str, Any]:
    selection = _mapping(model.get("selection"))
    post_rows = _rows(selection.get("post_strategist_top10"))
    commander = _mapping(selection.get("commander_final"))
    executed = _text(model.get("symbol"))
    selected = _candidate_symbol(selection.get("selected_symbol"))
    chain = {
        "raw_scanner_top1": _candidate_symbol(selection.get("raw_scanner_top1")),
        "scanner_top1": _candidate_symbol(selection.get("scanner_top1")),
        "post_strategy_top1": _candidate_symbol(post_rows[0]) if post_rows else "",
        "selected_symbol": selected,
        "commander_candidate": _candidate_symbol(
            commander.get("symbol")
            or commander.get("selected_symbol")
            or commander.get("candidate")
        ),
        "executed_symbol": executed,
        "selected_rank": selection.get("selected_rank"),
        "selection_mismatch": bool(selection.get("selection_mismatch")),
        "q9_decision_id": _text(selection.get("q9_decision_id")),
        "source": _text(selection.get("q9_snapshot_source")),
    }
    known = [
        value
        for value in (
            chain["raw_scanner_top1"],
            chain["post_strategy_top1"],
            chain["selected_symbol"],
            chain["commander_candidate"],
            chain["executed_symbol"],
        )
        if value
    ]
    chain["consistent"] = len(set(known)) <= 1 if known else None
    if not chain["selected_symbol"]:
        chain["selected_symbol"] = _text(lifecycle.get("selected_symbol"))
    return chain


def _scanner_diagnosis(
    model: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> dict[str, Any]:
    selection = _mapping(model.get("selection"))
    human = _mapping(lifecycle.get("scanner_reason_human"))
    selected_candidate = _first_mapping(
        selection.get("selected_candidate"),
        next(
            (
                row
                for row in _rows(human.get("ranked_candidates"))
                if _candidate_symbol(row) == _text(model.get("symbol"))
            ),
            {},
        ),
    )
    score = _number(
        selected_candidate.get("score_total")
        if selected_candidate.get("score_total") is not None
        else human.get("selected_score")
    )
    confidence = _number(
        selected_candidate.get("confidence")
        if selected_candidate.get("confidence") is not None
        else human.get("confidence")
    )
    risk = _number(selected_candidate.get("risk_score"))
    rank = selection.get("selected_rank")
    if score is None and confidence is None and risk is None:
        quality = "INSUFFICIENT_EVIDENCE"
    elif rank == 1 and ((risk is not None and risk > 0.7) or (confidence is not None and confidence < 0.6)):
        quality = "WEAK_MARKET_RELATIVE_TOP1"
    elif score is not None and score >= 0.7 and (risk is None or risk <= 0.7):
        quality = "STRONG_ABSOLUTE_CANDIDATE"
    else:
        quality = "MIXED_CANDIDATE"
    score_decomposition = _first_mapping(
        human.get("score_breakdown"),
        selection.get("score_decomposition"),
    )
    return {
        "rank": rank,
        "score_total": score,
        "confidence": confidence,
        "risk_score": risk,
        "absolute_quality": quality,
        "selection_reason": _first_text(
            human.get("selection_reason"),
            human.get("summary"),
        ),
        "score_decomposition": score_decomposition,
        "q13_score_decomposition": _mapping(selection.get("score_decomposition")),
        "top_candidates": _rows(
            human.get("ranked_candidates")
            or selection.get("raw_scanner_top10")
            or selection.get("post_strategist_top10")
        )[:5],
    }


def _commander_control(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    commander = _mapping(lifecycle.get("commander_summary") or lifecycle.get("commander"))
    decision = _mapping(commander.get("commander_decision"))
    policy = _first_mapping(
        decision.get("scanner_policy"),
        commander.get("scanner_policy"),
    )
    entry_control = _mapping(policy.get("entry_control"))
    return {
        "mode": _first_text(commander.get("mode"), commander.get("runtime_mode")),
        "path": _first_text(commander.get("path"), commander.get("selected_route")),
        "risk_mode": _first_text(decision.get("risk_mode"), commander.get("risk_mode")),
        "allowed_playbooks": list(
            decision.get("allowed_playbooks")
            or commander.get("allowed_playbooks")
            or []
        ),
        "banned_playbooks": list(
            decision.get("banned_playbooks")
            or commander.get("banned_playbooks")
            or []
        ),
        "max_priority_rank": policy.get("max_priority_rank"),
        "max_runner_ups": policy.get("max_runner_ups"),
        "cascade_enabled": entry_control.get("cascade_enabled"),
        "entry_control_mode": _text(entry_control.get("mode")),
        "reason": _first_text(
            entry_control.get("reason"),
            commander.get("decision_summary"),
            commander.get("route_reason_text"),
        ),
        "strategist_cache_used": commander.get("strategist_cache_used"),
    }


def _entry_diagnosis(
    model: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    summary_input: Mapping[str, Any],
) -> dict[str, Any]:
    decision_flow = _mapping(summary_input.get("decision_flow"))
    quant = _mapping(summary_input.get("quant_tactic"))
    entry_quant = _mapping(quant.get("entry_quant_decision"))
    factors = _first_mapping(quant.get("factors"), quant.get("factor_snapshot"))
    monitor_human = _mapping(lifecycle.get("monitor_reason_human"))
    condition_scores = _mapping(monitor_human.get("entry_condition_scores"))
    grouped = _mapping(monitor_human.get("entry_grouped_logic_trace"))
    volume = _mapping(grouped.get("volume_confirmation"))
    cost = _mapping(entry_quant.get("cost_edge"))
    blockers = list(
        entry_quant.get("blockers")
        or monitor_human.get("entry_blockers")
        or condition_scores.get("entry_hard_gate_blockers")
        or []
    )
    return {
        "decision": _first_text(
            entry_quant.get("decision"),
            decision_flow.get("entry_execution_visibility"),
        ),
        "reason": _first_text(
            (model.get("entry") or {}).get("reason"),
            decision_flow.get("entry_reason"),
            monitor_human.get("entry_reason"),
        ),
        "pattern": _first_text(
            monitor_human.get("entry_pattern"),
            decision_flow.get("entry_observation"),
        ),
        "condition_path": _text(monitor_human.get("entry_condition_path")),
        "entry_quality_score": _number(
            condition_scores.get("entry_quality_score")
            if condition_scores.get("entry_quality_score") is not None
            else factors.get("entry_quality_score")
        ),
        "entry_quality_tier": _text(condition_scores.get("entry_quality_tier")),
        "hard_gate_passed": condition_scores.get("entry_hard_gate_passed"),
        "blockers": blockers,
        "volume_ratio": _number(
            volume.get("volume_ratio_effective")
            if volume.get("volume_ratio_effective") is not None
            else factors.get("volume_ratio")
        ),
        "vwap_distance_pct": _number(factors.get("vwap_distance_pct")),
        "breakout_score": _number(condition_scores.get("breakout_score")),
        "pullback_score": _number(condition_scores.get("pullback_score")),
        "cost_floor_state": _first_text(
            _mapping(entry_quant.get("cost_edge")).get("cost_floor_state"),
            factors.get("cost_floor_state"),
        ),
        "cost_adjusted_edge_pct": _number(cost.get("cost_adjusted_edge_pct")),
        "cost_drag_pct": _number(cost.get("cost_drag_pct")),
    }


def _exit_diagnosis(
    model: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> dict[str, Any]:
    human = _mapping(lifecycle.get("monitor_reason_human"))
    alignment = _mapping(evaluation.get("horizon_alignment"))
    exit_quality = _mapping(evaluation.get("exit_quality"))
    return {
        "reason": _first_text(
            human.get("trigger_type"),
            (model.get("exit") or {}).get("reason"),
        ),
        "active_exit_axis": _first_text(
            human.get("trigger_type"),
            exit_quality.get("label"),
        ),
        "position_age_seconds": _number(
            human.get("position_age_seconds")
            if human.get("position_age_seconds") is not None
            else (model.get("outcome") or {}).get("holding_seconds")
        ),
        "stop_loss_pct": _number(human.get("effective_stop_loss_pct")),
        "take_profit_pct": _number(human.get("take_profit_pct")),
        "exit_triggered": human.get("exit_triggered"),
        "horizon_alignment": alignment,
        "post_exit": {
            "status": exit_quality.get("status"),
            "best_exit_offset": exit_quality.get("best_exit_offset"),
            "max_post_exit_upside_pct": exit_quality.get(
                "max_post_exit_upside_pct"
            ),
            "max_post_exit_drawdown_pct": exit_quality.get(
                "max_post_exit_drawdown_pct"
            ),
            "checkpoints": _mapping(exit_quality.get("observed_checkpoints")),
        },
    }


def _same_symbol_sequence(
    model: Mapping[str, Any],
    all_models: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    day = _text(model.get("day"))
    symbol = _text(model.get("symbol"))
    current_id = _text(model.get("trade_id"))
    rows = []
    for candidate in all_models:
        if _text(candidate.get("day")) != day or _text(candidate.get("symbol")) != symbol:
            continue
        outcome = _mapping(candidate.get("outcome"))
        rows.append(
            {
                "trade_id": _text(candidate.get("trade_id")),
                "entry_timestamp": _text(_mapping(candidate.get("entry")).get("timestamp")),
                "exit_timestamp": _text(_mapping(candidate.get("exit")).get("timestamp")),
                "net_return_pct": _number(outcome.get("net_return_pct")),
                "holding_seconds": _number(outcome.get("holding_seconds")),
                "current_trade": _text(candidate.get("trade_id")) == current_id,
            }
        )
    return sorted(rows, key=lambda row: (row["entry_timestamp"], row["trade_id"]))


def _root_cause(
    model: Mapping[str, Any],
    root_cause_report: Mapping[str, Any],
    entry_timing_report: Mapping[str, Any],
) -> dict[str, Any]:
    trade_id = _text(model.get("trade_id"))
    q14 = next(
        (
            row
            for row in _rows(root_cause_report.get("rows"))
            if _text(row.get("trade_id")) == trade_id
        ),
        {},
    )
    timing = next(
        (
            row
            for row in _rows(entry_timing_report.get("rows"))
            if _text(row.get("trade_id")) == trade_id
        ),
        {},
    )
    labels = []
    if q14.get("root_cause"):
        labels.append(_text(q14.get("root_cause")))
    if timing.get("label") and timing.get("label") != "INSUFFICIENT_EVIDENCE":
        labels.append(_text(timing.get("label")))
    return {
        "status": "AVAILABLE" if labels else "INSUFFICIENT_EVIDENCE",
        "primary": labels[0] if labels else "INSUFFICIENT_EVIDENCE",
        "labels": labels,
        "q14": q14,
        "entry_timing": timing,
    }


def _executive_diagnosis(
    *,
    model: Mapping[str, Any],
    scanner: Mapping[str, Any],
    root_cause: Mapping[str, Any],
    entry: Mapping[str, Any],
    exit_data: Mapping[str, Any],
) -> str:
    symbol = _text(model.get("symbol")) or "unknown symbol"
    outcome = _mapping(model.get("outcome"))
    net_return = _number(outcome.get("net_return_pct"))
    result = (
        "profit"
        if net_return is not None and net_return > 0
        else "loss"
        if net_return is not None and net_return < 0
        else "flat or unresolved result"
    )
    root = _text(root_cause.get("primary"))
    quality = _text(scanner.get("absolute_quality"))
    cost_state = _text(entry.get("cost_floor_state"))
    horizon = _text(
        _mapping(exit_data.get("horizon_alignment")).get("strategy_horizon")
    )
    parts = [
        f"{symbol} finished as {result}",
        f"Scanner quality was {quality}" if quality else "",
        f"the primary diagnostic label is {root}" if root else "",
        f"entry cost state was {cost_state}" if cost_state else "",
        f"the applied horizon was {horizon}" if horizon else "",
    ]
    sentence = ". ".join(part for part in parts if part) + "."
    return ". ".join(
        segment[:1].upper() + segment[1:] if segment else segment
        for segment in sentence.split(". ")
    )


def build_quant_trade_diagnosis(
    *,
    trade_dir: Path,
    model: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    attribution: Mapping[str, Any] | None = None,
    root_cause_report: Mapping[str, Any] | None = None,
    entry_timing_report: Mapping[str, Any] | None = None,
    conditional_alpha_context: Mapping[str, Any] | None = None,
    all_models: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    trade_dir = Path(trade_dir)
    lifecycle = _read_json(trade_dir / "lifecycle_bundle.json")
    summary_input = _read_json(trade_dir / "reports" / "ai_trade_summary_input.json")
    model = dict(model)
    evaluation = dict(evaluation)
    market = _market_context(lifecycle, summary_input)
    strategy_scores = _strategy_candidate_scores(lifecycle)
    selection = _selection_chain(model, lifecycle)
    scanner = _scanner_diagnosis(model, lifecycle)
    commander = _commander_control(lifecycle)
    entry = _entry_diagnosis(model, lifecycle, summary_input)
    exit_data = _exit_diagnosis(model, evaluation, lifecycle)
    root_cause = _root_cause(
        model,
        root_cause_report or {},
        entry_timing_report or {},
    )
    outcome = {
        **_mapping(model.get("outcome")),
        "broker_authoritative": _mapping(model.get("exit")).get(
            "broker_authoritative"
        ),
        "broker_truth_source": _mapping(model.get("exit")).get(
            "broker_truth_source"
        ),
        "integrity": _mapping(model.get("integrity")),
    }
    sequence = _same_symbol_sequence(model, all_models)
    executive = _executive_diagnosis(
        model=model,
        scanner=scanner,
        root_cause=root_cause,
        entry=entry,
        exit_data=exit_data,
    )
    quant_interpretation = {
        "entry_cost_edge_positive": (
            entry.get("cost_adjusted_edge_pct") is not None
            and float(entry["cost_adjusted_edge_pct"]) > 0
        ),
        "statistical_plausibility_status": "INSUFFICIENT_EVIDENCE",
        "thesis_statistically_plausible": None,
        "statistical_plausibility_note": (
            "A positive entry cost edge is a point-in-time estimate, not "
            "statistical evidence across independent samples."
        ),
        "cost_edge_status": (
            "POSITIVE"
            if entry.get("cost_adjusted_edge_pct") is not None
            and float(entry["cost_adjusted_edge_pct"]) > 0
            else "NON_POSITIVE_OR_UNAVAILABLE"
        ),
        "horizon_status": _mapping(exit_data.get("horizon_alignment")).get(
            "status"
        ),
        "selection_quality": scanner.get("absolute_quality"),
        "primary_attribution_axis": root_cause.get("primary"),
        "primary_failure_axis": (
            root_cause.get("primary")
            if _number(outcome.get("net_return_pct")) is not None
            and float(outcome["net_return_pct"]) < 0
            else None
        ),
    }
    return {
        "schema_version": "quant_trade_diagnosis.v1",
        "behavior_effect": "diagnostic_only",
        "authority": {
            "pnl": "broker_truth",
            "selection": "q9_trade_read_model",
            "attribution": "q13_q14_reports",
            "missing_evidence_policy": "do_not_infer",
        },
        "trade": {
            "trade_id": model.get("trade_id"),
            "day": model.get("day"),
            "symbol": model.get("symbol"),
            "status": model.get("status"),
        },
        "executive_diagnosis": executive,
        "market_and_strategy": market,
        "strategy_candidate_scores": strategy_scores,
        "selection_authority_chain": selection,
        "scanner_ranking": scanner,
        "commander_control": commander,
        "monitor_entry": entry,
        "monitor_exit": exit_data,
        "trade_outcome": outcome,
        "same_symbol_sequence": sequence,
        "root_cause_attribution": root_cause,
        "conditional_alpha_context": dict(conditional_alpha_context or {}),
        "selection_counterfactual": dict(attribution or {}),
        "quant_interpretation": quant_interpretation,
        "next_evaluation_questions": [
            "Did Scanner Top1 outperform Top3 and Top5 alternatives after cost?",
            "Did the selected setup have positive directional edge after cost?",
            "Did the actual exit comply with the persisted strategy horizon?",
            "Would a later horizon checkpoint have improved the realized exit?",
            "Did repeated same-symbol exposure add or destroy expectancy?",
        ],
        "evidence": {
            "trade_dir": str(trade_dir),
            "q9_trade_read_model_schema": model.get("schema_version"),
            "trade_evaluation_schema": evaluation.get("schema_version"),
            "lifecycle_available": bool(lifecycle),
            "summary_input_available": bool(summary_input),
        },
    }
