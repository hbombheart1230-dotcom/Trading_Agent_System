from __future__ import annotations

from typing import Any, Callable, Dict, List

from libs.reporting.trade_execution_outcome_text import execution_outcome_summary_is_placeholder
from libs.reporting.trade_report_common import (
    compact_named_rows,
    compact_scalar_dict,
    listify,
    report_clip,
)


def as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}

def compact_section_seed_for_llm(value: Any) -> Dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    out = {
        "summary": report_clip(row.get("summary"), max_len=220),
        "bullets": listify(row.get("bullets"), max_items=2, max_len=140),
        "status": report_clip(row.get("status"), max_len=24),
        "grade": report_clip(row.get("grade"), max_len=16),
        "current_action": report_clip(row.get("current_action"), max_len=24),
        "watch_next": listify(row.get("watch_next"), max_items=2, max_len=120),
        "thesis_invalidation": listify(row.get("thesis_invalidation"), max_items=2, max_len=120),
    }
    return {key: val for key, val in out.items() if val not in ("", None, [], {})}


def sparse_story_input_for_llm(
    story_input: Dict[str, Any],
    *,
    compact_story_input_for_llm: Callable[[Dict[str, Any]], Dict[str, Any]],
    reporter_summary_is_placeholder: Callable[[Any], bool],
    compact_timeline_rows: Callable[..., List[Dict[str, Any]]],
) -> Dict[str, Any]:
    compact = compact_story_input_for_llm(story_input)
    commander = compact.get("commander") if isinstance(compact.get("commander"), dict) else {}
    entry = compact.get("entry_summary") if isinstance(compact.get("entry_summary"), dict) else {}
    exit_summary = compact.get("exit_summary") if isinstance(compact.get("exit_summary"), dict) else {}
    market = compact.get("market_context_human") if isinstance(compact.get("market_context_human"), dict) else {}
    scanner = compact.get("scanner_reason_human") if isinstance(compact.get("scanner_reason_human"), dict) else {}
    monitor = compact.get("monitor_reason_human") if isinstance(compact.get("monitor_reason_human"), dict) else {}
    filters_human = compact.get("filters_human") if isinstance(compact.get("filters_human"), dict) else {}
    guard = compact.get("guard_reason_human") if isinstance(compact.get("guard_reason_human"), dict) else {}
    execution = compact.get("execution_outcome_human") if isinstance(compact.get("execution_outcome_human"), dict) else {}
    reporter = compact.get("reporter_status_human") if isinstance(compact.get("reporter_status_human"), dict) else {}
    conclusion = compact.get("operator_conclusion_human") if isinstance(compact.get("operator_conclusion_human"), dict) else {}
    entry_visibility = compact.get("entry_execution_visibility") if isinstance(compact.get("entry_execution_visibility"), dict) else {}
    report_section_seeds = compact.get("report_section_seeds") if isinstance(compact.get("report_section_seeds"), dict) else {}
    execution_seed = as_dict(report_section_seeds.get("execution_quality"))
    if execution.get("summary") and execution_outcome_summary_is_placeholder(execution_seed.get("summary")):
        execution_seed = dict(execution_seed)
        execution_seed["summary"] = execution.get("summary")
        if execution.get("bullets"):
            execution_seed["bullets"] = listify(execution.get("bullets"), max_items=4, max_len=180)
        if execution.get("status"):
            execution_seed["status"] = execution.get("status")
    guard_seed = as_dict(report_section_seeds.get("guard_approval_result"))
    reporter_seed = as_dict(report_section_seeds.get("reporter_evaluation"))
    if reporter_summary_is_placeholder(reporter.get("summary")) and report_clip(reporter_seed.get("summary"), max_len=220):
        reporter = dict(reporter)
        reporter["summary"] = report_clip(reporter_seed.get("summary"), max_len=220)
        if reporter_seed.get("bullets"):
            reporter["bullets"] = listify(reporter_seed.get("bullets"), max_items=4, max_len=180)
        if reporter_seed.get("status"):
            reporter["status"] = report_clip(reporter_seed.get("status"), max_len=24)
        if reporter_seed.get("grade"):
            reporter["grade"] = report_clip(reporter_seed.get("grade"), max_len=16)
    conclusion_seed = as_dict(report_section_seeds.get("final_operator_conclusion"))
    holding = compact.get("holding_summary") if isinstance(compact.get("holding_summary"), dict) else {}
    lifecycle = compact.get("lifecycle_summary") if isinstance(compact.get("lifecycle_summary"), dict) else {}
    diagnostics = compact.get("ai_report_diagnostics") if isinstance(compact.get("ai_report_diagnostics"), dict) else {}
    return {
        "trade_id": compact.get("trade_id"),
        "story_id": compact.get("story_id"),
        "run_id": compact.get("run_id"),
        "symbol": compact.get("symbol"),
        "action": compact.get("action"),
        "status": compact.get("status"),
        "story_type": compact.get("story_type"),
        "execution_mode_label": compact.get("execution_mode_label"),
        "strategist_output": as_dict(compact.get("strategist_output")),
        "strategist_refresh_trace": as_dict(compact.get("strategist_refresh_trace")),
        "lifecycle_summary": {
            "holding_duration": lifecycle.get("holding_duration"),
            "entry_reason_human": lifecycle.get("entry_reason_human"),
            "exit_reason_human": lifecycle.get("exit_reason_human"),
            "lifecycle_summary_human": lifecycle.get("lifecycle_summary_human"),
        },
        "market_context": {
            "regime": market.get("regime"),
            "market_sentiment": market.get("market_sentiment"),
            "playbook": market.get("playbook"),
            "themes": listify(market.get("themes"), max_items=3, max_len=60),
            "theme_strength_packet": compact_scalar_dict(
                market.get("theme_strength_packet"),
                max_items=8,
                max_len=120,
            ),
            "theme_source": market.get("theme_source"),
            "theme_source_status": market.get("theme_source_status"),
            "theme_source_reason": market.get("theme_source_reason"),
            "theme_strength_top_themes": listify(market.get("theme_strength_top_themes"), max_items=6, max_len=60),
            "risk_mode": market.get("risk_mode"),
            "selected_playbook": market.get("selected_playbook"),
            "preferred_themes": listify(market.get("preferred_themes"), max_items=4, max_len=60),
            "avoid_themes": listify(market.get("avoid_themes"), max_items=4, max_len=60),
            "scanner_bias_summary": {
                "enabled": (market.get("scanner_bias_summary") or {}).get("enabled"),
                "active_biases": listify((market.get("scanner_bias_summary") or {}).get("active_biases"), max_items=6, max_len=80),
                "bias_strength": report_clip((market.get("scanner_bias_summary") or {}).get("bias_strength"), max_len=24),
                "bias_source": report_clip((market.get("scanner_bias_summary") or {}).get("bias_source"), max_len=80),
                "summary": report_clip((market.get("scanner_bias_summary") or {}).get("summary"), max_len=220),
            },
            "global_sentiment_score": market.get("global_sentiment_score"),
            "vix_level": market.get("vix_level"),
            "stress_flags": listify(market.get("stress_flags"), max_items=3, max_len=60),
            "candidate_hints": listify(market.get("candidate_hints"), max_items=6, max_len=24),
            "market_headlines": listify(market.get("market_headlines"), max_items=3, max_len=160),
            "symbol_headlines": listify(market.get("symbol_headlines"), max_items=3, max_len=160),
            "global_sentiment_signal": compact_scalar_dict(
                market.get("global_sentiment_signal"), max_items=8, max_len=120
            ),
            "fear_index": compact_scalar_dict(market.get("fear_index"), max_items=8, max_len=120),
            "key_events": listify(market.get("key_events_hint"), max_items=4, max_len=160),
            "news_input_summary": market.get("news_input_summary"),
        },
        "commander": {
            "command_intent": commander.get("command_intent"),
            "strategist_invocation": commander.get("strategist_invocation"),
            "llm_policy": commander.get("llm_policy"),
            "selected_route": commander.get("selected_route"),
            "route_reason_text": commander.get("route_reason_text"),
            "strategist_cache_used": commander.get("strategist_cache_used"),
            "strategist_called": commander.get("strategist_called"),
            "cooldown_applied": commander.get("cooldown_applied"),
            "applied_policy": compact_scalar_dict(commander.get("applied_policy"), max_items=12, max_len=120),
            "policy_source": commander.get("policy_source"),
            "policy_validation_status": commander.get("policy_validation_status"),
            "policy_fallback_used": commander.get("policy_fallback_used"),
            "policy_fallback_reason": commander.get("policy_fallback_reason"),
            "policy_partial_normalized": commander.get("policy_partial_normalized"),
            "policy_default_filled_fields": listify(commander.get("policy_default_filled_fields"), max_items=12, max_len=80),
            "policy_validation_missing_fields": listify(commander.get("policy_validation_missing_fields"), max_items=12, max_len=80),
            "policy_validation_invalid_fields": listify(commander.get("policy_validation_invalid_fields"), max_items=12, max_len=80),
            "override_reason": commander.get("override_reason"),
            "applied_policy_source_chain": listify(
                commander.get("applied_policy_source_chain"), max_items=6, max_len=80
            ),
            "entry_control": as_dict(commander.get("entry_control"))
            or as_dict(entry_visibility.get("commander_entry_control")),
        },
        "entry": {
            "ts": entry.get("ts"),
            "action": entry.get("action"),
            "reason_human": entry.get("reason_human"),
        },
        "scanner": {
            "selected_symbol": scanner.get("selected_symbol"),
            "selected_rank": scanner.get("selected_rank"),
            "universe_size": scanner.get("universe_size"),
            "ranking_basis": scanner.get("ranking_basis"),
            "playbook": scanner.get("playbook"),
            "policy_source": scanner.get("policy_source"),
            "applied_policy_present": scanner.get("applied_policy_present"),
            "monitor_entry_policy_summary": compact_scalar_dict(
                scanner.get("monitor_entry_policy_summary"), max_items=8, max_len=120
            ),
            "confidence": scanner.get("confidence"),
            "confidence_label": scanner.get("confidence_label"),
            "top_reasons": listify(scanner.get("top_reasons"), max_items=3, max_len=140),
            "why_selected": listify(scanner.get("why_selected"), max_items=4, max_len=140),
            "selection_basis": scanner.get("selection_basis"),
            "selection_reason_with_bias": scanner.get("selection_reason_with_bias"),
            "tie_break_rule": scanner.get("tie_break_rule"),
            "runner_ups": listify(scanner.get("runner_ups"), max_items=2, max_len=140),
            "runner_ups_lost": [
                {
                    "symbol": report_clip((row or {}).get("symbol"), max_len=24),
                    "summary": report_clip((row or {}).get("summary"), max_len=180),
                }
                for row in list(scanner.get("runner_ups_lost") or [])[:3]
                if isinstance(row, dict)
            ],
            "scanner_bias_applied": scanner.get("scanner_bias_applied"),
            "scanner_bias_summary": compact_scalar_dict(scanner.get("scanner_bias_summary"), max_items=8, max_len=120),
            "candidate_bias_adjustments": [
                {
                    "symbol": report_clip((row or {}).get("symbol"), max_len=24),
                    "bias_adjustment": (row or {}).get("bias_adjustment"),
                    "bias_adjustments": listify(
                        [
                            (
                                str((item or {}).get("reason") or "")
                                if isinstance(item, dict)
                                else str(item or "")
                            )
                            for item in list((row or {}).get("bias_adjustments") or [])
                            if str((item or {}).get("reason") if isinstance(item, dict) else item or "").strip()
                        ],
                        max_items=4,
                        max_len=120,
                    ),
                }
                for row in list(scanner.get("candidate_bias_adjustments") or [])[:5]
                if isinstance(row, dict)
            ],
            "selection_trace": {
                "ranked_candidates": compact_named_rows(
                    (scanner.get("selection_trace") or {}).get("ranked_candidates"),
                    max_items=5,
                ),
                "selected_symbol": report_clip((scanner.get("selection_trace") or {}).get("selected_symbol"), max_len=24),
                "selected_rank": (scanner.get("selection_trace") or {}).get("selected_rank"),
                "selection_reason": report_clip((scanner.get("selection_trace") or {}).get("selection_reason"), max_len=280),
                "selected_symbol_score_drivers": compact_scalar_dict(
                    (scanner.get("selection_trace") or {}).get("selected_symbol_score_drivers"),
                    max_items=6,
                    max_len=120,
                ),
            },
            "summary": scanner.get("summary"),
        },
        "filters": {
            "summary": filters_human.get("summary"),
            "bullets": listify(filters_human.get("bullets"), max_items=4, max_len=180),
        },
        "holding": {
            "run_count": holding.get("run_count"),
            "holding_event_count": holding.get("holding_event_count"),
            "recent_monitor_updates": listify(holding.get("recent_monitor_updates"), max_items=4, max_len=140),
        },
        "monitor": {
            "posture": monitor.get("posture"),
            "trigger_type": monitor.get("trigger_type"),
            "summary": monitor.get("summary"),
            "entry_check_summary": monitor.get("entry_check_summary"),
            "entry_blockers": listify(monitor.get("entry_blockers"), max_items=6, max_len=120),
            "threshold_shortfalls": listify(monitor.get("threshold_shortfalls"), max_items=4, max_len=160),
            "policy_ref": compact_scalar_dict(monitor.get("policy_ref"), max_items=8, max_len=120),
            "timing_assessment": compact_scalar_dict(monitor.get("timing_assessment"), max_items=8, max_len=120),
            "thresholds_guards_used": compact_scalar_dict(monitor.get("thresholds_guards_used"), max_items=8, max_len=120),
            "entry_metrics": compact_scalar_dict(monitor.get("entry_metrics"), max_items=10, max_len=120),
            "entry_thresholds": compact_scalar_dict(monitor.get("entry_thresholds"), max_items=8, max_len=120),
            "received_policy": compact_scalar_dict(monitor.get("received_policy"), max_items=12, max_len=120),
            "received_policy_source": monitor.get("received_policy_source"),
            "effective_policy": compact_scalar_dict(monitor.get("effective_policy"), max_items=12, max_len=120),
            "effective_policy_source": monitor.get("effective_policy_source"),
            "effective_policy_source_chain": listify(
                monitor.get("effective_policy_source_chain"), max_items=6, max_len=80
            ),
            "policy_adjustments": compact_scalar_dict(monitor.get("policy_adjustments"), max_items=8, max_len=120),
            "policy_adjustment_summary": monitor.get("policy_adjustment_summary"),
            "policy_adjustment_reasoning": monitor.get("policy_adjustment_reasoning"),
            "effective_policy_deltas": [
                (
                    report_clip(
                        f"{(row or {}).get('field')}: {(row or {}).get('from')} -> {(row or {}).get('to')}",
                        max_len=120,
                    )
                    if isinstance(row, dict)
                    else report_clip(row, max_len=120)
                )
                for row in list(monitor.get("effective_policy_deltas") or [])[:8]
                if (
                    isinstance(row, dict)
                    or str(row or "").strip()
                )
            ],
            "applied_policy": compact_scalar_dict(monitor.get("applied_policy"), max_items=12, max_len=120),
            "policy_source": monitor.get("policy_source"),
            "policy_validation_status": monitor.get("policy_validation_status"),
            "policy_fallback_used": monitor.get("policy_fallback_used"),
            "policy_fallback_reason": monitor.get("policy_fallback_reason"),
            "policy_partial_normalized": monitor.get("policy_partial_normalized"),
            "policy_default_filled_fields": listify(monitor.get("policy_default_filled_fields"), max_items=12, max_len=80),
            "policy_validation_missing_fields": listify(monitor.get("policy_validation_missing_fields"), max_items=12, max_len=80),
            "policy_validation_invalid_fields": listify(monitor.get("policy_validation_invalid_fields"), max_items=12, max_len=80),
            "override_reason": monitor.get("override_reason"),
            "applied_policy_source_chain": listify(
                monitor.get("applied_policy_source_chain"), max_items=6, max_len=80
            ),
            "position_age_seconds": monitor.get("position_age_seconds"),
            "hard_stop_pct": monitor.get("hard_stop_pct"),
            "adaptive_stop_loss_pct": monitor.get("adaptive_stop_loss_pct"),
            "stop_loss_pct": monitor.get("stop_loss_pct"),
            "effective_stop_loss_pct": monitor.get("effective_stop_loss_pct"),
            "trailing_stop_pct": monitor.get("trailing_stop_pct"),
            "take_profit_pct": monitor.get("take_profit_pct"),
            "monitor_stop_policy_trace": compact_scalar_dict(
                monitor.get("monitor_stop_policy_trace"), max_items=8, max_len=120
            ),
            "current_price": monitor.get("current_price"),
            "average_price": monitor.get("average_price"),
            "peak_price": monitor.get("peak_price"),
            "current_drawdown": monitor.get("current_drawdown"),
            "peak_drawdown": monitor.get("peak_drawdown"),
            "active_exit_axis": monitor.get("active_exit_axis"),
            "watch_axes": listify(monitor.get("watch_axes"), max_items=4, max_len=80),
            "price_source": monitor.get("price_source"),
            "entry_candidate_cascade": as_dict(monitor.get("entry_candidate_cascade"))
            or as_dict(entry_visibility.get("monitor_entry_candidate_cascade")),
        },
        "exit": {
            "ts": exit_summary.get("ts"),
            "action": exit_summary.get("action"),
            "reason_human": exit_summary.get("reason_human"),
        },
        "guard": {
            "summary": guard.get("summary") or guard_seed.get("summary"),
            "status": guard.get("status") or guard_seed.get("status"),
            "bullets": listify(guard.get("bullets"), max_items=4, max_len=180) or listify(guard_seed.get("bullets"), max_items=4, max_len=180),
        },
        "execution": {
            "summary": execution.get("summary") or execution_seed.get("summary"),
            "status": execution.get("status") or execution_seed.get("status"),
            "bullets": listify(execution.get("bullets"), max_items=4, max_len=180) or listify(execution_seed.get("bullets"), max_items=4, max_len=180),
        },
        "reporter": {
            "summary": reporter.get("summary") or reporter_seed.get("summary"),
            "status": reporter.get("status") or reporter_seed.get("status"),
            "grade": reporter.get("grade") or reporter_seed.get("grade"),
            "bullets": listify(reporter.get("bullets"), max_items=3, max_len=160) or listify(reporter_seed.get("bullets"), max_items=3, max_len=160),
        },
        "operator_conclusion": {
            "summary": conclusion.get("summary") or conclusion_seed.get("summary"),
            "current_action": conclusion.get("current_action") or conclusion_seed.get("current_action"),
            "watch_next": listify(conclusion.get("watch_next"), max_items=3, max_len=140) or listify(conclusion_seed.get("watch_next"), max_items=3, max_len=140),
            "thesis_invalidation": listify(conclusion.get("thesis_invalidation"), max_items=3, max_len=140) or listify(conclusion_seed.get("thesis_invalidation"), max_items=3, max_len=140),
        },
        "report_section_seeds": {
            "market_context_at_entry": compact_section_seed_for_llm(report_section_seeds.get("market_context_at_entry")),
            "strategist_summary": compact_section_seed_for_llm(report_section_seeds.get("strategist_summary")),
            "why_this_symbol_was_chosen": compact_section_seed_for_llm(report_section_seeds.get("why_this_symbol_was_chosen")),
            "entry_decision": compact_section_seed_for_llm(report_section_seeds.get("entry_decision")),
            "holding_monitoring_story": compact_section_seed_for_llm(report_section_seeds.get("holding_monitoring_story")),
            "exit_decision": compact_section_seed_for_llm(report_section_seeds.get("exit_decision")),
            "scanner_filters": compact_section_seed_for_llm(report_section_seeds.get("scanner_filters")),
            "execution_quality": compact_section_seed_for_llm(execution_seed),
            "guard_approval_result": compact_section_seed_for_llm(guard_seed),
            "reporter_evaluation": compact_section_seed_for_llm(reporter_seed),
            "final_operator_conclusion": compact_section_seed_for_llm(conclusion_seed),
        },
        "timeline": compact_timeline_rows(story_input.get("timeline"), head=1, tail=5),
        "improvement_points": listify(compact.get("improvement_points"), max_items=4, max_len=140),
        "strategist_evidence": as_dict(compact.get("strategist_evidence")),
        "entry_execution_visibility": entry_visibility,
        "ai_report_diagnostics": {
            "report_status": diagnostics.get("report_status"),
            "report_reason_code": diagnostics.get("report_reason_code"),
            "report_reason_human": diagnostics.get("report_reason_human"),
        },
    }
