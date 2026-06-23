from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.quant.factors import build_factor_snapshot_from_candidate


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def build_candidate_ranking_table_payload(ranking_table: List[Dict[str, Any]]) -> Dict[str, Any]:
    reconstructed_pre_adjust = sorted(
        [dict(row) for row in ranking_table if isinstance(row, dict)],
        key=lambda row: (
            -_to_float(row.get("pre_adjust_score_total")),
            -_to_float(row.get("confidence")),
            _to_float(row.get("risk_score")),
        ),
    )
    for index, row in enumerate(reconstructed_pre_adjust, start=1):
        row["rank"] = index
    intrinsic_control = sorted(
        [dict(row) for row in ranking_table if isinstance(row, dict)],
        key=lambda row: (
            -_to_float(row.get("scanner_intrinsic_control_score_total")),
            -_to_float(row.get("confidence")),
            _to_float(row.get("risk_score")),
        ),
    )
    for index, row in enumerate(intrinsic_control, start=1):
        row["rank"] = index
    return {
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
        "rows": ranking_table,
        "post_strategist_top10": list(ranking_table[:10]),
        "reconstructed_pre_adjust_top10": reconstructed_pre_adjust[:10],
        "reconstructed_pre_adjust_evidence_class": "RECONSTRUCTED",
        "reconstructed_pre_adjust_limitation": (
            "same candidate universe with score overlays removed; candidate sourcing may already "
            "contain Strategist influence and is not a raw Scanner control"
        ),
        "scanner_intrinsic_control_top10": intrinsic_control[:10],
        "scanner_intrinsic_control_source": "same_candidate_universe_ranking_only",
        "scanner_intrinsic_control_evidence_class": "TRUSTED_SHADOW",
        "scanner_intrinsic_control_limitation": (
            "candidate sourcing may already reflect Strategist guidance; ranking weights are isolated"
        ),
    }


