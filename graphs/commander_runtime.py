from __future__ import annotations

"""M21-1: Canonical commander runtime entry.

This module provides one stable entry for orchestration while preserving
existing runtime behavior.

Implementation note:
  - This file is the primary commander/orchestrator implementation.
  - `graphs/nodes/commander_node.py` is a thin graph wrapper.
  - `libs/agent/commander.py` is legacy compatibility scaffolding.
  - Commander only routes runtime flow; it does not select symbols or execute orders.

Modes:
  - graph_spine: run M17 graph spine (`run_trading_graph`)
  - decision_packet: run strategist decision + execution packet path
    (`decide_trade` -> `execute_from_packet`)
  - integrated_chain: run visible chain
    (`strategist_node -> scanner_node -> monitor_node -> decision_node -> execute_from_packet`)

Default mode is graph_spine for backward compatibility.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional, Tuple

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.contracts.agent_outputs import build_commander_shadow_artifact
from libs.runtime.monitor_policy import (
    build_default_monitor_entry_policy,
    build_monitor_entry_policy_bundle,
    normalize_monitor_entry_policy,
)
from libs.runtime.scanner_bias import normalize_scanner_bias_context, summarize_scanner_bias_context
from libs.runtime.canonical_artifacts import write_commander_artifact, write_commander_shadow_artifact
from libs.runtime.resilience_state import ensure_runtime_resilience_state


RuntimeMode = Literal["graph_spine", "decision_packet", "integrated_chain"]
RuntimePhase = Literal["preopen", "session", "closeout"]


_PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC = 120
_PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD = 0.80


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_mode(value: Any) -> RuntimeMode:
    v = str(value or "").strip().lower()
    if v == "decision_packet":
        return "decision_packet"
    if v in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    return "graph_spine"


def _normalize_transition(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("retry", "pause", "cancel", "resume"):
        return v
    return ""


def _normalize_phase(value: Any) -> RuntimePhase:
    v = str(value or "").strip().lower()
    if v == "preopen":
        return "preopen"
    if v == "closeout":
        return "closeout"
    return "session"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _runtime_now_epoch(state: Dict[str, Any]) -> int:
    return _coerce_int(state.get("now_epoch"), int(time.time()))


def _runtime_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _derive_commander_market_regime(state: Dict[str, Any], *, shadow_assessment: Dict[str, Any]) -> tuple[str, bool]:
    direct_regime = str(state.get("market_regime") or "").strip()
    if direct_regime:
        return direct_regime, False
    shadow_regime = str(
        (
            (shadow_assessment.get("post_strategist_assessment") or {}).get("market_regime")
            if isinstance(shadow_assessment.get("post_strategist_assessment"), dict)
            else ""
        )
        or ""
    ).strip()
    if shadow_regime:
        return shadow_regime, True
    global_signal = state.get("global_signal") if isinstance(state.get("global_signal"), dict) else {}
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    sentiment_score = _runtime_float(global_signal.get("score"), 0.0)
    fear_level = _runtime_float(fear_index.get("level"), 0.0)
    if fear_level >= 28.0 or sentiment_score <= -0.15:
        return "risk_off", False
    if fear_level <= 20.0 and sentiment_score >= 0.15:
        return "risk_on", False
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    fallback_regime = str(strategist_output.get("market_regime") or "").strip()
    if fallback_regime:
        return fallback_regime, True
    return "neutral", False


def _build_shadow_assessment_summary(
    state: Dict[str, Any],
    *,
    mode_value: str,
    phase_value: str,
    status_value: str,
    path_value: str,
    reason_text: str = "",
) -> Dict[str, Any]:
    try:
        return build_commander_shadow_artifact(
            state,
            mode=str(mode_value or ""),
            phase=str(phase_value or ""),
            path=str(path_value or ""),
            status=str(status_value or "ok"),
            reason=str(reason_text or ""),
        )
    except Exception:
        return {}


def _commander_decision_event_meta(state: Dict[str, Any]) -> Dict[str, Any]:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    return {
        "shadow_used": bool(commander_decision.get("shadow_used")),
        "source_priority": list(commander_decision.get("source_priority") or []),
        "strategist_fallback_used": bool(commander_decision.get("strategist_fallback_used")),
        "applied_policy": dict(commander_decision.get("applied_policy") or {}),
        "policy_source": str(commander_decision.get("policy_source") or ""),
        "policy_validation_status": str(commander_decision.get("policy_validation_status") or ""),
        "policy_fallback_used": bool(commander_decision.get("policy_fallback_used")),
        "policy_fallback_reason": str(commander_decision.get("policy_fallback_reason") or ""),
        "override_reason": str(commander_decision.get("override_reason") or ""),
        "applied_policy_source_chain": list(commander_decision.get("applied_policy_source_chain") or []),
    }


def _summarize_monitor_entry_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(policy or {}) if isinstance(policy, dict) else {}
    keys = (
        "timeframe_minutes",
        "breakout_lookback",
        "volume_lookback",
        "volume_ratio_min",
        "min_extended_from_vwap_pct",
        "max_extended_from_vwap_pct",
        "pullback_min_pct",
        "pullback_max_pct",
        "reclaim_tolerance_pct",
        "breakout_buffer_pct",
        "intent_cooldown_sec",
        "require_vwap_reclaim",
        "require_rebound",
        "policy_source",
    )
    return {key: row.get(key) for key in keys if key in row}


def _resolve_commander_applied_policy(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    default_policy = build_default_monitor_entry_policy()

    candidate_policy: Dict[str, Any] = {}
    candidate_source = "default"
    if isinstance(strategist_output.get("monitor_entry_policy"), dict) and strategist_output.get("monitor_entry_policy"):
        candidate_policy = dict(strategist_output.get("monitor_entry_policy") or {})
        candidate_source = "strategist"
    elif isinstance(strategy_monitor_policy.get("entry_policy"), dict) and strategy_monitor_policy.get("entry_policy"):
        candidate_policy = dict(strategy_monitor_policy.get("entry_policy") or {})
        candidate_source = "strategy_policy.monitor_policy.entry_policy"
    elif isinstance(state.get("monitor_entry_policy"), dict) and state.get("monitor_entry_policy"):
        candidate_policy = dict(state.get("monitor_entry_policy") or {})
        candidate_source = "state.monitor_entry_policy"

    policy_source_hint = str(candidate_policy.get("policy_source") or "").strip()
    normalized_policy, normalized_meta = normalize_monitor_entry_policy(
        candidate_policy or None,
        fallback_policy=default_policy,
        policy_source=policy_source_hint or ("strategist" if candidate_source == "strategist" else default_policy.policy_source),
    )

    validation_status = str(normalized_meta.get("status") or "ok")
    fallback_used = bool(normalized_meta.get("fallback_used"))
    fallback_reason = str(normalized_meta.get("fallback_reason") or "")
    partial_normalized = bool(normalized_meta.get("partial_normalized"))
    default_filled_fields = list(normalized_meta.get("default_filled_fields") or [])
    validation_missing_fields = list(
        normalized_meta.get("policy_validation_missing_fields")
        or normalized_meta.get("missing_fields")
        or []
    )
    validation_invalid_fields = list(
        normalized_meta.get("policy_validation_invalid_fields")
        or normalized_meta.get("invalid_fields")
        or []
    )
    if candidate_source == "strategist":
        validation_status = str(strategist_output.get("policy_validation_status") or validation_status or "ok")
        fallback_used = bool(
            strategist_output.get("policy_fallback_used")
            if strategist_output.get("policy_fallback_used") is not None
            else fallback_used
        )
        fallback_reason = str(strategist_output.get("policy_fallback_reason") or fallback_reason or "")
        partial_normalized = bool(
            strategist_output.get("policy_partial_normalized")
            if strategist_output.get("policy_partial_normalized") is not None
            else partial_normalized
        )
        default_filled_fields = list(
            strategist_output.get("policy_default_filled_fields")
            or default_filled_fields
            or []
        )
        validation_missing_fields = list(
            strategist_output.get("policy_validation_missing_fields")
            or validation_missing_fields
            or []
        )
        validation_invalid_fields = list(
            strategist_output.get("policy_validation_invalid_fields")
            or validation_invalid_fields
            or []
        )

    applied_policy = build_monitor_entry_policy_bundle(
        threshold_policy=normalized_policy,
        playbook=str(strategist_output.get("playbook") or ""),
        monitor_guidance=str(strategist_output.get("monitor_guidance") or ""),
        risk_tone=str(strategist_output.get("risk_tone") or ""),
        trade_aggressiveness=str(strategist_output.get("trade_aggressiveness") or ""),
        interpretation_policy=(
            dict(candidate_policy.get("interpretation_policy") or {})
            if isinstance(candidate_policy.get("interpretation_policy"), dict)
            else None
        ),
    )
    policy_source = str(applied_policy.get("policy_source") or policy_source_hint or candidate_source or default_policy.policy_source)
    if not candidate_policy:
        policy_source = "default"
        validation_status = str(normalized_meta.get("status") or "ok")
        fallback_used = bool(normalized_meta.get("fallback_used") or True)
        fallback_reason = str(normalized_meta.get("fallback_reason") or "no_strategist_policy_available")
        partial_normalized = bool(normalized_meta.get("partial_normalized"))
        default_filled_fields = list(normalized_meta.get("default_filled_fields") or [])
        validation_missing_fields = list(
            normalized_meta.get("policy_validation_missing_fields")
            or normalized_meta.get("missing_fields")
            or []
        )
        validation_invalid_fields = list(
            normalized_meta.get("policy_validation_invalid_fields")
            or normalized_meta.get("invalid_fields")
            or []
        )

    source_chain = [candidate_source or "default", "validation"]
    if fallback_used:
        source_chain.append("default_fallback")
    source_chain.append("commander_confirmed")
    source_chain = [str(x) for x in source_chain if str(x or "").strip()]

    return {
        "applied_policy": dict(applied_policy),
        "policy_source": policy_source,
        "policy_validation_status": validation_status,
        "policy_fallback_used": bool(fallback_used),
        "policy_fallback_reason": fallback_reason,
        "policy_partial_normalized": bool(partial_normalized),
        "policy_default_filled_fields": list(default_filled_fields),
        "policy_validation_missing_fields": list(validation_missing_fields),
        "policy_validation_invalid_fields": list(validation_invalid_fields),
        "override_reason": "",
        "applied_policy_source_chain": source_chain,
        "monitor_entry_policy_summary": _summarize_monitor_entry_policy(applied_policy),
    }


def _attach_commander_applied_policy(state: Dict[str, Any]) -> Dict[str, Any]:
    policy_meta = _resolve_commander_applied_policy(state)
    applied_policy = dict(policy_meta.get("applied_policy") or {})
    state["commander_applied_policy"] = dict(applied_policy)
    state["commander_applied_policy_meta"] = dict(policy_meta)
    state["monitor_entry_policy"] = dict(applied_policy)

    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    if not strategist_output:
        return state

    strategist_output = dict(strategist_output)
    strategy_policy = (
        dict(strategist_output.get("strategy_policy") or {})
        if isinstance(strategist_output.get("strategy_policy"), dict)
        else {}
    )
    scanner_policy = (
        dict(strategy_policy.get("scanner_policy") or {})
        if isinstance(strategy_policy.get("scanner_policy"), dict)
        else {}
    )
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    commander_context = (
        dict(strategy_policy.get("commander_context") or {})
        if isinstance(strategy_policy.get("commander_context"), dict)
        else {}
    )
    raw_scanner_bias_context = {}
    if isinstance(commander_context.get("scanner_bias"), dict):
        raw_scanner_bias_context = dict(commander_context.get("scanner_bias") or {})
    elif isinstance(scanner_policy.get("scanner_bias"), dict):
        raw_scanner_bias_context = dict(scanner_policy.get("scanner_bias") or {})
    elif isinstance(strategist_output.get("scanner_bias_context"), dict):
        raw_scanner_bias_context = dict(strategist_output.get("scanner_bias_context") or {})
    scanner_bias_context, scanner_bias_meta = normalize_scanner_bias_context(
        raw_scanner_bias_context or None,
        bias_source="commander_confirmed",
    )
    scanner_bias_summary = summarize_scanner_bias_context(scanner_bias_context)
    commander_context.update(
        {
            "source": str(commander_context.get("source") or "commander_decision"),
            "market_regime": str(commander_decision.get("market_regime") or commander_context.get("market_regime") or ""),
            "session_bias": str(commander_decision.get("session_bias") or commander_context.get("session_bias") or ""),
            "risk_mode": str(commander_decision.get("risk_mode") or commander_context.get("risk_mode") or ""),
            "allowed_playbooks": list(commander_decision.get("allowed_playbooks") or commander_context.get("allowed_playbooks") or []),
            "banned_playbooks": list(commander_decision.get("banned_playbooks") or commander_context.get("banned_playbooks") or []),
            "scanner_mission": str(commander_decision.get("scanner_mission") or commander_context.get("scanner_mission") or ""),
            "monitor_mission": str(commander_decision.get("monitor_mission") or commander_context.get("monitor_mission") or ""),
            "llm_policy": str(commander_decision.get("llm_policy") or commander_context.get("llm_policy") or ""),
            "command_intent": str(commander_decision.get("command_intent") or commander_context.get("command_intent") or ""),
            "strategist_invocation": str(commander_decision.get("strategist_invocation") or commander_context.get("strategist_invocation") or ""),
            "flow_instruction": str(commander_decision.get("flow_instruction") or commander_context.get("flow_instruction") or ""),
            "no_trade_reason_code": str(commander_decision.get("no_trade_reason_code") or commander_context.get("no_trade_reason_code") or ""),
            "decision_summary": str(commander_decision.get("decision_summary") or commander_context.get("decision_summary") or ""),
            "strategist_refresh_requested": bool(
                commander_decision.get("strategist_refresh_requested")
                if commander_decision.get("strategist_refresh_requested") is not None
                else commander_context.get("strategist_refresh_requested")
            ),
            "strategist_refresh_reason": str(
                commander_decision.get("strategist_refresh_reason")
                or commander_context.get("strategist_refresh_reason")
                or ""
            ),
            "strategist_refresh_context": dict(
                commander_decision.get("strategist_refresh_context")
                or commander_context.get("strategist_refresh_context")
                or {}
            ),
            "observations": dict(commander_decision.get("observations") or commander_context.get("observations") or {}),
            "source_priority": list(commander_decision.get("source_priority") or commander_context.get("source_priority") or []),
            "source_refs": dict(commander_decision.get("source_refs") or commander_context.get("source_refs") or {}),
            "shadow_used": bool(
                commander_decision.get("shadow_used")
                if commander_decision.get("shadow_used") is not None
                else commander_context.get("shadow_used")
            ),
            "strategist_fallback_used": bool(
                commander_decision.get("strategist_fallback_used")
                if commander_decision.get("strategist_fallback_used") is not None
                else commander_context.get("strategist_fallback_used")
            ),
            "applied_policy": dict(applied_policy),
            "policy_source": str(policy_meta.get("policy_source") or ""),
            "policy_validation_status": str(policy_meta.get("policy_validation_status") or ""),
            "policy_fallback_used": bool(policy_meta.get("policy_fallback_used")),
            "policy_fallback_reason": str(policy_meta.get("policy_fallback_reason") or ""),
            "policy_partial_normalized": bool(policy_meta.get("policy_partial_normalized")),
            "policy_default_filled_fields": list(policy_meta.get("policy_default_filled_fields") or []),
            "policy_validation_missing_fields": list(policy_meta.get("policy_validation_missing_fields") or []),
            "policy_validation_invalid_fields": list(policy_meta.get("policy_validation_invalid_fields") or []),
            "override_reason": str(policy_meta.get("override_reason") or ""),
            "applied_policy_source_chain": list(policy_meta.get("applied_policy_source_chain") or []),
            "monitor_entry_policy_summary": dict(policy_meta.get("monitor_entry_policy_summary") or {}),
            "scanner_bias": scanner_bias_context.to_dict(),
            "scanner_bias_summary": dict(scanner_bias_summary),
        }
    )
    strategy_policy["commander_context"] = commander_context

    monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    monitor_policy["applied_policy"] = dict(applied_policy)
    monitor_policy["policy_source"] = str(policy_meta.get("policy_source") or "")
    monitor_policy["policy_validation_status"] = str(policy_meta.get("policy_validation_status") or "")
    monitor_policy["policy_fallback_used"] = bool(policy_meta.get("policy_fallback_used"))
    monitor_policy["policy_fallback_reason"] = str(policy_meta.get("policy_fallback_reason") or "")
    monitor_policy["policy_partial_normalized"] = bool(policy_meta.get("policy_partial_normalized"))
    monitor_policy["policy_default_filled_fields"] = list(policy_meta.get("policy_default_filled_fields") or [])
    monitor_policy["policy_validation_missing_fields"] = list(policy_meta.get("policy_validation_missing_fields") or [])
    monitor_policy["policy_validation_invalid_fields"] = list(policy_meta.get("policy_validation_invalid_fields") or [])
    monitor_policy["override_reason"] = str(policy_meta.get("override_reason") or "")
    monitor_policy["applied_policy_source_chain"] = list(policy_meta.get("applied_policy_source_chain") or [])
    strategy_policy["monitor_policy"] = monitor_policy
    scanner_policy["scanner_bias"] = scanner_bias_context.to_dict()
    scanner_policy["scanner_bias_summary"] = dict(scanner_bias_summary)
    strategy_policy["scanner_policy"] = scanner_policy

    provenance = (
        dict(strategy_policy.get("provenance") or {})
        if isinstance(strategy_policy.get("provenance"), dict)
        else {}
    )
    provenance["applied_policy_source"] = str(policy_meta.get("policy_source") or "")
    provenance["policy_validation_status"] = str(policy_meta.get("policy_validation_status") or "")
    provenance["policy_fallback_used"] = bool(policy_meta.get("policy_fallback_used"))
    provenance["policy_fallback_reason"] = str(policy_meta.get("policy_fallback_reason") or "")
    provenance["policy_partial_normalized"] = bool(policy_meta.get("policy_partial_normalized"))
    provenance["policy_default_filled_fields"] = list(policy_meta.get("policy_default_filled_fields") or [])
    provenance["policy_validation_missing_fields"] = list(policy_meta.get("policy_validation_missing_fields") or [])
    provenance["policy_validation_invalid_fields"] = list(policy_meta.get("policy_validation_invalid_fields") or [])
    provenance["override_reason"] = str(policy_meta.get("override_reason") or "")
    provenance["applied_policy_source_chain"] = list(policy_meta.get("applied_policy_source_chain") or [])
    provenance["scanner_bias_source"] = str(scanner_bias_meta.get("bias_source") or "")
    strategy_policy["provenance"] = provenance

    strategist_output["strategy_policy"] = strategy_policy
    strategist_output["commander_context_ref"] = {
        **(
            dict(strategist_output.get("commander_context_ref") or {})
            if isinstance(strategist_output.get("commander_context_ref"), dict)
            else {}
        ),
        "source": str(commander_context.get("source") or ""),
        "market_regime": str(commander_context.get("market_regime") or ""),
        "session_bias": str(commander_context.get("session_bias") or ""),
        "risk_mode": str(commander_context.get("risk_mode") or ""),
        "command_intent": str(commander_context.get("command_intent") or ""),
        "strategist_invocation": str(commander_context.get("strategist_invocation") or ""),
        "llm_policy": str(commander_context.get("llm_policy") or ""),
        "no_trade_reason_code": str(commander_context.get("no_trade_reason_code") or ""),
        "strategist_refresh_requested": bool(commander_context.get("strategist_refresh_requested")),
        "strategist_refresh_reason": str(commander_context.get("strategist_refresh_reason") or ""),
        "strategist_refresh_context": dict(commander_context.get("strategist_refresh_context") or {}),
        "decision_summary": str(commander_context.get("decision_summary") or ""),
        "source_priority": list(commander_context.get("source_priority") or []),
        "policy_source": str(policy_meta.get("policy_source") or ""),
        "policy_validation_status": str(policy_meta.get("policy_validation_status") or ""),
        "policy_fallback_used": bool(policy_meta.get("policy_fallback_used")),
        "override_reason": str(policy_meta.get("override_reason") or ""),
        "applied_policy_present": bool(applied_policy),
    }
    strategist_output["policy_provenance"] = dict(provenance)
    strategist_output["scanner_bias_context"] = scanner_bias_context.to_dict()
    strategist_output["scanner_bias_summary"] = dict(scanner_bias_summary)
    state["strategist_output"] = _normalize_strategist_output_contract(strategist_output)
    state["strategy_policy"] = dict(strategy_policy)
    state["scanner_bias_context"] = scanner_bias_context.to_dict()
    return state


def _build_commander_decision(
    state: Dict[str, Any],
    *,
    mode_value: str,
    phase_value: str,
    status_value: str,
    path_value: str,
    reason_text: str = "",
) -> Dict[str, Any]:
    portfolio_snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    preflight = state.get("portfolio_preflight") if isinstance(state.get("portfolio_preflight"), dict) else {}
    runtime_fast_path = state.get("runtime_fast_path") if isinstance(state.get("runtime_fast_path"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    resilience = state.get("runtime_resilience_state") if isinstance(state.get("runtime_resilience_state"), dict) else {}
    shadow_assessment = _build_shadow_assessment_summary(
        state,
        mode_value=mode_value,
        phase_value=phase_value,
        status_value=status_value,
        path_value=path_value,
        reason_text=reason_text,
    )
    positions = [row for row in list(portfolio_snapshot.get("positions") or []) if isinstance(row, dict)]
    open_position_count = len(positions)
    market_regime, strategist_fallback_used = _derive_commander_market_regime(state, shadow_assessment=shadow_assessment)
    stress_flags = list(
        (
            (strategist_output.get("macro_stress_overlay") or {}).get("stress_flags")
            if isinstance(strategist_output.get("macro_stress_overlay"), dict)
            else []
        )
        or []
    )
    if str(phase_value or "").strip() == "preopen":
        session_bias = "preopen_context"
    elif str(phase_value or "").strip() == "closeout":
        session_bias = "closeout_control"
    elif open_position_count > 0:
        session_bias = "position_management"
    elif "cached" in str(path_value or ""):
        session_bias = "context_reuse"
    else:
        session_bias = "active_selection"

    if bool(preflight.get("blocked")) or str(status_value or "").strip().lower() in {"blocked", "preflight_blocked"}:
        risk_mode = "blocked"
    elif market_regime == "risk_off" or bool(stress_flags) or str(resilience.get("degrade_mode") or "").strip():
        risk_mode = "defensive"
    elif market_regime == "risk_on":
        risk_mode = "offensive"
    else:
        risk_mode = "balanced"

    allowed_playbooks: list[str]
    if risk_mode == "blocked":
        allowed_playbooks = []
    elif risk_mode == "defensive":
        allowed_playbooks = ["defensive", "pullback"]
    elif risk_mode == "offensive":
        allowed_playbooks = ["breakout", "pullback"]
    else:
        allowed_playbooks = ["pullback", "defensive", "breakout"]
    all_playbooks = ["breakout", "pullback", "reversal", "defensive"]
    banned_playbooks = [x for x in all_playbooks if x not in allowed_playbooks]

    if risk_mode == "defensive":
        scanner_mission = "Prioritize liquid leaders and defensive candidates with resilient participation."
        monitor_mission = "Require cleaner confirmation and protect downside quickly."
    elif risk_mode == "offensive":
        scanner_mission = "Prioritize liquid momentum leaders with strong participation and clean continuation."
        monitor_mission = "Confirm intraday continuation promptly while respecting risk rails."
    elif session_bias == "position_management":
        scanner_mission = "Keep candidate refresh narrow while existing exposure is being managed."
        monitor_mission = "Focus on hold versus exit confirmation for open positions first."
    else:
        scanner_mission = "Prioritize balanced liquid leaders with clear scanner fit and manageable risk."
        monitor_mission = "Wait for confirmation and avoid low-quality chase entries."

    if "cached" in str(path_value or "") or str(runtime_fast_path.get("reason") or "").strip() == "flat_position_cached_strategist":
        llm_policy = "prefer_cached_context"
    elif session_bias == "position_management":
        llm_policy = "allow_if_context_changed"
    elif str(phase_value or "").strip() == "preopen":
        llm_policy = "allow_context_refresh"
    else:
        llm_policy = "allow"

    shadow_used = bool(shadow_assessment)
    shadow_no_trade_reason_code = str(shadow_assessment.get("no_trade_reason_code") or "").strip()
    shadow_reason_summary = str(shadow_assessment.get("reason_summary") or "").strip()
    command_intent = str(shadow_assessment.get("decision") or "OBSERVE_ONLY").strip() if shadow_used else "OBSERVE_ONLY"
    strategist_invocation = str(shadow_assessment.get("strategist_action_recommendation") or "").strip() if shadow_used else ""
    llm_policy = str(shadow_assessment.get("llm_call_advice") or llm_policy).strip()
    flow_instruction = str(shadow_assessment.get("suggested_action") or "").strip()
    no_trade_reason_code = shadow_no_trade_reason_code
    if not strategist_invocation:
        strategist_invocation = "SKIP" if open_position_count > 0 else "RUN"
    if not flow_instruction:
        flow_instruction = "HOLD_OBSERVE" if open_position_count > 0 else "NO_ACTION"
    if not no_trade_reason_code:
        no_trade_reason_code = "POSITION_ALREADY_OPEN" if open_position_count > 0 else "NONE"
    observations = dict(shadow_assessment.get("observations") or {}) if isinstance(shadow_assessment.get("observations"), dict) else {}
    refresh_assessment = _assess_pre_buy_strategist_refresh_need(state, commander_market_regime=market_regime)
    strategist_refresh_requested = bool(refresh_assessment.get("requested"))
    strategist_refresh_reason = str(refresh_assessment.get("refresh_signal") or refresh_assessment.get("reason") or "").strip()
    strategist_refresh_context = {
        k: v
        for k, v in dict(refresh_assessment).items()
        if k not in {"requested"}
    }
    cache_reuse_assessment = _assess_cached_strategist_reuse_preference(state)
    strategist_cache_preferred = bool(cache_reuse_assessment.get("preferred"))
    strategist_cache_preference_reason = str(cache_reuse_assessment.get("reason") or "").strip()
    strategist_cache_preference_context = {
        k: v
        for k, v in dict(cache_reuse_assessment).items()
        if k not in {"preferred"}
    }
    if strategist_refresh_requested:
        strategist_invocation = "RUN_REFRESH"
        llm_policy = "allow_context_refresh"
        flow_instruction = "REFRESH_STRATEGY_FRAME"
        observations = {
            **observations,
            "strategist_refresh_requested": True,
            "strategist_refresh_reason": strategist_refresh_reason,
        }
    elif strategist_invocation == "RUN" and strategist_cache_preferred:
        strategist_invocation = "SKIP"
        llm_policy = "prefer_cached_context"
        flow_instruction = "REUSE_STRATEGY_FRAME"
        observations = {
            **observations,
            "strategist_cache_preferred": True,
            "strategist_cache_preference_reason": strategist_cache_preference_reason,
        }
    source_priority = ["shadow_commander", "runtime_observation", "strategist_fallback"]
    if strategist_refresh_requested:
        source_priority = ["commander_refresh_heuristic", *source_priority]
    elif strategist_invocation == "SKIP" and strategist_cache_preferred:
        source_priority = ["commander_cache_reuse", *source_priority]
    source_refs = {
        "shadow_event": "commander_router.shadow_assessment",
        "runtime_fast_path_reason": str(runtime_fast_path.get("reason") or ""),
        "runtime_path": str(path_value or ""),
        "strategist_fallback_fields": ["market_regime"] if strategist_fallback_used else [],
    }
    if strategist_refresh_requested:
        source_refs["strategist_refresh_reason"] = strategist_refresh_reason
        source_refs["strategist_refresh_scope"] = "strategy_frame_refresh"
    elif strategist_invocation == "SKIP" and strategist_cache_preferred:
        source_refs["strategist_cache_preference_reason"] = strategist_cache_preference_reason
        source_refs["strategist_cache_preference_scope"] = "cached_strategy_frame_reuse"
    applied_policy_meta = (
        dict(state.get("commander_applied_policy_meta") or {})
        if isinstance(state.get("commander_applied_policy_meta"), dict)
        else {}
    )
    if not applied_policy_meta:
        strategist_policy_present = bool(
            (isinstance(strategist_output.get("monitor_entry_policy"), dict) and strategist_output.get("monitor_entry_policy"))
            or (isinstance(state.get("monitor_entry_policy"), dict) and state.get("monitor_entry_policy"))
            or (
                isinstance((strategist_output.get("strategy_policy") or {}).get("monitor_policy"), dict)
                and ((strategist_output.get("strategy_policy") or {}).get("monitor_policy") or {}).get("entry_policy")
            )
        )
        if strategist_policy_present:
            applied_policy_meta = _resolve_commander_applied_policy(state)
    applied_policy = dict(applied_policy_meta.get("applied_policy") or {})

    decision_summary = (
        f"Commander set regime={market_regime}, session_bias={session_bias}, risk_mode={risk_mode}; "
        f"allowed_playbooks={', '.join(allowed_playbooks) if allowed_playbooks else 'none'}."
    )
    if shadow_reason_summary:
        decision_summary = shadow_reason_summary
    if reason_text:
        decision_summary = f"{decision_summary} Runtime note: {str(reason_text).strip()[:180]}"
    if strategist_refresh_requested:
        decision_summary = (
            f"{decision_summary} Commander requested fresh strategist context "
            f"before rebuilding the entry frame ({strategist_refresh_reason or 'strategy_refresh'})."
        )
    elif strategist_invocation == "SKIP" and strategist_cache_preferred:
        decision_summary = (
            f"{decision_summary} Commander preferred cached strategist context "
            f"for this cycle ({strategist_cache_preference_reason or 'context_reuse'})."
        )

    return {
        "market_regime": market_regime,
        "session_bias": session_bias,
        "risk_mode": risk_mode,
        "allowed_playbooks": list(allowed_playbooks),
        "banned_playbooks": list(banned_playbooks),
        "scanner_mission": scanner_mission,
        "monitor_mission": monitor_mission,
        "llm_policy": llm_policy,
        "llm_invocation_policy": llm_policy,
        "command_intent": command_intent,
        "strategist_invocation": strategist_invocation,
        "flow_instruction": flow_instruction,
        "no_trade_reason_code": no_trade_reason_code,
        "observations": observations,
        "source_priority": source_priority,
        "source_refs": source_refs,
        "strategist_fallback_used": bool(strategist_fallback_used),
        "shadow_used": shadow_used,
        "shadow_assessment_summary": shadow_reason_summary,
        "strategist_refresh_requested": strategist_refresh_requested,
        "strategist_refresh_reason": strategist_refresh_reason,
        "strategist_refresh_context": strategist_refresh_context,
        "strategist_cache_preferred": bool(strategist_invocation == "SKIP" and strategist_cache_preferred),
        "strategist_cache_preference_reason": strategist_cache_preference_reason,
        "strategist_cache_preference_context": strategist_cache_preference_context,
        "decision_summary": decision_summary,
        "applied_policy": applied_policy,
        "policy_source": str(applied_policy_meta.get("policy_source") or ""),
        "policy_validation_status": str(applied_policy_meta.get("policy_validation_status") or ""),
        "policy_fallback_used": bool(applied_policy_meta.get("policy_fallback_used")),
        "policy_fallback_reason": str(applied_policy_meta.get("policy_fallback_reason") or ""),
        "policy_partial_normalized": bool(applied_policy_meta.get("policy_partial_normalized")),
        "policy_default_filled_fields": list(applied_policy_meta.get("policy_default_filled_fields") or []),
        "policy_validation_missing_fields": list(applied_policy_meta.get("policy_validation_missing_fields") or []),
        "policy_validation_invalid_fields": list(applied_policy_meta.get("policy_validation_invalid_fields") or []),
        "override_reason": str(applied_policy_meta.get("override_reason") or ""),
        "applied_policy_source_chain": list(applied_policy_meta.get("applied_policy_source_chain") or []),
    }


def _ensure_commander_shadow_runtime(state: Dict[str, Any]) -> Dict[str, Any]:
    runtime = state.get("commander_shadow_runtime") if isinstance(state.get("commander_shadow_runtime"), dict) else {}
    runtime = dict(runtime)
    runtime.setdefault("strategist_executed", None)
    runtime.setdefault("strategist_called", None)
    runtime.setdefault("llm_called_by_strategist", None)
    runtime.setdefault("used_cached_strategist", False)
    runtime.setdefault("market_changed", None)
    runtime.setdefault("repeated_same_context", None)
    runtime.setdefault("retry_count_estimate", None)
    runtime.setdefault("monitor_decision", "")
    runtime.setdefault("executor_action", "")
    runtime.setdefault("executor_status", "")
    runtime.setdefault("pre_buy_refresh_requested", False)
    runtime.setdefault("pre_buy_refresh_reason", "")
    runtime.setdefault("pre_buy_refresh_context", {})
    runtime.setdefault("prior_context", {})
    state["commander_shadow_runtime"] = runtime
    return runtime


def _reset_commander_shadow_runtime(state: Dict[str, Any]) -> None:
    state["commander_shadow_runtime"] = {
        "strategist_executed": None,
        "strategist_called": None,
        "llm_called_by_strategist": None,
        "used_cached_strategist": False,
        "market_changed": None,
        "repeated_same_context": None,
        "retry_count_estimate": None,
        "monitor_decision": "",
        "executor_action": "",
        "executor_status": "",
        "pre_buy_refresh_requested": False,
        "pre_buy_refresh_reason": "",
        "pre_buy_refresh_context": {},
        "prior_context": {},
    }


def _strategist_shadow_fingerprint(output: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(output or {}) if isinstance(output, dict) else {}
    return {
        "market_regime": str(row.get("market_regime") or "").strip().lower(),
        "market_sentiment": str(row.get("market_sentiment") or "").strip().lower(),
        "playbook": str(row.get("playbook") or "").strip().lower(),
        "monitor_guidance": str(row.get("monitor_guidance") or "").strip().lower(),
        "risk_tone": str(row.get("risk_tone") or "").strip().lower(),
        "trade_aggressiveness": str(row.get("trade_aggressiveness") or "").strip().lower(),
        "themes": tuple(sorted(str(x or "").strip().lower() for x in list(row.get("themes") or []) if str(x or "").strip())),
        "avoid_themes": tuple(sorted(str(x or "").strip().lower() for x in list(row.get("avoid_themes") or []) if str(x or "").strip())),
        "global_sentiment_score": round(float(row.get("global_sentiment_score") or 0.0), 4) if row.get("global_sentiment_score") not in (None, "") else None,
    }


def _shadow_market_changed(previous_output: Dict[str, Any], current_output: Dict[str, Any]) -> Optional[bool]:
    previous = _strategist_shadow_fingerprint(previous_output)
    current = _strategist_shadow_fingerprint(current_output)
    if not any(v not in (None, "", (), []) for v in previous.values()):
        return None
    return previous != current


def _shadow_text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _shadow_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _shadow_selected_symbol(state: Dict[str, Any]) -> str:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    return _shadow_text(selected.get("symbol") or monitor_output.get("selected_symbol"), max_len=24)


def _shadow_selected_score(state: Dict[str, Any]) -> Optional[float]:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    for key in ("score_total", "score", "confidence"):
        value = _shadow_float(selected.get(key))
        if value is not None:
            return value
    return None


def _seed_commander_shadow_prior_context(state: Dict[str, Any], *, prior_cached_output: Dict[str, Any]) -> None:
    shadow_runtime = _ensure_commander_shadow_runtime(state)
    strategist_llm = state.get("strategist_llm") if isinstance(state.get("strategist_llm"), dict) else {}
    baseline_output = (
        dict(prior_cached_output)
        if isinstance(prior_cached_output, dict) and prior_cached_output
        else dict(state.get("strategist_output") or {}) if isinstance(state.get("strategist_output"), dict) else {}
    )
    baseline_global_signal = baseline_output.get("global_signal") if isinstance(baseline_output.get("global_signal"), dict) else {}
    baseline_fear_index = baseline_global_signal.get("fear_index") if isinstance(baseline_global_signal.get("fear_index"), dict) else {}
    baseline_overlay = baseline_output.get("macro_stress_overlay") if isinstance(baseline_output.get("macro_stress_overlay"), dict) else {}
    shadow_runtime["prior_context"] = {
        "selected_symbol": _shadow_selected_symbol(state),
        "selected_score_total": _shadow_selected_score(state),
        "playbook": _shadow_text(baseline_output.get("playbook"), max_len=40),
        "market_regime": _shadow_text(baseline_output.get("market_regime"), max_len=40),
        "market_sentiment": _shadow_text(baseline_output.get("market_sentiment"), max_len=40),
        "global_sentiment_score": baseline_output.get("global_sentiment_score"),
        "vix_level": baseline_fear_index.get("level") if baseline_fear_index.get("level") not in (None, "") else baseline_overlay.get("vix_level"),
        "stress_flags": [str(x or "").strip() for x in list(baseline_overlay.get("stress_flags") or []) if str(x or "").strip()][:8],
        "llm_status": _shadow_text(strategist_llm.get("status") or strategist_llm.get("llm_status"), max_len=40),
    }
    state["commander_shadow_runtime"] = shadow_runtime


def _resolve_commander_cooldown_policy(state: Dict[str, Any]) -> Tuple[int, int]:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    threshold_default = _coerce_int(os.getenv("COMMANDER_INCIDENT_THRESHOLD", "0"), 0)
    cooldown_default = _coerce_int(os.getenv("COMMANDER_COOLDOWN_SEC", "0"), 0)
    threshold = _coerce_int(policy.get("incident_threshold"), threshold_default)
    cooldown_sec = _coerce_int(policy.get("cooldown_sec"), cooldown_default)
    return max(0, threshold), max(0, cooldown_sec)


def _set_degrade_mode(state: Dict[str, Any], *, reason: str) -> None:
    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        resilience = {}
        state["resilience"] = resilience
    resilience["degrade_mode"] = True
    if not str(resilience.get("degrade_reason") or "").strip():
        resilience["degrade_reason"] = str(reason or "")


def _apply_commander_cooldown_guard(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """M23-4: apply incident/cooldown policy before running node path."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)
    now_epoch = _runtime_now_epoch(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0))
    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))

    if cooldown_until > now_epoch:
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="commander_cooldown_active")
        return False, state, {
            "reason": "cooldown_active",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = now_epoch + cooldown_sec
        resilience["cooldown_until_epoch"] = cooldown_until
        state["resilience"] = resilience
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="incident_threshold_cooldown")
        return False, state, {
            "reason": "incident_threshold_cooldown",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    return True, state, {
        "reason": "cooldown_not_active",
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "now_epoch": now_epoch,
    }


def _register_commander_incident(state: Dict[str, Any], *, error_type: str) -> Dict[str, Any]:
    """M23-4: increment incident counter and optionally open commander cooldown."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0)) + 1
    resilience["incident_count"] = incident_count
    resilience["last_error_type"] = str(error_type or "")

    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))
    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = max(cooldown_until, now_epoch + cooldown_sec)
        resilience["cooldown_until_epoch"] = cooldown_until
        _set_degrade_mode(state, reason="incident_threshold_cooldown")

    state["resilience"] = resilience
    return {
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "last_error_type": str(error_type or ""),
    }


def _apply_operator_resume_intervention(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """M23-6: explicit operator intervention to resume runtime from cooldown/degrade."""
    transition = _normalize_transition(state.get("runtime_control"))
    if transition != "resume":
        return state, {}

    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    before = {
        "degrade_mode": bool(resilience.get("degrade_mode")),
        "degrade_reason": str(resilience.get("degrade_reason") or ""),
        "incident_count": _coerce_int(resilience.get("incident_count"), 0),
        "cooldown_until_epoch": _coerce_int(resilience.get("cooldown_until_epoch"), 0),
        "last_error_type": str(resilience.get("last_error_type") or ""),
    }
    now_epoch = _runtime_now_epoch(state)

    resilience["degrade_mode"] = False
    resilience["degrade_reason"] = ""
    resilience["incident_count"] = 0
    resilience["cooldown_until_epoch"] = 0
    resilience["last_error_type"] = ""
    state["resilience"] = resilience

    return state, {
        "type": "operator_resume",
        "at_epoch": now_epoch,
        "before": before,
        "after": {
            "degrade_mode": False,
            "degrade_reason": "",
            "incident_count": 0,
            "cooldown_until_epoch": 0,
            "last_error_type": "",
        },
    }


def _apply_runtime_transition(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Apply runtime control transition.

    Supported controls in `state["runtime_control"]`:
      - cancel: stop run immediately
      - pause: stop run immediately
      - retry: increment retry counter and continue run
    """
    transition = _normalize_transition(state.get("runtime_control"))
    if not transition:
        return True, state

    state["runtime_transition"] = transition

    if transition == "cancel":
        state["runtime_status"] = "cancelled"
        return False, state

    if transition == "pause":
        state["runtime_status"] = "paused"
        return False, state

    if transition == "resume":
        state["runtime_status"] = "resuming"
        return True, state

    # retry: mark status and continue the selected runtime path.
    state["runtime_status"] = "retrying"
    state["runtime_retry_count"] = _coerce_int(state.get("runtime_retry_count"), 0) + 1
    return True, state


def _runtime_agent_chain(mode: RuntimeMode, phase: RuntimePhase) -> Tuple[str, ...]:
    if phase == "preopen":
        return ("commander_router", "strategist")
    if phase == "closeout":
        return ("commander_router",)
    if mode == "decision_packet":
        return ("commander_router", "strategist", "supervisor", "executor", "reporter")
    if mode == "integrated_chain":
        return ("commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter")
    return ("commander_router", "strategist", "scanner", "monitor", "supervisor", "executor", "reporter")


def _annotate_runtime_plan(state: Dict[str, Any], selected: RuntimeMode, phase: RuntimePhase) -> Dict[str, Any]:
    state["runtime_plan"] = {
        "mode": selected,
        "phase": phase,
        "agents": list(_runtime_agent_chain(selected, phase)),
    }
    return state


def _import_event_logger():
    for mod in ("libs.event_logger", "libs.logging.event_logger", "libs.core.event_logger"):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _ensure_run_id(state: Dict[str, Any]) -> str:
    _EventLogger, new_run_id = _import_event_logger()
    rid = str(state.get("run_id") or new_run_id())
    state["run_id"] = rid
    return rid


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _log_commander_event(state: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="commander_router", event=event, payload=payload)
    except Exception:
        return


def _portfolio_guard_event_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    pg = state.get("portfolio_guard")
    if not isinstance(pg, dict):
        return {}
    return {
        "portfolio_guard": {
            "applied": bool(pg.get("applied")),
            "approved_total": _coerce_int(pg.get("approved_total"), 0),
            "blocked_total": _coerce_int(pg.get("blocked_total"), 0),
            "blocked_reason_counts": pg.get("blocked_reason_counts")
            if isinstance(pg.get("blocked_reason_counts"), dict)
            else {},
        }
    }


def _portfolio_preflight_event_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    pf = state.get("portfolio_preflight")
    if not isinstance(pf, dict):
        return {}
    return {
        "portfolio_preflight": {
            "applied": bool(pf.get("applied")),
            "blocked": bool(pf.get("blocked")),
            "reason": str(pf.get("reason") or ""),
            "phase": str(pf.get("phase") or ""),
        }
    }


def _extract_portfolio_snapshot_health(state: Dict[str, Any]) -> Dict[str, Any]:
    health = state.get("portfolio_snapshot_health")
    if isinstance(health, dict):
        return dict(health)
    snap = state.get("portfolio_snapshot")
    if isinstance(snap, dict) and isinstance(snap.get("_health"), dict):
        return dict(snap.get("_health") or {})
    return {}


def _portfolio_preflight_block_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    health = _extract_portfolio_snapshot_health(state)
    if not health:
        return {}

    reader_ok = bool(health.get("reader_ok"))
    mismatch = bool(health.get("positions_mismatch_detected"))
    reconciled = bool(health.get("reconciliation_applied"))

    reason = ""
    reason_human = ""
    if not reader_ok:
        reason = "portfolio_snapshot_reader_error"
        reason_human = "계좌 조회가 실패해서 전략 판단 전에 실행을 중단했습니다."
    elif mismatch and not reconciled:
        reason = "portfolio_snapshot_positions_mismatch_unresolved"
        reason_human = "계좌 보유 종목과 로컬 상태 불일치가 남아 있어서 전략 판단 전에 실행을 중단했습니다."
    if not reason:
        return {}

    return {
        "blocked": True,
        "reason": reason,
        "reason_human": reason_human,
        "reader_ok": reader_ok,
        "positions_source": str(health.get("positions_source") or ""),
        "reconciliation_status": str(health.get("reconciliation_status") or ""),
        "reader_positions_authoritative": bool(health.get("reader_positions_authoritative")),
        "positions_mismatch_detected": mismatch,
        "reconciliation_applied": reconciled,
        "reader_positions_count": _coerce_int(health.get("reader_positions_count"), 0),
        "persisted_positions_count": _coerce_int(health.get("persisted_positions_count"), 0),
    }


def _apply_portfolio_preflight_guard(state: Dict[str, Any], *, phase: RuntimePhase) -> Tuple[bool, Dict[str, Any]]:
    payload = _portfolio_preflight_block_payload(state)
    if not payload:
        state["portfolio_preflight"] = {
            "applied": True,
            "blocked": False,
            "phase": phase,
        }
        return True, state

    state["portfolio_preflight"] = {
        "applied": True,
        "blocked": True,
        "phase": phase,
        **payload,
    }
    state["runtime_status"] = "preflight_blocked"
    state["path"] = "portfolio_preflight_guard"
    state["decision"] = "reject"
    state["intents"] = []
    state["selected"] = None
    state["execution"] = {
        "allowed": False,
        "ok": False,
        "reason": payload.get("reason"),
        "order": {"action": "NOOP"},
        "payload": {
            "mode": "preflight_guard",
            "reason_human": payload.get("reason_human"),
        },
    }
    return False, state


def _graph_spine_portfolio_preflight_enabled(state: Dict[str, Any], *, phase: RuntimePhase) -> bool:
    if phase != "session":
        return False
    if _is_trueish(state.get("disable_graph_spine_portfolio_preflight")):
        return False
    if _is_trueish(state.get("enable_graph_spine_portfolio_preflight")):
        return True
    return _is_trueish(os.getenv("COMMANDER_GRAPH_SPINE_PORTFOLIO_PREFLIGHT_ENABLED", ""))


def _run_graph_spine_with_preflight(
    state: Dict[str, Any],
    *,
    graph_runner: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot

    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="session")
    if not should_continue:
        return state
    return graph_runner(state)


def _intent_from_monitor_state(state: Dict[str, Any]) -> Dict[str, Any]:
    intents = state.get("intents")
    if not isinstance(intents, list) or not intents:
        return {"action": "NOOP", "reason": "no_monitor_intent"}

    it0 = intents[0] if isinstance(intents[0], dict) else {}
    side = str(it0.get("side") or "BUY").strip().upper()
    action = "BUY" if side == "BUY" else "SELL" if side == "SELL" else "NOOP"
    symbol = str(it0.get("symbol") or state.get("symbol") or state.get("selected_symbol") or "").strip().upper()
    qty = max(0, _coerce_int(it0.get("qty"), 0))

    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    price = it0.get("price")
    if price is None:
        price = market.get("price")

    return {
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "order_type": "limit",
        "order_api_id": "ORDER_SUBMIT",
        "rationale": str(it0.get("thesis") or "monitor_intent"),
    }


def _build_packet_from_state(state: Dict[str, Any], *, intent: Dict[str, Any]) -> Dict[str, Any]:
    risk = state.get("risk_context") if isinstance(state.get("risk_context"), dict) else {}
    exec_context = state.get("exec_context") if isinstance(state.get("exec_context"), dict) else {}
    return {
        "intent": dict(intent),
        "risk": dict(risk),
        "exec_context": dict(exec_context),
    }


def _normalize_strategist_output_contract(output: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(output or {})
    strategy_policy = normalized.get("strategy_policy") if isinstance(normalized.get("strategy_policy"), dict) else {}
    if not strategy_policy:
        return normalized

    strategy_policy = dict(strategy_policy)
    decision_policy = strategy_policy.get("decision_policy") if isinstance(strategy_policy.get("decision_policy"), dict) else {}
    decision_policy = dict(decision_policy or {})
    decision_policy["use_strategy_v1_engine"] = False
    decision_policy["allow_score_override"] = False
    decision_policy["score_override_scope"] = "disabled"
    decision_policy["strategy_v1_name"] = ""
    decision_policy["strategy_variant_hint"] = "unified_ai_strategist"
    for key in (
        "buy_threshold",
        "sell_threshold",
        "high_vol_abs_threshold",
        "news_buy_threshold",
        "news_sell_threshold",
    ):
        decision_policy.pop(key, None)
    strategy_policy["decision_policy"] = decision_policy
    normalized["strategy_policy"] = strategy_policy
    return normalized


def _persist_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    if not strategist_output:
        return state
    if bool(state.get("strategist_blocked")) or bool(strategist_output.get("llm_frame_blocked")):
        return state
    strategist_output = _normalize_strategist_output_contract(strategist_output)
    state["strategist_output"] = dict(strategist_output)
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    persisted_state["strategist_output_cache"] = {
        "output": dict(strategist_output),
        "generated_epoch": int(_runtime_now_epoch(state)),
        "source": "strategist_node",
    }
    state["persisted_state"] = persisted_state
    return state


def _strategist_frame_blocked(state: Dict[str, Any]) -> bool:
    if bool(state.get("strategist_blocked")):
        return True
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategist_llm = state.get("strategist_llm") if isinstance(state.get("strategist_llm"), dict) else {}
    return bool(strategist_output.get("llm_frame_blocked")) or bool(strategist_llm.get("blocked"))


def _apply_strategist_block(state: Dict[str, Any], *, phase: str) -> Dict[str, Any]:
    reason = str(
        state.get("strategist_blocked_reason")
        or ((state.get("strategist_output") or {}).get("llm_frame_blocked_reason") if isinstance(state.get("strategist_output"), dict) else "")
        or ((state.get("strategist_llm") or {}).get("blocked_reason") if isinstance(state.get("strategist_llm"), dict) else "")
        or "strategist_llm_failed"
    )
    payload = {"path": "strategist_llm_blocked", "phase": phase, "reason": reason}
    _log_commander_event(state, "fast_path", payload)
    state["runtime_status"] = "blocked"
    state["path"] = f"{phase}_strategist_blocked"
    state["decision"] = "noop"
    state["decision_reason"] = reason
    return state


def _hydrate_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(state.get("strategist_output"), dict) and state.get("strategist_output"):
        return state
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = persisted_state.get("strategist_output_cache") if isinstance(persisted_state.get("strategist_output_cache"), dict) else {}
    cached = raw_cached.get("output") if isinstance(raw_cached.get("output"), dict) else raw_cached
    if isinstance(cached, dict) and cached:
        state["strategist_output"] = _normalize_strategist_output_contract(cached)
        if isinstance(raw_cached, dict) and raw_cached:
            state["strategist_output_cache_meta"] = dict(raw_cached)
        return state

    held_symbols = _portfolio_open_position_symbols(state)
    position_context = (
        persisted_state.get("position_strategy_context")
        if isinstance(persisted_state.get("position_strategy_context"), dict)
        else {}
    )
    for symbol in held_symbols:
        row = position_context.get(symbol) if isinstance(position_context.get(symbol), dict) else {}
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        if output:
            state["strategist_output"] = _normalize_strategist_output_contract(output)
            state["strategist_output_cache_meta"] = {
                "output": dict(state["strategist_output"]),
                "generated_epoch": _coerce_int(row.get("generated_epoch"), 0),
                "source": str(row.get("source") or "position_strategy_context"),
                "symbol": symbol,
            }
    return state


def _portfolio_open_position_count(state: Dict[str, Any]) -> int:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _coerce_int(row.get("qty"), 0) > 0:
            count += 1
    return int(count)


def _portfolio_open_position_symbols(state: Dict[str, Any]) -> list[str]:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    seen: set[str] = set()
    symbols: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _coerce_int(row.get("qty"), 0) <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _hydrate_monitor_symbol_features(state: Dict[str, Any]) -> Dict[str, Any]:
    held_symbols = _portfolio_open_position_symbols(state)
    if not held_symbols:
        state["monitor_feature_hydration"] = {
            "applied": False,
            "symbol_count": 0,
            "source": "none",
            "errors": [],
        }
        return state

    from graphs.nodes.skill_contracts import extract_market_quotes
    from libs.runtime.scanner_feature_hydration import hydrate_scanner_feature_map

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    skill_quotes, _quote_meta = extract_market_quotes(state)
    feature_map, feature_source, feature_errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": symbol} for symbol in held_symbols],
        skill_quotes=skill_quotes,
        policy=policy,
        refresh_existing=True,
    )
    state["monitor_feature_hydration"] = {
        "applied": True,
        "symbol_count": int(len(held_symbols)),
        "source": str(feature_source or "none"),
        "feature_symbol_count": int(len(feature_map)),
        "errors": list(feature_errors),
        "symbols": list(held_symbols),
    }
    return state


def _should_use_monitor_only_fast_path(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    enabled = _is_trueish(
        state.get("enable_monitor_only_fast_path")
        if state.get("enable_monitor_only_fast_path") is not None
        else os.getenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "true")
    )
    open_position_count = _portfolio_open_position_count(state)
    block_buy_when_open_position = _is_trueish(
        state.get("monitor_block_buy_when_open_position")
        if state.get("monitor_block_buy_when_open_position") is not None
        else os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false")
    )
    payload = {
        "enabled": bool(enabled),
        "open_position_count": int(open_position_count),
        "block_buy_when_open_position": bool(block_buy_when_open_position),
        "reason": "",
    }
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count <= 0:
        payload["reason"] = "no_open_position"
        return False, payload
    if not block_buy_when_open_position:
        payload["reason"] = "buy_not_blocked_when_open_position"
        return False, payload
    payload["reason"] = "holding_position_monitor_only"
    return True, payload


def _strategist_cache_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = persisted_state.get("strategist_output_cache") if isinstance(persisted_state.get("strategist_output_cache"), dict) else {}
    if isinstance(raw_cached.get("output"), dict):
        return dict(raw_cached)
    if raw_cached:
        return {"output": dict(raw_cached), "generated_epoch": 0, "source": "legacy_cache"}
    return {}


def _assess_cached_strategist_reuse_preference(state: Dict[str, Any]) -> Dict[str, Any]:
    enabled = _is_trueish(
        state.get("enable_cached_strategist_when_flat")
        if state.get("enable_cached_strategist_when_flat") is not None
        else os.getenv("COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED", "false")
    )
    open_position_count = _portfolio_open_position_count(state)
    cache_payload = _strategist_cache_payload(state)
    cached_output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    generated_epoch = max(0, _coerce_int(cache_payload.get("generated_epoch"), 0))
    reuse_sec = max(0, _coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600"), 600))
    age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    payload = {
        "preferred": False,
        "enabled": bool(enabled),
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "cache_source": str(cache_payload.get("source") or ""),
        "cached_output_present": bool(cached_output),
        "reason": "",
    }
    if not enabled:
        payload["reason"] = "disabled"
        return payload
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return payload
    if _is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return payload
    if not cached_output:
        payload["reason"] = "no_cached_strategist_output"
        return payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return payload
    payload["preferred"] = True
    payload["reason"] = "commander_preferred_cached_strategist"
    return payload


def _assess_pre_buy_strategist_refresh_need(
    state: Dict[str, Any],
    *,
    commander_market_regime: str = "",
) -> Dict[str, Any]:
    min_cache_age_sec = int(_PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC)
    readiness_threshold = float(_PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD)
    open_position_count = _portfolio_open_position_count(state)
    cache_payload = _strategist_cache_payload(state)
    cached_output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    generated_epoch = max(0, _coerce_int(cache_payload.get("generated_epoch"), 0))
    cache_age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    monitor_state = state.get("monitor") if isinstance(state.get("monitor"), dict) else {}
    entry_detail = state.get("monitor_entry_decision_detail") if isinstance(state.get("monitor_entry_decision_detail"), dict) else {}
    transition_trace = entry_detail.get("transition_trace") if isinstance(entry_detail.get("transition_trace"), dict) else {}
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    selected_symbol = str(
        selected.get("symbol")
        or monitor_output.get("selected_symbol")
        or ""
    ).strip()
    explicit_news_query_targets: list[str] = []
    for value in list(state.get("news_query_targets") or []):
        text = str(value or "").strip()
        if text and text not in explicit_news_query_targets:
            explicit_news_query_targets.append(text)
    cached_news_query_targets: list[str] = []
    for value in list(cached_output.get("news_query_targets") or []):
        text = str(value or "").strip()
        if text and text not in cached_news_query_targets:
            cached_news_query_targets.append(text)
    cached_candidate_hints: list[str] = []
    for value in list(cached_output.get("candidate_hints") or []):
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in cached_candidate_hints:
            cached_candidate_hints.append(symbol)
    for value in list(cached_output.get("candidate_symbols_hint") or []):
        symbol = str(value or "").strip().upper()
        if symbol and symbol not in cached_candidate_hints:
            cached_candidate_hints.append(symbol)
    for row in list(cached_output.get("candidates") or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in cached_candidate_hints:
            cached_candidate_hints.append(symbol)
    selected_symbol_upper = str(selected_symbol or "").strip().upper()
    selected_symbol_in_cached_frame = bool(
        not selected_symbol_upper
        or not cached_candidate_hints
        or selected_symbol_upper in cached_candidate_hints
    )
    cached_market_regime = str(cached_output.get("market_regime") or "").strip().lower()
    current_market_regime = str(commander_market_regime or state.get("market_regime") or "").strip().lower()
    readiness_score = _shadow_float(
        monitor_output.get("entry_transition_readiness_score")
        if monitor_output.get("entry_transition_readiness_score") not in (None, "")
        else monitor_state.get("entry_transition_readiness_score")
        if monitor_state.get("entry_transition_readiness_score") not in (None, "")
        else transition_trace.get("transition_readiness_score")
    )
    became_ready = bool(
        monitor_output.get("entry_became_ready_this_cycle")
        or monitor_state.get("entry_became_ready_this_cycle")
        or transition_trace.get("became_ready_this_cycle")
    )
    prior_intent = str(monitor_output.get("intent_side") or "").strip().upper()
    prior_reason = str(
        monitor_output.get("entry_exit_reason")
        or entry_detail.get("primary_reason_code")
        or entry_detail.get("reason")
        or ""
    ).strip()

    signal = ""
    if (
        explicit_news_query_targets
        and cached_news_query_targets
        and explicit_news_query_targets != cached_news_query_targets
    ):
        signal = "news_query_target_drift"
    elif current_market_regime and cached_market_regime and current_market_regime != cached_market_regime:
        signal = "market_regime_shifted_since_cache"
    elif selected_symbol_upper and cached_candidate_hints and selected_symbol_upper not in cached_candidate_hints:
        signal = "selected_symbol_outside_cached_frame"
    elif prior_intent == "BUY":
        signal = "prior_cycle_buy_intent"
    elif became_ready:
        signal = "became_ready_this_cycle"
    elif readiness_score is not None and readiness_score >= readiness_threshold:
        signal = "transition_readiness_threshold"

    payload = {
        "requested": False,
        "open_position_count": int(open_position_count),
        "selected_symbol": selected_symbol,
        "selected_symbol_in_cached_frame": bool(selected_symbol_in_cached_frame),
        "cached_candidate_hints": list(cached_candidate_hints[:8]),
        "current_news_query_targets": list(explicit_news_query_targets[:8]),
        "cached_news_query_targets": list(cached_news_query_targets[:8]),
        "current_market_regime": current_market_regime,
        "cached_market_regime": cached_market_regime,
        "cache_age_sec": int(cache_age_sec) if cache_age_sec < 10**9 else None,
        "min_cache_age_sec": int(min_cache_age_sec),
        "readiness_threshold": float(readiness_threshold),
        "transition_readiness_score": readiness_score,
        "became_ready_this_cycle": bool(became_ready),
        "prior_intent_side": prior_intent,
        "prior_reason": prior_reason,
        "cache_source": str(cache_payload.get("source") or ""),
        "cached_output_present": bool(cached_output),
        "refresh_signal": signal,
        "reason": "",
    }
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return payload
    if _is_trueish(state.get("force_refresh_strategist")):
        payload["requested"] = True
        payload["refresh_signal"] = "force_refresh_requested"
        payload["reason"] = "commander_requested_refresh"
        return payload
    if not cached_output:
        payload["reason"] = "no_cached_strategist_output"
        return payload
    if not selected_symbol:
        payload["reason"] = "selected_symbol_missing"
        return payload
    if cache_age_sec < min_cache_age_sec:
        payload["reason"] = "cache_too_fresh_for_refresh"
        return payload
    if not signal:
        payload["reason"] = "no_pre_buy_refresh_signal"
        return payload
    payload["requested"] = True
    payload["reason"] = "commander_requested_refresh"
    return payload


def _should_use_cached_strategist_when_flat(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    enabled = _is_trueish(
        state.get("enable_cached_strategist_when_flat")
        if state.get("enable_cached_strategist_when_flat") is not None
        else os.getenv("COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED", "false")
    )
    open_position_count = _portfolio_open_position_count(state)
    cache_payload = _strategist_cache_payload(state)
    output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    generated_epoch = max(0, _coerce_int(cache_payload.get("generated_epoch"), 0))
    reuse_sec = max(0, _coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600"), 600))
    age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    payload = {
        "enabled": bool(enabled),
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "reason": "",
    }
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategist_refresh_requested = bool(commander_decision.get("strategist_refresh_requested"))
    strategist_refresh_context = (
        dict(commander_decision.get("strategist_refresh_context") or {})
        if isinstance(commander_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return False, payload
    if strategist_refresh_requested:
        payload.update({k: v for k, v in strategist_refresh_context.items() if k != "reason"})
        payload["source"] = "commander_decision"
        payload["refresh_signal"] = str(
            commander_decision.get("strategist_refresh_reason")
            or strategist_refresh_context.get("refresh_signal")
            or ""
        )
        payload["reason"] = "commander_requested_refresh"
        return False, payload
    if _is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return False, payload
    if not output:
        payload["reason"] = "no_cached_strategist_output"
        return False, payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return False, payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return False, payload
    payload["reason"] = "flat_position_cached_strategist"
    return True, payload


def _should_use_cached_strategist_from_commander_skip(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategist_invocation = str(commander_decision.get("strategist_invocation") or "").strip().upper()
    llm_policy = str(commander_decision.get("llm_policy") or "").strip().upper()
    open_position_count = _portfolio_open_position_count(state)
    cache_payload = _strategist_cache_payload(state)
    output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    generated_epoch = max(0, _coerce_int(cache_payload.get("generated_epoch"), 0))
    reuse_sec = max(0, _coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600"), 600))
    age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    payload = {
        "enabled": True,
        "source": "commander_decision",
        "strategist_invocation": strategist_invocation,
        "llm_policy": llm_policy,
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "reason": "",
    }
    strategist_refresh_requested = bool(commander_decision.get("strategist_refresh_requested"))
    strategist_refresh_context = (
        dict(commander_decision.get("strategist_refresh_context") or {})
        if isinstance(commander_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return False, payload
    if strategist_refresh_requested:
        payload.update({k: v for k, v in strategist_refresh_context.items() if k != "reason"})
        payload["refresh_signal"] = str(
            commander_decision.get("strategist_refresh_reason")
            or strategist_refresh_context.get("refresh_signal")
            or ""
        )
        payload["reason"] = "commander_requested_refresh"
        return False, payload
    if strategist_invocation != "SKIP":
        payload["reason"] = "commander_hint_not_skip"
        return False, payload
    if _is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return False, payload
    if not output:
        payload["reason"] = "no_cached_strategist_output"
        return False, payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return False, payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return False, payload
    payload["reason"] = "commander_skip_cached_strategist"
    return True, payload


def _run_integrated_chain(
    state: Dict[str, Any],
    *,
    execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a visible end-to-end chain inside canonical runtime."""
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
    from graphs.nodes.build_risk_context import build_risk_context
    from graphs.nodes.strategist_node import strategist_node
    from graphs.nodes.scanner_node import scanner_node
    from graphs.nodes.monitor_node import monitor_node
    from graphs.nodes.decision_node import decision_node
    from graphs.nodes.update_state_after_execution import update_state_after_execution
    from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts

    shadow_runtime = _ensure_commander_shadow_runtime(state)
    prior_cache_payload = _strategist_cache_payload(state)
    prior_cached_output = prior_cache_payload.get("output") if isinstance(prior_cache_payload.get("output"), dict) else {}
    _seed_commander_shadow_prior_context(
        state,
        prior_cached_output=prior_cached_output if isinstance(prior_cached_output, dict) else {},
    )
    shadow_runtime = _ensure_commander_shadow_runtime(state)

    # Keep integrated chain position/risk context aligned with live state.
    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="session")
    if not should_continue:
        return state
    state = build_risk_context(state)
    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value=str(state.get("path") or "integrated_chain_pending"),
        reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
    )

    use_monitor_only, fast_path_payload = _should_use_monitor_only_fast_path(state)
    if use_monitor_only:
        shadow_runtime["strategist_executed"] = False
        shadow_runtime["strategist_called"] = False
        shadow_runtime["llm_called_by_strategist"] = False
        shadow_runtime["used_cached_strategist"] = False
        state = _hydrate_strategist_output_cache(state)
        state = _attach_commander_applied_policy(state)
        state["commander_decision"] = _build_commander_decision(
            state,
            mode_value="integrated_chain",
            phase_value=str(state.get("runtime_phase") or "session"),
            status_value=str(state.get("runtime_status") or "planning"),
            path_value="integrated_chain_monitor_only",
            reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
        )
        held_symbols = _portfolio_open_position_symbols(state)
        if held_symbols:
            state["selected"] = {
                "symbol": held_symbols[0],
                "_monitor_synthetic_selected": True,
            }
        else:
            state.pop("selected", None)
        state.pop("scanner_output", None)
        state["runtime_fast_path"] = dict(fast_path_payload)
        _log_commander_event(state, "fast_path", {"path": "integrated_chain_monitor_only", **fast_path_payload})
        state = _hydrate_monitor_symbol_features(state)
        state = monitor_node(state)
        shadow_runtime["monitor_decision"] = str(((state.get("monitor_output") or {}).get("intent_side") or "NOOP"))
        state = decision_node(state)
        decision = str(state.get("decision") or "").strip().lower()
        if decision == "approve":
            intent = _intent_from_monitor_state(state)
            state["decision_packet"] = _build_packet_from_state(state, intent=intent)
            state = execute_fn(state)
            shadow_runtime["executor_action"] = str((((state.get("execution") or {}).get("order") or {}).get("action") or ((state.get("decision_packet") or {}).get("intent") or {}).get("action") or ""))
            shadow_runtime["executor_status"] = str(((state.get("execution") or {}).get("reason") or ((state.get("execution") or {}).get("ok_source") or "")))
            state = update_state_after_execution(state)
            try:
                state["intraday_trade_report"] = generate_intraday_trade_artifacts(state)
            except Exception as exc:
                state["intraday_trade_report"] = {
                    "ok": False,
                    "status": "failed",
                    "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
                }
        state["path"] = "integrated_chain_monitor_only"
        return state

    reused_strategist_cache, cache_payload = _should_use_cached_strategist_from_commander_skip(state)
    if not reused_strategist_cache and str(cache_payload.get("reason") or "").strip() != "commander_requested_refresh":
        reused_strategist_cache, cache_payload = _should_use_cached_strategist_when_flat(state)
    if reused_strategist_cache:
        shadow_runtime["strategist_executed"] = False
        shadow_runtime["strategist_called"] = False
        shadow_runtime["llm_called_by_strategist"] = False
        shadow_runtime["used_cached_strategist"] = True
        shadow_runtime["pre_buy_refresh_requested"] = False
        shadow_runtime["pre_buy_refresh_reason"] = ""
        shadow_runtime["pre_buy_refresh_context"] = {}
        shadow_runtime["market_changed"] = False
        shadow_runtime["repeated_same_context"] = True
        state = _hydrate_strategist_output_cache(state)
        state["runtime_fast_path"] = dict(cache_payload)
        _log_commander_event(state, "fast_path", {"path": "integrated_chain_cached_frame", **cache_payload})
    else:
        if str(cache_payload.get("reason") or "").strip() == "commander_requested_refresh":
            shadow_runtime["pre_buy_refresh_requested"] = True
            shadow_runtime["pre_buy_refresh_reason"] = str(
                cache_payload.get("refresh_signal")
                or cache_payload.get("strategist_refresh_reason")
                or cache_payload.get("reason")
                or ""
            )
            shadow_runtime["pre_buy_refresh_context"] = dict(cache_payload)
            _log_commander_event(state, "pre_buy_refresh", {"path": "integrated_chain", **cache_payload})
        else:
            shadow_runtime["pre_buy_refresh_requested"] = False
            shadow_runtime["pre_buy_refresh_reason"] = ""
            shadow_runtime["pre_buy_refresh_context"] = {}
        state = strategist_node(state)
        shadow_runtime["strategist_executed"] = True
        shadow_runtime["strategist_called"] = True
        shadow_runtime["used_cached_strategist"] = False
        strategist_llm = state.get("strategist_llm") if isinstance(state.get("strategist_llm"), dict) else {}
        llm_status = str(strategist_llm.get("status") or strategist_llm.get("llm_status") or "").strip().lower()
        shadow_runtime["llm_called_by_strategist"] = bool(
            llm_status not in {"", "disabled"}
            or str(strategist_llm.get("prompt_ref") or "").strip()
            or str(strategist_llm.get("response_ref") or "").strip()
        )
        shadow_runtime["retry_count_estimate"] = max(0, _coerce_int(strategist_llm.get("attempts"), 1) - 1)
        market_changed = _shadow_market_changed(prior_cached_output if isinstance(prior_cached_output, dict) else {}, state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {})
        shadow_runtime["market_changed"] = market_changed
        shadow_runtime["repeated_same_context"] = (market_changed is False)
        if _strategist_frame_blocked(state):
            return _apply_strategist_block(state, phase="integrated_chain")
        state = _persist_strategist_output_cache(state)
    state = _attach_commander_applied_policy(state)
    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value="integrated_chain_cached_frame" if reused_strategist_cache else "integrated_chain",
        reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
    )
    state = scanner_node(state)
    state = _hydrate_monitor_symbol_features(state)
    state = monitor_node(state)
    shadow_runtime["monitor_decision"] = str(((state.get("monitor_output") or {}).get("intent_side") or "NOOP"))
    state = decision_node(state)

    decision = str(state.get("decision") or "").strip().lower()
    if decision == "approve":
        intent = _intent_from_monitor_state(state)
        state["decision_packet"] = _build_packet_from_state(state, intent=intent)
        state = execute_fn(state)
        shadow_runtime["executor_action"] = str((((state.get("execution") or {}).get("order") or {}).get("action") or ((state.get("decision_packet") or {}).get("intent") or {}).get("action") or ""))
        shadow_runtime["executor_status"] = str(((state.get("execution") or {}).get("reason") or ((state.get("execution") or {}).get("ok_source") or "")))
        state = update_state_after_execution(state)
        try:
            state["intraday_trade_report"] = generate_intraday_trade_artifacts(state)
        except Exception as exc:
            state["intraday_trade_report"] = {
                "ok": False,
                "status": "failed",
                "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
            }

    state["path"] = "integrated_chain_cached_frame" if reused_strategist_cache else "integrated_chain"
    return state


def _run_preopen_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    """Warm strategist context before session without entering selection/execution paths."""
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
    from graphs.nodes.build_risk_context import build_risk_context
    from graphs.nodes.strategist_node import strategist_node

    state = build_portfolio_snapshot(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snaps or {}), "portfolio": state.get("portfolio_snapshot")}
    should_continue, state = _apply_portfolio_preflight_guard(state, phase="preopen")
    if not should_continue:
        return state
    state = build_risk_context(state)
    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value=str(state.get("runtime_mode") or "graph_spine"),
        phase_value="preopen",
        status_value=str(state.get("runtime_status") or "planning"),
        path_value=str(state.get("path") or "preopen_pending"),
        reason_text="",
    )
    state = strategist_node(state)
    if _strategist_frame_blocked(state):
        return _apply_strategist_block(state, phase="preopen")
    state = _attach_commander_applied_policy(state)
    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value=str(state.get("runtime_mode") or "graph_spine"),
        phase_value="preopen",
        status_value=str(state.get("runtime_status") or "planning"),
        path_value="preopen_strategist",
        reason_text="",
    )
    state = _persist_strategist_output_cache(state)
    state["path"] = "preopen_strategist"
    state["runtime_status"] = str(state.get("runtime_status") or "preopen_ready")
    return state


def _run_closeout_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep commander passive during closeout; reporting remains script-driven."""
    state["path"] = "closeout_idle"
    state["runtime_status"] = str(state.get("runtime_status") or "closeout_ready")
    return state


def resolve_runtime_mode(state: Dict[str, Any], *, mode: Optional[RuntimeMode] = None) -> RuntimeMode:
    """Resolve runtime mode with explicit precedence.

    Priority:
      1) explicit argument `mode`
      2) `state["runtime_mode"]`
      3) env `COMMANDER_RUNTIME_MODE`
      4) default `graph_spine`

    Safety guard:
      - decision_packet via state/env requires activation:
        state["allow_decision_packet_runtime"]=true OR
        env COMMANDER_RUNTIME_ALLOW_DECISION_PACKET=true
      - explicit `mode` bypasses this guard (caller-controlled override).
    """
    if mode is not None:
        return _normalize_mode(mode)

    allow_decision_packet = _is_trueish(state.get("allow_decision_packet_runtime")) or _is_trueish(
        os.getenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "")
    )

    if "runtime_mode" in state:
        selected = _normalize_mode(state.get("runtime_mode"))
        if selected == "decision_packet" and not allow_decision_packet:
            return "graph_spine"
        return selected
    env_mode = os.getenv("COMMANDER_RUNTIME_MODE", "")
    selected = _normalize_mode(env_mode or "graph_spine")
    if selected == "decision_packet" and not allow_decision_packet:
        return "graph_spine"
    return selected


def resolve_runtime_phase(state: Dict[str, Any], *, phase: Optional[RuntimePhase] = None) -> RuntimePhase:
    """Resolve runtime phase with explicit precedence."""
    if phase is not None:
        return _normalize_phase(phase)
    if "runtime_phase" in state:
        return _normalize_phase(state.get("runtime_phase"))
    return _normalize_phase(os.getenv("COMMANDER_RUNTIME_PHASE", "session"))


def run_commander_runtime(
    state: Dict[str, Any],
    *,
    mode: Optional[RuntimeMode] = None,
    phase: Optional[RuntimePhase] = None,
    graph_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    integrated_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    preopen_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    closeout_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    execute: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one canonical commander runtime step.

    Mode selection uses `resolve_runtime_mode(...)`.
    """
    state = ensure_runtime_resilience_state(state)
    _reset_commander_shadow_runtime(state)

    def _build_commander_decision_frame(
        mode_value: str,
        phase_value: str,
        *,
        status_value: str,
        path_value: str,
        reason_text: str = "",
    ) -> Dict[str, Any]:
        runtime_plan = state.get("runtime_plan") if isinstance(state.get("runtime_plan"), dict) else {}
        portfolio_snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
        strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
        return {
            "session_type": str(phase_value or ""),
            "market_clock_phase": str(phase_value or ""),
            "portfolio_state_summary": {
                "position_count": len(list(portfolio_snapshot.get("positions") or [])),
                "cash": portfolio_snapshot.get("cash"),
                "positions_source": str((state.get("portfolio_preflight") or {}).get("positions_source") if isinstance(state.get("portfolio_preflight"), dict) else ""),
                "preflight_status": str((state.get("portfolio_preflight") or {}).get("status") if isinstance(state.get("portfolio_preflight"), dict) else ""),
            },
            "market_regime_summary": {
                "market_regime": str(strategist_output.get("market_regime") or ""),
                "market_sentiment": str(strategist_output.get("market_sentiment") or ""),
                "playbook": str(strategist_output.get("playbook") or ""),
            },
            "goal": (
                "Execute full trading session flow."
                if str(phase_value or "").strip() == "session"
                else f"Run {str(phase_value or '').strip() or 'runtime'} phase safely."
            ),
            "agent_invocation_plan": list(runtime_plan.get("agents") or []),
            "decision_checkpoints": {
                "runtime_transition": str(state.get("runtime_transition") or ""),
                "runtime_status": str(status_value or state.get("runtime_status") or ""),
                "portfolio_preflight_status": str((state.get("portfolio_preflight") or {}).get("status") if isinstance(state.get("portfolio_preflight"), dict) else ""),
                "runtime_fast_path": dict(state.get("runtime_fast_path") or {}) if isinstance(state.get("runtime_fast_path"), dict) else {},
            },
            "final_runtime_path": str(path_value or ""),
            "final_reason": str(reason_text or state.get("runtime_status") or ""),
            "handoff_instruction": (
                "Proceed to downstream agents according to runtime plan."
                if str(status_value or "").strip().lower() in {"ok", "ready", "preopen_ready", "closeout_ready"}
                else "Do not proceed. Inspect commander/runtime status first."
            ),
            "mode": str(mode_value or ""),
        }

    def _persist_commander(mode_value: str, phase_value: str, *, status_value: str, path_value: str, reason: str = "") -> None:
        state["commander_decision"] = _build_commander_decision(
            state,
            mode_value=mode_value,
            phase_value=phase_value,
            status_value=status_value,
            path_value=path_value,
            reason_text=reason,
        )
        state["commander_decision_frame"] = _build_commander_decision_frame(
            mode_value,
            phase_value,
            status_value=status_value,
            path_value=path_value,
            reason_text=reason,
        )
        try:
            write_commander_artifact(
                state,
                mode=str(mode_value or ""),
                phase=str(phase_value or ""),
                path=str(path_value or ""),
                status=str(status_value or "ok"),
                reason=str(reason or ""),
            )
        except Exception:
            pass
        try:
            # Shadow commander is observation-only: it records recommendations and
            # explanations beside the live flow, but never overrides runtime behavior.
            shadow_path = write_commander_shadow_artifact(
                state,
                mode=str(mode_value or ""),
                phase=str(phase_value or ""),
                path=str(path_value or ""),
                status=str(status_value or "ok"),
                reason=str(reason or ""),
            )
            shadow_payload = state.get("commander_shadow_runtime") if isinstance(state.get("commander_shadow_runtime"), dict) else {}
            _log_commander_event(
                state,
                "shadow_assessment",
                {
                    "path": str(path_value or ""),
                    "artifact_path": str(shadow_path or ""),
                    "shadow_only": True,
                    "monitor_decision": str(shadow_payload.get("monitor_decision") or ""),
                    "executor_action": str(shadow_payload.get("executor_action") or ""),
                    **_commander_decision_event_meta(state),
                },
            )
        except Exception:
            pass
    selected = resolve_runtime_mode(state, mode=mode)
    selected_phase = resolve_runtime_phase(state, phase=phase)
    state["runtime_phase"] = selected_phase
    state = _annotate_runtime_plan(state, selected, selected_phase)
    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value=selected,
        phase_value=selected_phase,
        status_value=str(state.get("runtime_status") or "planning"),
        path_value=str(state.get("path") or "pending"),
        reason_text=str(state.get("runtime_transition") or ""),
    )
    _log_commander_event(
        state,
        "route",
        {
            "mode": selected,
            "phase": selected_phase,
            "agents": list(state.get("runtime_plan", {}).get("agents", [])),
            **_commander_decision_event_meta(state),
        },
    )

    should_run, state = _apply_runtime_transition(state)
    if state.get("runtime_transition"):
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "retry_count": state.get("runtime_retry_count"),
                **_commander_decision_event_meta(state),
            },
        )
    if not should_run:
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None, **_commander_decision_event_meta(state)},
        )
        _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "stopped") or "stopped"), path_value="")
        return state

    state, intervention_payload = _apply_operator_resume_intervention(state)
    if intervention_payload:
        _log_commander_event(state, "intervention", intervention_payload)

    should_run, state, cooldown_payload = _apply_commander_cooldown_guard(state)
    if not should_run:
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "reason": cooldown_payload.get("reason"),
                "cooldown_until_epoch": cooldown_payload.get("cooldown_until_epoch"),
                "incident_count": cooldown_payload.get("incident_count"),
                "incident_threshold": cooldown_payload.get("incident_threshold"),
                **_commander_decision_event_meta(state),
            },
        )
        _log_commander_event(state, "resilience", cooldown_payload)
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None, **_commander_decision_event_meta(state)},
        )
        _persist_commander(
            selected,
            selected_phase,
            status_value=str(state.get("runtime_status", "stopped") or "stopped"),
            path_value=str(state.get("path") or ""),
            reason=str(cooldown_payload.get("reason") or state.get("runtime_status") or ""),
        )
        return state

    graph_runner = graph_runner or run_trading_graph
    decide = decide or decide_trade
    execute = execute or execute_from_packet
    integrated_runner = integrated_runner or (lambda s: _run_integrated_chain(s, execute_fn=execute))
    preopen_runner = preopen_runner or _run_preopen_phase
    closeout_runner = closeout_runner or _run_closeout_phase

    try:
        if selected_phase == "preopen":
            state = preopen_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "preopen_ready"),
                    "path": state.get("path", "preopen_strategist"),
                    **_commander_decision_event_meta(state),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "preopen_ready") or "preopen_ready"), path_value=str(state.get("path", "preopen_strategist") or "preopen_strategist"))
            return state

        if selected_phase == "closeout":
            state = closeout_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "closeout_ready"),
                    "path": state.get("path", "closeout_idle"),
                    **_commander_decision_event_meta(state),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "closeout_ready") or "closeout_ready"), path_value=str(state.get("path", "closeout_idle") or "closeout_idle"))
            return state

        if selected == "decision_packet":
            state = decide(state)
            state = execute(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "ok"),
                    "path": "decision_packet",
                    **_commander_decision_event_meta(state),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value="decision_packet")
            return state

        if selected == "integrated_chain":
            state = integrated_runner(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "phase": selected_phase,
                    "status": state.get("runtime_status", "ok"),
                    "path": state.get("path", "integrated_chain"),
                    **_commander_decision_event_meta(state),
                    **_portfolio_guard_event_summary(state),
                    **_portfolio_preflight_event_summary(state),
                },
            )
            _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value=str(state.get("path", "integrated_chain") or "integrated_chain"))
            return state

        if _graph_spine_portfolio_preflight_enabled(state, phase=selected_phase):
            state = _run_graph_spine_with_preflight(state, graph_runner=graph_runner)
        else:
            state = graph_runner(state)
        _log_commander_event(
            state,
            "end",
            {
                "mode": selected,
                "phase": selected_phase,
                "status": state.get("runtime_status", "ok"),
                "path": state.get("path", "graph_spine"),
                **_commander_decision_event_meta(state),
                **_portfolio_guard_event_summary(state),
                **_portfolio_preflight_event_summary(state),
            },
        )
        _persist_commander(selected, selected_phase, status_value=str(state.get("runtime_status", "ok") or "ok"), path_value=str(state.get("path", "graph_spine") or "graph_spine"))
        return state
    except Exception as e:
        incident_payload = _register_commander_incident(state, error_type=type(e).__name__)
        state["runtime_status"] = "error"
        _log_commander_event(
            state,
            "error",
            {
                "mode": selected,
                "phase": selected_phase,
                "error_type": type(e).__name__,
                "error": str(e),
                **incident_payload,
            },
        )
        _persist_commander(selected, selected_phase, status_value="error", path_value=str(state.get("path") or ""), reason=str(e))
        raise
