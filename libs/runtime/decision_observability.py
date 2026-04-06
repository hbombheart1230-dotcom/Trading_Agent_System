from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from libs.core.symbols import normalize_symbol


_DECISION_OUTCOMES = {"BUY", "SELL", "WAIT", "NOOP"}


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _clip(value: Any, *, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _dedupe_non_empty(values: Iterable[Any], *, limit: int | None = None) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit is not None and len(out) >= int(limit):
            break
    return out


def _humanize_reason_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ")


def _extract_failed_names(rows: Any, *, statuses: Sequence[str]) -> List[str]:
    expected = {str(item or "").strip().lower() for item in list(statuses or []) if str(item or "").strip()}
    out: List[str] = []
    for row in list(rows or []):
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status not in expected:
            continue
        out.append(str(row.get("name") or "").strip())
    return _dedupe_non_empty(out, limit=8)


def _blocker_family(
    *,
    code: str,
    primary_failure_axis: str,
    guard_blocked: bool,
) -> str:
    reason = str(code or "").strip().lower()
    axis = str(primary_failure_axis or "").strip().lower()
    if guard_blocked:
        return "guard_intervention"
    if axis in {
        "vwap_relationship",
        "pullback_structure",
        "volume_confirmation",
        "breakout_readiness",
        "entry_confirmation",
        "overextension",
        "chart_structure_support",
        "chart_structure_continuation",
    }:
        return axis
    if "chart_structure" in reason:
        return "chart_structure_guard"
    if "volume" in reason:
        return "volume_confirmation"
    if "reclaim" in reason or "vwap" in reason:
        return "vwap_relationship"
    if "pullback" in reason:
        return "pullback_structure"
    if "breakout" in reason:
        return "breakout_readiness"
    if "extend" in reason:
        return "overextension"
    if "confirmation" in reason:
        return "entry_confirmation"
    return "unknown"


def _normalize_decision_outcome(value: Any, *, fallback: str = "WAIT") -> str:
    text = str(value or "").strip().upper()
    return text if text in _DECISION_OUTCOMES else fallback


def build_monitor_no_trade_surface(
    entry_info: Mapping[str, Any] | None,
    *,
    final_decision: Any,
    buy_submitted: bool,
    guard_blocked: bool = False,
    guard_reason: Any = None,
    commander_no_trade_reason_code: Any = None,
) -> Dict[str, Any]:
    row = dict(entry_info or {}) if isinstance(entry_info, Mapping) else {}
    summary = dict(row.get("policy_alignment_summary") or {}) if isinstance(row.get("policy_alignment_summary"), Mapping) else {}
    trace = dict(row.get("policy_interpreter_trace") or {}) if isinstance(row.get("policy_interpreter_trace"), Mapping) else {}
    check_status = dict(trace.get("check_status") or {}) if isinstance(trace.get("check_status"), Mapping) else {}
    condition_scores = dict(row.get("condition_scores") or {}) if isinstance(row.get("condition_scores"), Mapping) else {}
    policy_interpretation = dict(row.get("policy_interpretation") or {}) if isinstance(row.get("policy_interpretation"), Mapping) else {}
    policy_gating = dict(row.get("policy_aware_gating") or {}) if isinstance(row.get("policy_aware_gating"), Mapping) else {}
    chart_hint = dict(row.get("chart_structure_decision_hint") or {}) if isinstance(row.get("chart_structure_decision_hint"), Mapping) else {}

    decision_outcome = _normalize_decision_outcome(final_decision, fallback="BUY" if buy_submitted else "WAIT")
    evaluated = bool(row.get("evaluated"))
    pre_intent_decision = "BUY" if bool(row.get("triggered")) else ("NOOP" if not evaluated else "WAIT")
    no_trade_stage = "none"
    if decision_outcome not in {"BUY", "SELL"}:
        if guard_blocked:
            no_trade_stage = "guard_block"
        elif pre_intent_decision == "NOOP":
            no_trade_stage = "pre_intent_noop"
        else:
            no_trade_stage = "pre_intent_wait"

    no_trade_reason_code = (
        str(guard_reason or "").strip()
        if guard_blocked
        else str(row.get("reason") or commander_no_trade_reason_code or row.get("primary_failure_axis") or "").strip()
    )
    dominant_blocker = str(
        summary.get("primary_blocker")
        or no_trade_reason_code
        or row.get("primary_failure_axis")
        or commander_no_trade_reason_code
        or ""
    ).strip()
    confidence_score = _to_float(condition_scores.get("confidence_score"))
    confidence_threshold = _to_float(condition_scores.get("confidence_threshold"))
    confidence_gap = max(0.0, confidence_threshold - confidence_score) if confidence_threshold > 0.0 else 0.0
    reclaim_distance = row.get("reclaim_distance_to_ready")
    volume_distance = row.get("volume_distance_to_ready")
    breakout_distance = row.get("breakout_distance_to_ready")
    reclaim_gap = max(0.0, -_to_float(reclaim_distance)) if reclaim_distance not in (None, "") else None
    volume_gap = max(0.0, -_to_float(volume_distance)) if volume_distance not in (None, "") else None
    breakout_gap = max(0.0, -_to_float(breakout_distance)) if breakout_distance not in (None, "") else None
    transition_readiness_score = _to_float(row.get("transition_readiness_score"))

    blocker_metrics = {
        "reclaim_margin": reclaim_distance,
        "breakout_margin": breakout_distance,
        "volume_margin": volume_distance,
        "confidence_margin": round(confidence_score - confidence_threshold, 4) if confidence_threshold > 0.0 else None,
        "transition_readiness_score": transition_readiness_score if transition_readiness_score > 0.0 else None,
    }
    blocker_metrics = {k: v for k, v in blocker_metrics.items() if v not in (None, "")}

    distance_to_ready = {
        "reclaim_score_gap": round(reclaim_gap, 4) if reclaim_gap is not None else None,
        "breakout_gap": round(breakout_gap, 4) if breakout_gap is not None else None,
        "volume_gap": round(volume_gap, 4) if volume_gap is not None else None,
        "confidence_gap": round(confidence_gap, 4) if confidence_threshold > 0.0 else None,
    }
    distance_to_ready = {k: v for k, v in distance_to_ready.items() if v is not None}

    near_ready_flag = bool(
        decision_outcome not in {"BUY", "SELL"}
        and (
            transition_readiness_score >= 0.75
            or (reclaim_gap is not None and reclaim_gap <= 0.03)
            or (breakout_gap is not None and breakout_gap <= 0.01)
            or (volume_gap is not None and volume_gap <= 0.20)
            or (confidence_threshold > 0.0 and confidence_gap <= 0.05)
        )
    )

    required_checks_failed = _dedupe_non_empty(
        list(summary.get("top_failed_required_checks") or [])
        or _extract_failed_names(check_status.get("required"), statuses=("fail",)),
        limit=6,
    )
    preferred_checks_failed = _dedupe_non_empty(
        list(summary.get("top_failed_preferred_checks") or [])
        or _extract_failed_names(check_status.get("preferred"), statuses=("fail",)),
        limit=6,
    )
    relaxable_checks_failed = _dedupe_non_empty(
        list(summary.get("top_relaxable_gaps") or [])
        or _extract_failed_names(check_status.get("relaxable"), statuses=("fail",)),
        limit=6,
    )

    evidence_snapshot = {
        "entry_style": str(policy_interpretation.get("entry_style") or ""),
        "entry_condition_path": str(row.get("entry_condition_path") or ""),
        "paths_passed": _dedupe_non_empty(list(row.get("entry_condition_paths_passed") or []), limit=4),
        "policy_alignment_state": str(summary.get("alignment_state") or ""),
        "primary_failure_axis": str(row.get("primary_failure_axis") or ""),
        "transition_readiness_score": round(transition_readiness_score, 4) if transition_readiness_score > 0.0 else None,
        "policy_aware_gating_applied": bool(policy_gating.get("applied")),
        "chart_structure_hint_applied": bool(chart_hint.get("applied")),
        "confidence_score": round(confidence_score, 4) if confidence_score > 0.0 else None,
        "confidence_threshold": round(confidence_threshold, 4) if confidence_threshold > 0.0 else None,
    }
    evidence_snapshot = {k: v for k, v in evidence_snapshot.items() if v not in (None, "", [])}

    return {
        "schema_version": "monitor_no_trade_surface.v1",
        "decision_outcome": decision_outcome,
        "pre_intent_decision": pre_intent_decision,
        "no_trade_stage": no_trade_stage,
        "guard_intervened": bool(guard_blocked),
        "guard_reason": str(guard_reason or "").strip(),
        "no_trade_reason_code": no_trade_reason_code,
        "no_trade_reason_summary": _humanize_reason_code(no_trade_reason_code or dominant_blocker),
        "dominant_blocker": dominant_blocker,
        "blocker_family": _blocker_family(
            code=str(dominant_blocker or no_trade_reason_code),
            primary_failure_axis=str(row.get("primary_failure_axis") or ""),
            guard_blocked=bool(guard_blocked),
        ),
        "blocker_metrics": blocker_metrics,
        "distance_to_ready": distance_to_ready,
        "near_ready_flag": near_ready_flag,
        "required_checks_failed": required_checks_failed,
        "preferred_checks_failed": preferred_checks_failed,
        "relaxable_checks_failed": relaxable_checks_failed,
        "evidence_snapshot": evidence_snapshot,
    }


def build_scanner_monitor_handoff_surface(
    *,
    selected: Mapping[str, Any] | None,
    ranked_candidates: Sequence[Mapping[str, Any]] | None,
    scanner_output: Mapping[str, Any] | None,
    final_decision: Any,
    no_trade_surface: Mapping[str, Any] | None,
    entry_info: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    selected_row = dict(selected or {}) if isinstance(selected, Mapping) else {}
    scanner_row = dict(scanner_output or {}) if isinstance(scanner_output, Mapping) else {}
    no_trade = dict(no_trade_surface or {}) if isinstance(no_trade_surface, Mapping) else {}
    entry_row = dict(entry_info or {}) if isinstance(entry_info, Mapping) else {}
    selected_symbol = normalize_symbol(
        selected_row.get("symbol")
        or scanner_row.get("scanner_selected_symbol")
        or scanner_row.get("top_stock")
        or ""
    )
    selected_score_total = _to_float(
        selected_row.get("score_total")
        if selected_row.get("score_total") not in (None, "")
        else selected_row.get("score")
    )
    selected_score_breakdown = (
        dict(selected_row.get("score_breakdown") or {})
        if isinstance(selected_row.get("score_breakdown"), Mapping)
        else {}
    )
    top_candidates: List[Dict[str, Any]] = []
    selected_rank = 0
    for rank, row in enumerate(list(ranked_candidates or [])[:3], start=1):
        if not isinstance(row, Mapping):
            continue
        symbol = normalize_symbol(row.get("symbol") or "")
        score_total = _to_float(row.get("score_total") if row.get("score_total") not in (None, "") else row.get("score"))
        score_breakdown = dict(row.get("score_breakdown") or {}) if isinstance(row.get("score_breakdown"), Mapping) else {}
        top_candidates.append(
            {
                "rank": rank,
                "symbol": symbol,
                "score_total": score_total,
                "score_breakdown": score_breakdown,
            }
        )
        if symbol and symbol == selected_symbol:
            selected_rank = rank
    if selected_rank <= 0 and selected_symbol:
        selected_rank = _to_int(scanner_row.get("selected_rank")) or 1

    final_outcome = _normalize_decision_outcome(final_decision, fallback="WAIT")
    no_trade_reason_code = str(no_trade.get("no_trade_reason_code") or "").strip()
    expected_monitor_block_reason = _clip(
        scanner_row.get("expected_monitor_block_reason")
        or selected_row.get("expected_monitor_block_reason"),
        max_len=120,
    )
    dominant_block_reason = _clip(
        scanner_row.get("dominant_block_reason")
        or selected_row.get("dominant_block_reason"),
        max_len=120,
    )
    scanner_vs_monitor_alignment = "unknown"
    if final_outcome == "BUY":
        scanner_vs_monitor_alignment = "aligned"
    elif not selected_symbol:
        scanner_vs_monitor_alignment = "unknown"
    elif str(no_trade.get("no_trade_stage") or "") == "guard_block":
        scanner_vs_monitor_alignment = "guard_block"
    elif expected_monitor_block_reason and no_trade_reason_code and expected_monitor_block_reason == no_trade_reason_code:
        scanner_vs_monitor_alignment = "expected_mismatch"
    elif dominant_block_reason and no_trade_reason_code and (
        dominant_block_reason == no_trade_reason_code
        or dominant_block_reason in no_trade_reason_code
        or no_trade_reason_code in dominant_block_reason
    ):
        scanner_vs_monitor_alignment = "partial_mismatch"
    elif no_trade_reason_code:
        scanner_vs_monitor_alignment = "mismatch"

    handoff_trace = _dedupe_non_empty(
        [
            f"scanner_top_pick:{selected_symbol}" if selected_symbol else "",
            f"scanner_rank:{selected_rank}" if selected_rank > 0 else "",
            f"monitor_outcome:{final_outcome}",
            f"monitor_reason:{no_trade_reason_code}" if no_trade_reason_code else "",
            f"expected_monitor_block_reason:{expected_monitor_block_reason}" if expected_monitor_block_reason else "",
        ],
        limit=6,
    )
    return {
        "schema_version": "scanner_monitor_handoff.v1",
        "scanner_selected_symbol": selected_symbol,
        "scanner_rank": int(selected_rank),
        "scanner_score_total": selected_score_total,
        "scanner_score_breakdown": selected_score_breakdown,
        "scanner_top_candidates": top_candidates,
        "scanner_vs_monitor_alignment": scanner_vs_monitor_alignment,
        "monitor_rejection_after_top_pick": bool(selected_symbol and final_outcome not in {"BUY", "SELL"}),
        "monitor_rejection_reason_code": no_trade_reason_code,
        "monitor_rejection_reason_summary": str(no_trade.get("no_trade_reason_summary") or ""),
        "handoff_trace": handoff_trace,
        "entry_style": str(((entry_row.get("policy_interpretation") or {}).get("entry_style")) if isinstance(entry_row.get("policy_interpretation"), Mapping) else ""),
    }


def _extract_error_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    known = ("TimeoutError", "ValueError", "RuntimeError", "TypeError", "ConnectionError")
    for item in known:
        if item in text:
            return item
    if ":" in text:
        return text.split(":", 1)[0].strip()
    if "(" in text:
        return text.split("(", 1)[0].strip()
    return text[:40]


def build_strategist_policy_resolution_surface(
    *,
    strategist_output: Mapping[str, Any] | None,
    strategist_llm: Mapping[str, Any] | None,
    commander_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    output = dict(strategist_output or {}) if isinstance(strategist_output, Mapping) else {}
    llm = dict(strategist_llm or {}) if isinstance(strategist_llm, Mapping) else {}
    context = dict(commander_context or {}) if isinstance(commander_context, Mapping) else {}
    llm_status = str(llm.get("status") or llm.get("llm_status") or output.get("llm_frame_status") or "").strip().lower()
    llm_attempted = bool(
        llm_status not in {"", "disabled"}
        or _to_int(llm.get("attempts")) > 0
        or str(llm.get("prompt_ref") or "").strip()
        or str(llm.get("response_ref") or "").strip()
    )
    llm_blocked = bool(llm.get("blocked") or output.get("llm_frame_blocked"))
    llm_ok = bool(llm_attempted and not llm_blocked and llm_status in {"ok", "success", "applied"})
    llm_error_message_short = _clip(
        llm.get("blocked_reason")
        or llm.get("reason")
        or llm.get("error")
        or output.get("llm_frame_blocked_reason"),
        max_len=180,
    )
    fallback_used = bool(
        output.get("policy_fallback_used")
        or output.get("strategist_fallback_used")
        or llm_status in {"fallback", "error", "blocked"}
        or llm_blocked
    )
    reused_cached_strategy = bool(
        context.get("strategist_cache_preferred")
        or str(context.get("strategist_invocation") or "").strip().upper() == "SKIP"
    )
    if reused_cached_strategy:
        strategy_generation_mode = "cached"
    elif fallback_used:
        strategy_generation_mode = "fallback"
    elif llm_attempted and llm_ok:
        strategy_generation_mode = "live_llm"
    else:
        strategy_generation_mode = "default_safe"
    fallback_source = ""
    if reused_cached_strategy:
        fallback_source = "cached_strategy"
    elif fallback_used:
        fallback_source = _clip(
            output.get("policy_source")
            or output.get("policy_fallback_reason")
            or "default_safe_policy",
            max_len=120,
        )
    effective_schema_version = ""
    monitor_entry_policy = dict(output.get("monitor_entry_policy") or {}) if isinstance(output.get("monitor_entry_policy"), Mapping) else {}
    if str(monitor_entry_policy.get("schema_version") or "").strip():
        effective_schema_version = str(monitor_entry_policy.get("schema_version") or "").strip()
    prompt_ref = str(llm.get("prompt_ref") or "").strip()
    prompt_version = Path(prompt_ref).name if prompt_ref else ""
    policy_staleness = (
        context.get("strategist_refresh_context", {}).get("cache_age_sec")
        if isinstance(context.get("strategist_refresh_context"), Mapping)
        else None
    )
    policy_id = _clip(
        monitor_entry_policy.get("policy_id")
        or output.get("policy_source")
        or context.get("policy_source"),
        max_len=120,
    )
    return {
        "schema_version": "strategist_policy_resolution.v1",
        "llm_attempted": llm_attempted,
        "llm_ok": llm_ok,
        "llm_error_type": _extract_error_type(llm_error_message_short),
        "llm_error_message_short": llm_error_message_short,
        "latency_ms": _to_int(llm.get("latency_ms")),
        "fallback_used": fallback_used,
        "fallback_source": fallback_source,
        "fallback_policy_id": policy_id if fallback_used else "",
        "effective_policy_source": _clip(output.get("policy_source"), max_len=120),
        "effective_prompt_version": prompt_version,
        "effective_schema_version": effective_schema_version,
        "policy_staleness": policy_staleness,
        "reused_cached_strategy": reused_cached_strategy,
        "strategy_generation_mode": strategy_generation_mode,
    }


def build_commander_route_observability_surface(
    *,
    selected_route: str,
    route_reason: str,
    commander_decision: Mapping[str, Any] | None,
    runtime_fast_path: Mapping[str, Any] | None,
    resilience: Mapping[str, Any] | None,
    runtime_status: Any,
    runtime_transition: Any,
) -> Dict[str, Any]:
    decision = dict(commander_decision or {}) if isinstance(commander_decision, Mapping) else {}
    fast_path = dict(runtime_fast_path or {}) if isinstance(runtime_fast_path, Mapping) else {}
    resilience_row = dict(resilience or {}) if isinstance(resilience, Mapping) else {}
    strategist_invocation = str(decision.get("strategist_invocation") or "").strip().upper()
    cache_hit = bool(selected_route == "cached_strategist" or fast_path.get("cache_age_sec"))
    if strategist_invocation in {"RUN", "RUN_REFRESH"}:
        strategist_call_decision = "call"
    elif strategist_invocation == "SKIP" or cache_hit or selected_route == "monitor_only":
        strategist_call_decision = "skip"
    else:
        strategist_call_decision = "observe"
    if cache_hit:
        strategy_generation_mode = "cached"
    elif bool(decision.get("strategist_fallback_used") or decision.get("policy_fallback_used")):
        strategy_generation_mode = "fallback"
    elif strategist_call_decision == "call":
        strategy_generation_mode = "live_llm"
    else:
        strategy_generation_mode = "default_safe"
    applied_policy = dict(decision.get("applied_policy") or {}) if isinstance(decision.get("applied_policy"), Mapping) else {}
    applied_policy_id = _clip(
        applied_policy.get("policy_id")
        or applied_policy.get("id")
        or decision.get("policy_source"),
        max_len=120,
    )
    route_reason_text = _clip(route_reason or decision.get("decision_summary"), max_len=220)
    return {
        "schema_version": "commander_route_observability.v1",
        "route_selected": str(selected_route or ""),
        "route_reason": route_reason_text,
        "strategist_call_decision": strategist_call_decision,
        "strategist_call_reason": _clip(
            decision.get("strategist_refresh_reason") or route_reason_text if strategist_call_decision == "call" else "",
            max_len=180,
        ),
        "strategist_skip_reason": _clip(
            decision.get("strategist_cache_preference_reason")
            or fast_path.get("reason")
            or route_reason_text if strategist_call_decision == "skip" else "",
            max_len=180,
        ),
        "policy_refresh_reason": _clip(decision.get("strategist_refresh_reason"), max_len=180),
        "cache_hit": cache_hit,
        "cache_age_sec": fast_path.get("cache_age_sec"),
        "applied_policy_source": _clip(decision.get("policy_source"), max_len=120),
        "applied_policy_id": applied_policy_id,
        "monitor_only_reason": route_reason_text if str(selected_route or "") == "monitor_only" else "",
        "full_cycle_reason": route_reason_text if str(selected_route or "") == "full_cycle" else "",
        "resilience_state": {
            "runtime_status": str(runtime_status or ""),
            "runtime_transition": str(runtime_transition or ""),
            "incident_count": _to_int(resilience_row.get("incident_count")),
            "degrade_mode": bool(resilience_row.get("degrade_mode")),
            "cooldown_until_epoch": _to_int(resilience_row.get("cooldown_until_epoch")),
            "last_error_type": _clip(resilience_row.get("last_error_type"), max_len=80),
        },
        "intervention_reason": _clip(
            runtime_transition
            or resilience_row.get("degrade_reason")
            or route_reason_text,
            max_len=180,
        ),
        "strategy_generation_mode": strategy_generation_mode,
    }