def build_candidate_selection_reason_payload(
    *,
    selected: Dict[str, Any] | None,
    selected_symbol: str,
    selected_rank: int,
    selected_score_total: float,
    margin_vs_second: float,
    critical_positive_factors: List[str],
    critical_negative_factors: List[str],
    selection_summary: str,
    scanner_policy_trace: Dict[str, Any],
    playbook: str,
    compatibility_bias_context: Dict[str, Any],
    market_representative_guard_meta: Dict[str, Any],
    blocker_family_overlay_meta: Dict[str, Any],
    selection_veto_enforced: bool,
    scanner_bias_applied: bool,
    scanner_memory_bias_applied: bool,
    scanner_memory_bias: Dict[str, Any],
    commander_memory_application_trace: Dict[str, Any],
    candidate_bias_adjustments: List[Dict[str, Any]],
    candidate_memory_bias_adjustments: List[Dict[str, Any]],
    candidate_symbol_prior_adjustments: List[Dict[str, Any]],
    selection_reason_with_bias: str,
    runner_up_reasons: List[Dict[str, Any]],
) -> Dict[str, Any]:
    row = selected if isinstance(selected, dict) else {}
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    selected_present = bool(row)
    return {
        "selected_symbol": selected_symbol,
        "selected_rank": int(selected_rank),
        "selected_score_total": float(selected_score_total),
        "margin_vs_second": float(margin_vs_second),
        "critical_positive_factors": list(critical_positive_factors),
        "critical_negative_factors": list(critical_negative_factors),
        "selection_summary": selection_summary,
        "commander_context_consumed": bool(scanner_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(scanner_policy_trace.get("consumed_fields") or []),
        "commander_priority_ref": dict(scanner_policy_trace.get("commander_priority_ref") or {}),
        "strategist_constraints_ref": dict(scanner_policy_trace.get("strategist_constraints_ref") or {}),
        "selection_basis": dict(scanner_policy_trace.get("selection_basis") or {}),
        "ranking_factors": list(scanner_policy_trace.get("ranking_factors") or []),
        "playbook": str(scanner_policy_trace.get("playbook") or playbook or ""),
        "policy_source": str(scanner_policy_trace.get("policy_source") or ""),
        "applied_policy_present": bool(scanner_policy_trace.get("applied_policy_present")),
        "monitor_entry_policy_summary": dict(scanner_policy_trace.get("monitor_entry_policy_summary") or {}),
        "scanner_bias_context": dict(scanner_policy_trace.get("scanner_bias_context") or {}),
        "entry_compatibility_score": float(_to_float(row.get("entry_compatibility_score"))) if selected_present else 0.0,
        "compatibility_bias": float(_to_float(row.get("compatibility_bias"))) if selected_present else 0.0,
        "compatibility_components": dict(row.get("compatibility_components") or {}) if selected_present else {},
        "scanner_chart_fit_score": float(_to_float(row.get("scanner_chart_fit_score"))) if selected_present else 0.0,
        "scanner_chart_fit_authority": str(row.get("scanner_chart_fit_authority") or "") if selected_present else "",
        "scanner_chart_fit_components": dict(row.get("scanner_chart_fit_components") or {}) if selected_present else {},
        "scanner_macro_chart_fit_score": float(_to_float(row.get("scanner_macro_chart_fit_score"), 0.5)) if selected_present else 0.5,
        "scanner_macro_chart_fit_bias": float(_to_float(row.get("scanner_macro_chart_fit_bias"))) if selected_present else 0.0,
        "scanner_macro_chart_fit_authority": str(row.get("scanner_macro_chart_fit_authority") or "") if selected_present else "",
        "scanner_macro_chart_fit_components": dict(row.get("scanner_macro_chart_fit_components") or {}) if selected_present else {},
        "quant_factor_snapshot": build_factor_snapshot_from_candidate(
            row,
            tactic_id=str(row.get("tactical_strategy") or ""),
            playbook=str(scanner_policy_trace.get("playbook") or playbook or ""),
        )
        if selected_present
        else {},
        "tactic_suitability": dict(row.get("tactic_suitability") or {}) if selected_present else {},
        "expected_monitor_block_reason": str(row.get("expected_monitor_block_reason") or "") if selected_present else "",
        "dominant_block_reason": str(row.get("dominant_block_reason") or compatibility_bias_context.get("dominant_block_reason") or "") if selected_present else str(compatibility_bias_context.get("dominant_block_reason") or ""),
        "dominant_block_reason_ratio": float(_to_float(row.get("dominant_block_reason_ratio") or compatibility_bias_context.get("dominant_block_reason_ratio"))),
        "market_representative_guard_enabled": bool(market_representative_guard_meta.get("enabled")),
        "market_representative_guard_applied": bool(market_representative_guard_meta.get("applied")),
        "market_representative_guard_symbol": str(market_representative_guard_meta.get("symbol") or ""),
        "market_representative_guard_penalty": float(_to_float(market_representative_guard_meta.get("penalty"))),
        "market_representative_guard_reason": str(
            market_representative_guard_meta.get("reason")
            or market_representative_guard_meta.get("skipped_reason")
            or ""
        ),
        "market_representative_guard_confirmation_sources": list(market_representative_guard_meta.get("confirmation_sources") or []),
        "blocker_family_concentration_applied": bool(blocker_family_overlay_meta.get("applied")),
        "blocker_family_concentration_family": str(blocker_family_overlay_meta.get("family") or ""),
        "blocker_family_concentration_penalty": float(_to_float(blocker_family_overlay_meta.get("penalty"))),
        "blocker_family_concentration_top3_before": list(blocker_family_overlay_meta.get("top3_symbols_before") or []),
        "blocker_family_concentration_top3_after": list(blocker_family_overlay_meta.get("top3_symbols_after") or []),
        "blocker_family_concentration_alternative_symbols": list(blocker_family_overlay_meta.get("alternative_symbols") or []),
        "selection_vetoed": bool(blocker_family_overlay_meta.get("selection_vetoed")),
        "selection_veto_enforced": bool(selection_veto_enforced),
        "selection_veto_reason": str(blocker_family_overlay_meta.get("selection_veto_reason") or ""),
        "bias_scale": float(_to_float(row.get("bias_scale") or compatibility_bias_context.get("bias_scale"))),
        "soft_penalty": float(_to_float(row.get("soft_penalty"))) if selected_present else 0.0,
        "compatibility_score_pre_penalty": float(_to_float(row.get("compatibility_score_pre_penalty"))) if selected_present else 0.0,
        "compatibility_score_post_penalty": float(_to_float(row.get("compatibility_score_post_penalty"))) if selected_present else 0.0,
        "compatibility_trace": dict(row.get("compatibility_trace") or {}) if selected_present else {},
        "pre_adjust_score_total": float(_to_float(row.get("pre_adjust_score_total"))) if selected_present else 0.0,
        "post_adjust_score_total": float(_to_float(row.get("post_adjust_score_total") or row.get("score_total") or row.get("score"))) if selected_present else 0.0,
        "scanner_bias_applied": bool(scanner_bias_applied),
        "scanner_bias_summary": dict(scanner_policy_trace.get("scanner_bias_summary") or {}),
        "scanner_memory_bias_applied": bool(scanner_memory_bias_applied),
        "scanner_memory_bias": dict(scanner_memory_bias),
        "scanner_memory_bias_summary": dict(scanner_policy_trace.get("scanner_memory_bias_summary") or {}),
        "commander_memory_application_trace": dict(commander_memory_application_trace),
        "scanner_memory_application_trace": dict(commander_memory_application_trace),
        "candidate_bias_adjustments": list(candidate_bias_adjustments),
        "candidate_memory_bias_adjustments": list(candidate_memory_bias_adjustments),
        "candidate_symbol_prior_adjustments": list(candidate_symbol_prior_adjustments),
        "selection_reason_with_bias": selection_reason_with_bias,
        "shadow_used": bool(scanner_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(scanner_policy_trace.get("strategist_fallback_used")),
        "why_selected": [
            f"highest total score ({float(_to_float(row.get('score_total') or row.get('score'))):.3f})"
            if selected_present
            else "no candidate selected",
            f"confidence {float(_to_float(row.get('confidence'))):.2f} and risk {float(_to_float(row.get('risk_score'))):.2f}"
            if selected_present
            else "",
            f"source mix: {', '.join(list(candidate.get('sources') or [])[:4])}"
            if selected_present
            else "",
            f"playbook alignment: {playbook or 'not_captured'}",
            f"tactic suitability: {str((row.get('tactic_suitability') or {}).get('tier') or 'unavailable')} "
            f"({float(_to_float((row.get('tactic_suitability') or {}).get('score'))):.2f})"
            if selected_present
            else "",
        ],
        "runner_ups_lost": runner_up_reasons,
        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
        "final_decision_basis": (
            "Scanner selected the highest-ranked candidate after strategist-guided weighting, "
            "source scoring, risk penalties, and capped scanner/memory bias adjustments."
            if scanner_bias_applied or scanner_memory_bias_applied
            else "Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties."
        ),
        "policy_provenance_ref": dict(scanner_policy_trace.get("policy_provenance_ref") or {}),
    }
