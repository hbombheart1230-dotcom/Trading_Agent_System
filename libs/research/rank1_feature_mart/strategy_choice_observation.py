from __future__ import annotations

from typing import Any, Mapping

from libs.runtime.quant.contracts import TACTIC_IDS
from libs.runtime.quant.tactics import (
    default_tactic_for_playbook,
    tactic_candidates_for_playbook,
)


MOMENTUM_TACTICS = {
    "trend_continuation",
    "opening_gap_momentum",
    "opening_range_breakout",
    "volume_breakout",
    "event_theme_momentum",
}
PULLBACK_TACTICS = {
    "vwap_reclaim_pullback",
    "lower_vwap_rebound_probe",
}
REVERSAL_TACTICS = {"mean_reversion_probe", "reversal_reclaim"}
DEFENSIVE_TACTICS = {
    "cost_aware_scalp",
    "defensive_observe",
    "inverse_hedge_reclaim",
}

SETUP_TACTIC_CANDIDATES = {
    "FRESH_CHANGE_ACTIVATION": (
        "opening_gap_momentum",
        "opening_range_breakout",
        "volume_breakout",
        "event_theme_momentum",
        "trend_continuation",
    ),
    "DIRECTIONAL_BREADTH": (
        "trend_continuation",
        "volume_breakout",
        "vwap_reclaim_pullback",
    ),
    "LIQUIDITY_ONLY": (),
    "UNCLASSIFIED": (),
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tactic_family(tactic: str) -> str:
    if tactic in MOMENTUM_TACTICS:
        return "MOMENTUM_ACTIVATION"
    if tactic in PULLBACK_TACTICS:
        return "PULLBACK_RECLAIM"
    if tactic in REVERSAL_TACTICS:
        return "REVERSAL_RECLAIM"
    if tactic in DEFENSIVE_TACTICS:
        return "DEFENSIVE_COST_CONTROL"
    return "UNKNOWN"


def _setup_family(setup: str) -> str:
    if setup == "FRESH_CHANGE_ACTIVATION":
        return "MOMENTUM_ACTIVATION"
    if setup == "DIRECTIONAL_BREADTH":
        return "TREND_DIRECTIONAL"
    if setup == "LIQUIDITY_ONLY":
        return "LIQUIDITY_WITHOUT_DIRECTION"
    return "UNKNOWN"


def _alignment(setup: str, tactic: str) -> tuple[str, str]:
    setup_family = _setup_family(setup)
    tactic_family = _tactic_family(tactic)
    if setup_family in {"UNKNOWN", "LIQUIDITY_WITHOUT_DIRECTION"}:
        return (
            "INSUFFICIENT_EVIDENCE",
            "candidate setup does not contain enough directional structure",
        )
    if setup_family == tactic_family:
        return "MATCH", "candidate setup and selected tactic share the same family"
    if setup_family == "TREND_DIRECTIONAL" and tactic_family in {
        "MOMENTUM_ACTIVATION",
        "PULLBACK_RECLAIM",
    }:
        return (
            "COMPATIBLE",
            "directional breadth can support the tactic but does not prove its trigger",
        )
    return "MISMATCH", "candidate setup family differs from the selected market tactic"


def build_strategy_choice_observation(
    *,
    canonical_strategist: Mapping[str, Any],
    strategy: Mapping[str, Any],
    scanner: Mapping[str, Any],
) -> dict[str, Any]:
    canonical = _mapping(canonical_strategist)
    final_playbook = _text(
        canonical.get("final_playbook")
        or strategy.get("market_playbook")
        or strategy.get("playbook")
    ).lower()
    selected_tactic = _text(
        canonical.get("tactical_strategy") or strategy.get("tactical_strategy")
    ).lower()
    setup = _text(scanner.get("candidate_setup") or "UNCLASSIFIED").upper()
    alignment, alignment_reason = _alignment(setup, selected_tactic)
    scores = dict(canonical.get("strategy_scores") or strategy.get("strategy_scores") or {})
    rejected = dict(canonical.get("rejected_strategy_reasons") or {})
    llm_trace = _mapping(canonical.get("llm_trace"))
    call_trace = _mapping(llm_trace.get("llm_call_trace"))
    requested_source = _text(canonical.get("requested_playbook_source") or "unknown").lower()
    invocation_hint = _text(canonical.get("commander_invocation_hint") or "UNKNOWN")
    if not canonical:
        generation_mode = "MISSING_CANONICAL_EVIDENCE"
    elif invocation_hint == "RUN_REFRESH" and requested_source == "deterministic":
        generation_mode = "TACTICAL_REFRESH_INHERITED_MARKET_FRAME"
    elif invocation_hint == "SKIP":
        generation_mode = "CACHED_OR_SKIPPED_FRAME"
    elif requested_source == "llm":
        generation_mode = "LLM_MARKET_FRAME"
    else:
        generation_mode = "DETERMINISTIC_MARKET_FRAME"
    option_surface = []
    for tactic in TACTIC_IDS:
        score = scores.get(tactic)
        option_surface.append(
            {
                "tactic_id": tactic,
                "playbook_eligible": tactic in tactic_candidates_for_playbook(final_playbook),
                "score_status": "SCORED" if score is not None else "NOT_SCORED_BY_CURRENT_MODEL",
                "score": score,
                "selected": tactic == selected_tactic,
                "rejected_reason": _text(rejected.get(tactic)),
            }
        )
    default_tactic = default_tactic_for_playbook(final_playbook)
    return {
        "schema_version": "rank1_strategy_choice_observation.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "evidence_status": "OBSERVED" if canonical else "MISSING_CANONICAL_EVIDENCE",
        "playbook_choice": {
            "pre_llm_playbook": _text(canonical.get("pre_llm_playbook")).lower(),
            "llm_requested_playbook": _text(
                canonical.get("llm_requested_playbook")
            ).lower(),
            "requested_playbook": _text(canonical.get("requested_playbook")).lower(),
            "requested_playbook_source": requested_source,
            "final_playbook": final_playbook,
            "changed_from_pre_llm": bool(
                canonical
                and _text(canonical.get("pre_llm_playbook"))
                and _text(canonical.get("pre_llm_playbook")).lower()
                != final_playbook
            ),
        },
        "generation": {
            "mode": generation_mode,
            "commander_invocation_hint": invocation_hint,
            "llm_status": _text(llm_trace.get("llm_status") or call_trace.get("final_status")),
            "model": _text(llm_trace.get("model") or call_trace.get("final_model")),
            "primary_attempted": call_trace.get("primary_attempted"),
            "llm_fallback_used": call_trace.get("fallback_used"),
            "strategist_fallback_used": canonical.get("strategist_fallback_used"),
            "temperature": _mapping(
                call_trace.get("llm_execution_effective_config")
            ).get("temperature"),
        },
        "tactic_choice": {
            "selected_tactic": selected_tactic,
            "selected_subtype": _text(
                canonical.get("tactical_subtype")
                or strategy.get("tactical_subtype")
            ).lower(),
            "default_tactic_for_playbook": default_tactic,
            "selected_is_playbook_default": selected_tactic == default_tactic,
            "playbook_candidate_tactics": tactic_candidates_for_playbook(final_playbook),
            "scored_tactic_count": sum(item["score_status"] == "SCORED" for item in option_surface),
            "catalog_tactic_count": len(option_surface),
            "selection_source_status": "NOT_EXPLICITLY_PERSISTED",
            "option_surface": option_surface,
        },
        "candidate_setup_observation": {
            "candidate_setup": setup,
            "candidate_setup_family": _setup_family(setup),
            "selected_tactic_family": _tactic_family(selected_tactic),
            "setup_playbook_alignment": alignment,
            "alignment_reason": alignment_reason,
            "candidate_tactical_recommendation": list(
                SETUP_TACTIC_CANDIDATES.get(setup, ())
            ),
            "recommendation_effect": "NONE_OBSERVATION_ONLY",
        },
    }
