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
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional, Tuple

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.contracts.agent_outputs import build_commander_shadow_artifact
from libs.runtime.decision_observability import build_commander_route_observability_surface
from libs.runtime.monitor_policy import (
    build_default_monitor_entry_policy,
    build_monitor_entry_policy_bundle,
    normalize_monitor_entry_policy,
)
from libs.llm.model_catalog import resolve_execution_profile, resolve_model_profile
from libs.runtime.scanner_bias import normalize_scanner_bias_context, summarize_scanner_bias_context
from libs.runtime.scanner_policy import normalize_scanner_source_type
from libs.runtime.canonical_artifacts import write_commander_artifact, write_commander_shadow_artifact
from libs.runtime.market_hours import MarketHours
from libs.runtime.resilience_state import ensure_runtime_resilience_state


RuntimeMode = Literal["graph_spine", "decision_packet", "integrated_chain"]
RuntimePhase = Literal["preopen", "session", "closeout"]


_PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC = 120
_PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD = 0.80
_OPEN_POSITION_STRATEGIST_REFRESH_COOLDOWN_SEC = 900
_COMMANDER_OWNED_POLICY_FIELDS = [
    "universe.asset_type",
    "reporter.ai_review.enabled",
    "reporter.trade_report.enabled",
    "reporter.trade_report.generate_on_open",
    "strategist.runtime.strict_mode",
    "strategist.runtime.allow_legacy_rule",
    "strategist.runtime.allow_legacy_strategy_v1",
    "strategist.memory_feedback.enabled",
    "strategist.reporter_feedback_mode",
    "commander.route.monitor_only_when_holding",
    "commander.route.cached_strategist_when_flat",
    "monitor.exit.enabled",
    "monitor.exit.eod_flat.enabled",
    "monitor.entry.block_buy_when_open_position",
    "monitor.entry.scoring.enabled",
    "monitor.entry.scoring.shadow_mode",
]
_COMMANDER_OWNED_UNIVERSE_POLICY_FIELDS = [
    "universe.asset_type",
]
_COMMANDER_OWNED_SCANNER_POLICY_FIELDS = [
    "scanner.source.type",
    "scanner.kiwoom.strict_only",
    "scanner.fallback.block_static_when_empty",
    "scanner.kiwoom.live_fetch",
    "scanner.kiwoom.include_change_rate",
]
_COMMANDER_OWNED_NUMERIC_POLICY_FIELDS = [
    "execution.cooldowns.post_exit_sec",
    "execution.cooldowns.sell_sec",
    "monitor.hold.min_hold_seconds",
    "monitor.exit.confirm_ticks",
    "monitor.exit.eod_flat.cutoff_min",
    "scanner.candidate.top_pool",
    "scanner.kiwoom.condition_limit",
    "monitor.entry.scoring.threshold",
    "strategist.memory_feedback.recent_runs",
]
_COMMANDER_OWNED_LLM_POLICY_FIELDS = [
    "llm.strategist.profile",
    "llm.reporter.intraday.profile",
    "llm.reporter.daily.profile",
]
_COMMANDER_OWNED_LLM_EXECUTION_POLICY_FIELDS = [
    "llm.execution_profile.profile_name",
    "llm.execution_profile.temperature",
    "llm.execution_profile.max_tokens",
    "llm.execution_profile.timeout_sec",
    "llm.execution_profile.retry.max_attempts",
    "llm.execution_profile.retry.backoff_sec",
    "llm.strategist.execution_profile.name",
    "llm.strategist.execution_profile.temperature",
    "llm.strategist.execution_profile.max_tokens",
    "llm.strategist.execution_profile.timeout_sec",
    "llm.strategist.execution_profile.retry_max",
    "llm.reporter.intraday.execution_profile.name",
    "llm.reporter.intraday.execution_profile.temperature",
    "llm.reporter.intraday.execution_profile.max_tokens",
    "llm.reporter.daily.execution_profile.name",
    "llm.reporter.daily.execution_profile.temperature",
    "llm.reporter.daily.execution_profile.max_tokens",
]


def _merge_nested_policy_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in dict(updates or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_nested_policy_dict(dict(out.get(key) or {}), value)
        else:
            out[key] = value
    return out


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


def _runtime_clock_dt_kst(state: Dict[str, Any], *, market_hours: MarketHours | None = None) -> datetime:
    mh = market_hours or MarketHours()
    epoch = _coerce_int(state.get("tick_ts"), 0)
    if epoch <= 0:
        epoch = _coerce_int(state.get("now_epoch"), 0)
    if epoch <= 0:
        epoch = int(time.time())
    return datetime.fromtimestamp(epoch, tz=mh.tz)


def _ensure_market_context_clock_fields(
    state: Dict[str, Any],
    *,
    market_hours: MarketHours | None = None,
) -> Dict[str, Any]:
    mh = market_hours or MarketHours()
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    out = dict(market_context or {})
    if out.get("minutes_to_close") not in (None, ""):
        state["market_context"] = out
        return out
    dt_kst = _runtime_clock_dt_kst(state, market_hours=mh)
    minutes_to_close: float | None = None
    if mh.is_open(dt_kst):
        close_dt = dt_kst.replace(
            hour=mh.close_time.hour,
            minute=mh.close_time.minute,
            second=0,
            microsecond=0,
        )
        minutes_to_close = max(0.0, (close_dt - dt_kst).total_seconds() / 60.0)
    out["minutes_to_close"] = minutes_to_close
    out.setdefault("market_clock_source", "runtime_clock")
    out.setdefault("market_clock_kst", dt_kst.isoformat())
    state["market_context"] = out
    return out


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
    route_observability = build_commander_route_observability_surface(
        selected_route=_derive_commander_selected_route(state),
        route_reason=str(
            commander_decision.get("decision_summary")
            or state.get("runtime_transition")
            or state.get("runtime_status")
            or ""
        ),
        commander_decision=commander_decision,
        runtime_fast_path=state.get("runtime_fast_path") if isinstance(state.get("runtime_fast_path"), dict) else {},
        resilience=state.get("runtime_resilience_state") if isinstance(state.get("runtime_resilience_state"), dict) else state.get("resilience"),
        runtime_status=state.get("runtime_status"),
        runtime_transition=state.get("runtime_transition"),
    )
    state["commander_route_observability"] = dict(route_observability)
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
        "route_observability": dict(route_observability),
        "strategist_invocation_mode": str(commander_decision.get("strategist_invocation_mode") or ""),
        "strategy_selection_mode": str(commander_decision.get("strategy_selection_mode") or ""),
        "strategy_state": str(commander_decision.get("strategy_state") or ""),
        "route_selected": str(route_observability.get("route_selected") or ""),
        "route_reason": str(route_observability.get("route_reason") or ""),
        "strategist_call_decision": str(route_observability.get("strategist_call_decision") or ""),
        "strategist_call_reason": str(route_observability.get("strategist_call_reason") or ""),
        "strategist_skip_reason": str(route_observability.get("strategist_skip_reason") or ""),
        "policy_refresh_reason": str(route_observability.get("policy_refresh_reason") or ""),
        "cache_hit": bool(route_observability.get("cache_hit")),
        "cache_age_sec": route_observability.get("cache_age_sec"),
        "applied_policy_source": str(route_observability.get("applied_policy_source") or ""),
        "applied_policy_id": str(route_observability.get("applied_policy_id") or ""),
        "monitor_only_reason": str(route_observability.get("monitor_only_reason") or ""),
        "full_cycle_reason": str(route_observability.get("full_cycle_reason") or ""),
        "resilience_state": dict(route_observability.get("resilience_state") or {}),
        "intervention_reason": str(route_observability.get("intervention_reason") or ""),
        "strategy_generation_mode": str(route_observability.get("strategy_generation_mode") or ""),
        "commander_applied_policy_summary": dict(state.get("commander_applied_policy_summary") or {}),
        "policy_sources": dict(
            (
                (state.get("applied_policy") or {}).get("policy_sources")
                if isinstance((state.get("applied_policy") or {}).get("policy_sources"), dict)
                else {}
            )
        ),
        "llm_execution_profile_source": "commander_applied_policy",
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


def _monitor_entry_policy_delta_fields(previous: Dict[str, Any], current: Dict[str, Any]) -> list[str]:
    before = dict(previous or {}) if isinstance(previous, dict) else {}
    after = dict(current or {}) if isinstance(current, dict) else {}
    ordered_keys: list[str] = []
    for key in list(before.keys()) + list(after.keys()):
        text = str(key or "").strip()
        if text and text not in ordered_keys:
            ordered_keys.append(text)
    return [key for key in ordered_keys if before.get(key) != after.get(key)]


def _compact_monitor_entry_state_for_refresh(entry_state: Dict[str, Any]) -> Dict[str, Any]:
    raw = dict(entry_state or {}) if isinstance(entry_state, dict) else {}
    blockers = [str(x) for x in list(raw.get("entry_blockers") or []) if str(x or "").strip()]
    return {
        "triggered": bool(raw.get("triggered")),
        "current_blocking_axis": str(raw.get("current_blocking_axis") or ""),
        "transition_readiness_score": raw.get("transition_readiness_score"),
        "entry_blockers": blockers[:6],
        "reclaim_distance_to_ready": raw.get("reclaim_distance_to_ready"),
        "volume_distance_to_ready": raw.get("volume_distance_to_ready"),
        "breakout_distance_to_ready": raw.get("breakout_distance_to_ready"),
        "vwap_reclaim_progress": raw.get("vwap_reclaim_progress"),
        "rebound_progress": raw.get("rebound_progress"),
        "volume_ratio": raw.get("volume_ratio"),
        "extended_from_vwap_pct": raw.get("extended_from_vwap_pct"),
        "breakout_gap_pct": raw.get("breakout_gap_pct"),
        "reclaim_gate_ok": bool(raw.get("reclaim_gate_ok")),
        "volume_ok": bool(raw.get("volume_ok")),
        "breakout_ok": bool(raw.get("breakout_ok")),
        "confidence_gate_ok": bool(raw.get("confidence_gate_ok")),
    }


def _build_open_position_strategist_refresh_context(override_assessment: Dict[str, Any]) -> Dict[str, Any]:
    assessment = dict(override_assessment or {}) if isinstance(override_assessment, dict) else {}
    positions = [dict(x) for x in list(assessment.get("positions") or []) if isinstance(x, dict)]
    selected_symbol = str(assessment.get("refresh_cooldown_symbol") or "").strip().upper()
    selected_position = next(
        (
            row
            for row in positions
            if str(row.get("symbol") or "").strip().upper() == selected_symbol
        ),
        positions[0] if positions else {},
    )
    entry_state = _compact_monitor_entry_state_for_refresh(selected_position.get("entry_state") or {})
    entry_blockers = [str(x) for x in list(entry_state.get("entry_blockers") or []) if str(x or "").strip()]
    summary = (
        f"Repeated hold refresh for {selected_symbol or 'unknown_symbol'} after "
        f"{int(selected_position.get('hold_repeat_count') or assessment.get('hold_repeat_count_max') or 0)} "
        f"consecutive hold cycles."
    )
    blocking_axis = str(entry_state.get("current_blocking_axis") or "")
    if blocking_axis:
        summary += f" Current blocking axis is {blocking_axis}."
    if entry_blockers:
        summary += f" Primary blockers: {', '.join(entry_blockers[:3])}."
    return {
        "refresh_scope": "open_position_monitor_refresh",
        "refresh_summary": summary,
        "selected_symbol": selected_symbol,
        "open_position_count": len(positions),
        "hold_repeat_count_max": int(assessment.get("hold_repeat_count_max") or 0),
        "selected_hold_repeat_count": int(selected_position.get("hold_repeat_count") or 0),
        "selected_effective_loss_ratio": selected_position.get("effective_loss_ratio"),
        "effective_loss_ratio_min": assessment.get("effective_loss_ratio_min"),
        "price_anomaly_flag": bool(assessment.get("price_anomaly_flag")),
        "monitor_posture": str(selected_position.get("posture") or ""),
        "monitor_reason": str(selected_position.get("reason") or ""),
        "active_exit_axis": str(selected_position.get("active_exit_axis") or ""),
        "position_qty": int(selected_position.get("qty") or 0),
        "position_age_seconds": selected_position.get("position_age_seconds"),
        "entry_state": dict(entry_state),
        "reason_chain": [str(x) for x in list(assessment.get("reason_chain") or []) if str(x or "").strip()][:8],
    }


def _summarize_monitor_entry_policy_from_strategist_output(strategist_output: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(strategist_output or {}) if isinstance(strategist_output, dict) else {}
    if not row:
        return {}
    temp_state = {"strategist_output": dict(row)}
    applied = dict((_resolve_commander_applied_policy(temp_state) or {}).get("applied_policy") or {})
    return _summarize_monitor_entry_policy(applied)


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


def _resolve_commander_reporter_feedback_policy(
    state: Dict[str, Any],
    *,
    selected_route: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    route = str(selected_route or _derive_commander_selected_route(state) or "").strip().lower()
    phase_text = str(phase or state.get("runtime_phase") or "session").strip().lower() or "session"

    if phase_text == "closeout":
        mode = "enabled"
        reason = "closeout_report_heavy"
    elif route == "monitor_only":
        mode = "disabled"
        reason = "monitor_only_route"
    elif route == "cached_strategist":
        mode = "disabled"
        reason = "cached_strategist_route"
    elif route == "full_cycle":
        mode = "auto"
        reason = "full_cycle_route"
    else:
        mode = "auto"
        reason = f"{phase_text}_default_auto"

    return {
        "reporter_feedback_mode": mode,
        "reporter_feedback_mode_source": "commander_applied_policy",
        "reporter_feedback_mode_reason": reason,
        "reporter_feedback_semantics": "advisory_only",
        "selected_route": route or "unknown",
        "runtime_phase": phase_text,
    }


def _resolve_commander_behavior_policy(
    state: Dict[str, Any],
    *,
    selected_route: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}

    def _existing_value(*path: str) -> Any:
        cursor: Any = applied_policy
        for key in path:
            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(key)
        return cursor

    route = str(selected_route or _derive_commander_selected_route(state) or "").strip().lower() or "unknown"
    phase_text = str(phase or state.get("runtime_phase") or "session").strip().lower() or "session"
    feedback_policy = _resolve_commander_reporter_feedback_policy(
        state,
        selected_route=route,
        phase=phase_text,
    )
    reporter_ai_review_enabled = _existing_value("reporter", "ai_review", "enabled")
    if reporter_ai_review_enabled is None:
        reporter_ai_review_enabled = False
    trade_report_enabled = _existing_value("reporter", "trade_report", "enabled")
    if trade_report_enabled is None:
        trade_report_enabled = True
    trade_report_generate_on_open = _existing_value("reporter", "trade_report", "generate_on_open")
    if trade_report_generate_on_open is None:
        trade_report_generate_on_open = False
    strict_mode = _existing_value("strategist", "runtime", "strict_mode")
    if strict_mode is None:
        strict_mode = True
    allow_legacy_rule = _existing_value("strategist", "runtime", "allow_legacy_rule")
    if allow_legacy_rule is None:
        allow_legacy_rule = False
    allow_legacy_strategy_v1 = _existing_value("strategist", "runtime", "allow_legacy_strategy_v1")
    if allow_legacy_strategy_v1 is None:
        allow_legacy_strategy_v1 = False
    memory_feedback_enabled = _existing_value("strategist", "memory_feedback", "enabled")
    if memory_feedback_enabled is None:
        memory_feedback_enabled = True
    monitor_only_when_holding = _existing_value("commander", "route", "monitor_only_when_holding")
    if monitor_only_when_holding is None:
        monitor_only_when_holding = True
    cached_strategist_when_flat = _existing_value("commander", "route", "cached_strategist_when_flat")
    if cached_strategist_when_flat is None:
        cached_strategist_when_flat = False
    exit_policy_enabled = _existing_value("monitor", "exit", "enabled")
    if exit_policy_enabled is None:
        exit_policy_enabled = True
    exit_policy_use_eod_flat = _existing_value("monitor", "exit", "eod_flat", "enabled")
    if exit_policy_use_eod_flat is None:
        exit_policy_use_eod_flat = True
    block_buy_when_open_position = _existing_value("monitor", "entry", "block_buy_when_open_position")
    if block_buy_when_open_position is None:
        block_buy_when_open_position = True
    monitor_scoring_enabled = _existing_value("monitor", "entry", "scoring", "enabled")
    if monitor_scoring_enabled is None:
        monitor_scoring_enabled = False
    monitor_scoring_shadow_mode = _existing_value("monitor", "entry", "scoring", "shadow_mode")
    if monitor_scoring_shadow_mode is None:
        monitor_scoring_shadow_mode = True
    post_exit_cooldown_sec = _existing_value("execution", "cooldowns", "post_exit_sec")
    if post_exit_cooldown_sec is None:
        post_exit_cooldown_sec = 180
    sell_cooldown_sec = _existing_value("execution", "cooldowns", "sell_sec")
    if sell_cooldown_sec is None:
        sell_cooldown_sec = 300
    min_hold_seconds = _existing_value("monitor", "hold", "min_hold_seconds")
    if min_hold_seconds is None:
        min_hold_seconds = 600
    exit_confirm_ticks = _existing_value("monitor", "exit", "confirm_ticks")
    if exit_confirm_ticks is None:
        exit_confirm_ticks = 2
    eod_flat_cutoff_min = _existing_value("monitor", "exit", "eod_flat", "cutoff_min")
    if eod_flat_cutoff_min is None:
        eod_flat_cutoff_min = 10
    top_candidate_pool = _existing_value("scanner", "candidate", "top_pool")
    if top_candidate_pool is None:
        top_candidate_pool = 30
    kiwoom_condition_limit = _existing_value("scanner", "kiwoom", "condition_limit")
    if kiwoom_condition_limit is None:
        kiwoom_condition_limit = 200
    scanner_source_type = _existing_value("scanner", "source", "type")
    if scanner_source_type in (None, ""):
        scanner_source_type = "kiwoom"
    scanner_strict_only = _existing_value("scanner", "kiwoom", "strict_only")
    if scanner_strict_only is None:
        scanner_strict_only = True
    scanner_strict_only = _is_trueish(scanner_strict_only)
    scanner_block_static_when_empty = _existing_value("scanner", "fallback", "block_static_when_empty")
    if scanner_block_static_when_empty is None:
        scanner_block_static_when_empty = True
    scanner_block_static_when_empty = _is_trueish(scanner_block_static_when_empty)
    scanner_live_fetch = _existing_value("scanner", "kiwoom", "live_fetch")
    if scanner_live_fetch is None:
        scanner_live_fetch = True
    scanner_live_fetch = _is_trueish(scanner_live_fetch)
    scanner_include_change_rate = _existing_value("scanner", "kiwoom", "include_change_rate")
    if scanner_include_change_rate is None:
        scanner_include_change_rate = True
    scanner_include_change_rate = _is_trueish(scanner_include_change_rate)
    universe_asset_type = _existing_value("universe", "asset_type")
    if universe_asset_type in (None, ""):
        universe_asset_type = "common_stock_only"
    monitor_scoring_threshold = _existing_value("monitor", "entry", "scoring", "threshold")
    if monitor_scoring_threshold is None:
        monitor_scoring_threshold = 3
    strategy_memory_recent_runs = _existing_value("strategist", "memory_feedback", "recent_runs")
    if strategy_memory_recent_runs is None:
        strategy_memory_recent_runs = 12
    strategist_llm_profile = str(_existing_value("llm", "strategist", "profile") or "balanced").strip().lower() or "balanced"
    reporter_intraday_profile = str(_existing_value("llm", "reporter", "intraday", "profile") or "fast_free").strip().lower() or "fast_free"
    reporter_daily_profile = str(_existing_value("llm", "reporter", "daily", "profile") or "strong_reasoning").strip().lower() or "strong_reasoning"
    strategist_llm = resolve_model_profile(strategist_llm_profile, default_profile="balanced")
    reporter_intraday_llm = resolve_model_profile(reporter_intraday_profile, default_profile="fast_free")
    reporter_daily_llm = resolve_model_profile(reporter_daily_profile, default_profile="strong_reasoning")
    default_execution_profile_name = (
        str(
            _existing_value("llm", "execution_profile", "profile_name")
            or _existing_value("llm", "execution_profile", "name")
            or "default_intraday"
        ).strip().lower()
        or "default_intraday"
    )
    default_execution_profile = resolve_execution_profile(
        default_execution_profile_name,
        default_profile="default_intraday",
        defaults={
            "profile_name": "default_intraday",
            "name": "default_intraday",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
            "retry_max": 2,
            "retry_backoff_sec": 0.0,
        },
    )
    strategist_execution_profile_name = (
        str(_existing_value("llm", "strategist", "execution_profile", "name") or "balanced_reasoning").strip().lower()
        or "balanced_reasoning"
    )
    reporter_intraday_execution_profile_name = (
        str(_existing_value("llm", "reporter", "intraday", "execution_profile", "name") or "concise_review").strip().lower()
        or "concise_review"
    )
    reporter_daily_execution_profile_name = (
        str(_existing_value("llm", "reporter", "daily", "execution_profile", "name") or "deep_review").strip().lower()
        or "deep_review"
    )
    strategist_execution_profile = resolve_execution_profile(
        strategist_execution_profile_name,
        default_profile="balanced_reasoning",
        defaults={
            "profile_name": "balanced_reasoning",
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {
                "max_attempts": int(((default_execution_profile.get("retry") or {}).get("max_attempts") or 2)),
                "backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
            },
            "retry_max": 2,
            "retry_backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
        },
    )
    reporter_intraday_execution_profile = resolve_execution_profile(
        reporter_intraday_execution_profile_name,
        default_profile="concise_review",
        defaults={
            "profile_name": "concise_review",
            "name": "concise_review",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": max(1, _coerce_int(default_execution_profile.get("timeout_sec"), 15)),
            "retry": {
                "max_attempts": int(((default_execution_profile.get("retry") or {}).get("max_attempts") or 2)),
                "backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
            },
            "retry_max": int(((default_execution_profile.get("retry") or {}).get("max_attempts") or 2)),
            "retry_backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
        },
    )
    reporter_daily_execution_profile = resolve_execution_profile(
        reporter_daily_execution_profile_name,
        default_profile="deep_review",
        defaults={
            "profile_name": "deep_review",
            "name": "deep_review",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": max(1, _coerce_int(default_execution_profile.get("timeout_sec"), 15)),
            "retry": {
                "max_attempts": int(((default_execution_profile.get("retry") or {}).get("max_attempts") or 2)),
                "backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
            },
            "retry_max": int(((default_execution_profile.get("retry") or {}).get("max_attempts") or 2)),
            "retry_backoff_sec": float(((default_execution_profile.get("retry") or {}).get("backoff_sec") or 0.0)),
        },
    )
    return {
        "execution": {
            "cooldowns": {
                "post_exit_sec": max(0, _coerce_int(post_exit_cooldown_sec, 180)),
                "sell_sec": max(0, _coerce_int(sell_cooldown_sec, 300)),
                "policy_source": "commander_applied_policy",
            },
        },
        "llm": {
            "execution_profile": {
                "profile_name": str(default_execution_profile.get("profile_name") or default_execution_profile.get("name") or "default_intraday"),
                "name": str(default_execution_profile.get("name") or "default_intraday"),
                "temperature": float(_runtime_float(default_execution_profile.get("temperature"), 0.2)),
                "max_tokens": max(256, _coerce_int(default_execution_profile.get("max_tokens"), 8192)),
                "timeout_sec": max(1, _coerce_int(default_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((default_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((default_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                    "retry_max": max(0, _coerce_int((default_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                    "retry_backoff_sec": max(0.0, float(_runtime_float((default_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    "policy_source": "commander_applied_policy",
                },
            "strategist": {
                "profile": str(strategist_llm.get("profile") or "balanced"),
                "primary": str(strategist_llm.get("primary") or ""),
                "fallback": str(strategist_llm.get("fallback") or ""),
                "execution_profile": {
                    "profile_name": str(strategist_execution_profile.get("profile_name") or strategist_execution_profile.get("name") or "balanced_reasoning"),
                    "name": str(strategist_execution_profile.get("name") or "balanced_reasoning"),
                    "temperature": float(_runtime_float(strategist_execution_profile.get("temperature"), 0.1)),
                    "max_tokens": max(256, _coerce_int(strategist_execution_profile.get("max_tokens"), 8192)),
                    "timeout_sec": max(1, _coerce_int(strategist_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((strategist_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((strategist_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                    "retry_max": max(0, _coerce_int(strategist_execution_profile.get("retry_max"), 2)),
                    "retry_backoff_sec": max(0.0, float(_runtime_float(strategist_execution_profile.get("retry_backoff_sec"), 0.0))),
                    "policy_source": "commander_applied_policy",
                },
                "policy_source": "commander_applied_policy",
            },
            "reporter": {
                "intraday": {
                    "profile": str(reporter_intraday_llm.get("profile") or "fast_free"),
                    "primary": str(reporter_intraday_llm.get("primary") or ""),
                    "fallback": str(reporter_intraday_llm.get("fallback") or ""),
                    "execution_profile": {
                        "profile_name": str(reporter_intraday_execution_profile.get("profile_name") or reporter_intraday_execution_profile.get("name") or "concise_review"),
                        "name": str(reporter_intraday_execution_profile.get("name") or "concise_review"),
                        "temperature": float(_runtime_float(reporter_intraday_execution_profile.get("temperature"), 0.2)),
                        "max_tokens": max(256, _coerce_int(reporter_intraday_execution_profile.get("max_tokens"), 8192)),
                        "timeout_sec": max(1, _coerce_int(reporter_intraday_execution_profile.get("timeout_sec"), 15)),
                        "retry": {
                            "max_attempts": max(0, _coerce_int((reporter_intraday_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                            "backoff_sec": max(0.0, float(_runtime_float((reporter_intraday_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                        },
                        "retry_max": max(0, _coerce_int(reporter_intraday_execution_profile.get("retry_max"), 2)),
                        "retry_backoff_sec": max(0.0, float(_runtime_float(reporter_intraday_execution_profile.get("retry_backoff_sec"), 0.0))),
                        "policy_source": "commander_applied_policy",
                    },
                    "policy_source": "commander_applied_policy",
                },
                "daily": {
                    "profile": str(reporter_daily_llm.get("profile") or "strong_reasoning"),
                    "primary": str(reporter_daily_llm.get("primary") or ""),
                    "fallback": str(reporter_daily_llm.get("fallback") or ""),
                    "execution_profile": {
                        "profile_name": str(reporter_daily_execution_profile.get("profile_name") or reporter_daily_execution_profile.get("name") or "deep_review"),
                        "name": str(reporter_daily_execution_profile.get("name") or "deep_review"),
                        "temperature": float(_runtime_float(reporter_daily_execution_profile.get("temperature"), 0.2)),
                        "max_tokens": max(256, _coerce_int(reporter_daily_execution_profile.get("max_tokens"), 8192)),
                        "timeout_sec": max(1, _coerce_int(reporter_daily_execution_profile.get("timeout_sec"), 15)),
                        "retry": {
                            "max_attempts": max(0, _coerce_int((reporter_daily_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                            "backoff_sec": max(0.0, float(_runtime_float((reporter_daily_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                        },
                        "retry_max": max(0, _coerce_int(reporter_daily_execution_profile.get("retry_max"), 2)),
                        "retry_backoff_sec": max(0.0, float(_runtime_float(reporter_daily_execution_profile.get("retry_backoff_sec"), 0.0))),
                        "policy_source": "commander_applied_policy",
                    },
                    "policy_source": "commander_applied_policy",
                },
            },
        },
        "reporter": {
            "ai_review": {
                "enabled": bool(reporter_ai_review_enabled),
                "policy_source": "commander_applied_policy",
            },
            "trade_report": {
                "enabled": bool(trade_report_enabled),
                "generate_on_open": bool(trade_report_generate_on_open),
                "policy_source": "commander_applied_policy",
            },
        },
        "strategist": {
            "runtime": {
                "strict_mode": bool(strict_mode),
                "allow_legacy_rule": bool(allow_legacy_rule),
                "allow_legacy_strategy_v1": bool(allow_legacy_strategy_v1),
                "policy_source": "commander_applied_policy",
            },
            "memory_feedback": {
                "enabled": bool(memory_feedback_enabled),
                "recent_runs": max(1, _coerce_int(strategy_memory_recent_runs, 12)),
                "policy_source": "commander_applied_policy",
            },
            "reporter_feedback_mode": str(feedback_policy.get("reporter_feedback_mode") or "auto"),
            "reporter_feedback_mode_source": str(
                feedback_policy.get("reporter_feedback_mode_source") or "commander_applied_policy"
            ),
            "reporter_feedback_mode_reason": str(feedback_policy.get("reporter_feedback_mode_reason") or ""),
            "reporter_feedback_semantics": "advisory_only",
        },
        "commander": {
            "route": {
                "monitor_only_when_holding": bool(monitor_only_when_holding),
                "cached_strategist_when_flat": bool(cached_strategist_when_flat),
                "policy_source": "commander_applied_policy",
            },
        },
        "universe": {
            "asset_type": str(universe_asset_type or "common_stock_only").strip().lower() or "common_stock_only",
            "policy_source": "commander_applied_policy",
        },
        "scanner": {
            "source": {
                "type": normalize_scanner_source_type(scanner_source_type),
                "policy_source": "commander_applied_policy",
            },
            "candidate": {
                "top_pool": max(1, _coerce_int(top_candidate_pool, 30)),
                "policy_source": "commander_applied_policy",
            },
            "kiwoom": {
                "condition_limit": max(0, _coerce_int(kiwoom_condition_limit, 200)),
                "strict_only": bool(scanner_strict_only),
                "live_fetch": bool(scanner_live_fetch),
                "include_change_rate": bool(scanner_include_change_rate),
                "policy_source": "commander_applied_policy",
            },
            "fallback": {
                "block_static_when_empty": bool(scanner_block_static_when_empty),
                "policy_source": "commander_applied_policy",
            },
        },
        "monitor": {
            "hold": {
                "min_hold_seconds": max(0, _coerce_int(min_hold_seconds, 600)),
                "policy_source": "commander_applied_policy",
            },
            "exit": {
                "enabled": bool(exit_policy_enabled),
                "confirm_ticks": max(1, _coerce_int(exit_confirm_ticks, 2)),
                "eod_flat": {
                    "enabled": bool(exit_policy_use_eod_flat),
                    "cutoff_min": max(0, _coerce_int(eod_flat_cutoff_min, 10)),
                },
                "policy_source": "commander_applied_policy",
            },
            "entry": {
                "block_buy_when_open_position": bool(block_buy_when_open_position),
                "scoring": {
                    "enabled": bool(monitor_scoring_enabled),
                    "shadow_mode": bool(monitor_scoring_shadow_mode),
                    "threshold": max(0.0, float(_runtime_float(monitor_scoring_threshold, 3.0))),
                    "entry_threshold": max(0.0, float(_runtime_float(monitor_scoring_threshold, 3.0))),
                    "policy_source": "commander_applied_policy",
                },
            },
        },
        "policy_sources": {
            "commander_owned_fields": list(_COMMANDER_OWNED_POLICY_FIELDS),
            "commander_owned_universe_fields": list(_COMMANDER_OWNED_UNIVERSE_POLICY_FIELDS),
            "commander_owned_scanner_fields": list(_COMMANDER_OWNED_SCANNER_POLICY_FIELDS),
            "commander_owned_numeric_fields": list(_COMMANDER_OWNED_NUMERIC_POLICY_FIELDS),
            "commander_owned_llm_fields": list(_COMMANDER_OWNED_LLM_POLICY_FIELDS),
            "commander_owned_llm_execution_fields": list(_COMMANDER_OWNED_LLM_EXECUTION_POLICY_FIELDS),
        },
        "commander_applied_policy_summary": {
            "selected_route": route,
            "runtime_phase": phase_text,
            "reporter_ai_review_enabled": bool(reporter_ai_review_enabled),
            "trade_report_enabled": bool(trade_report_enabled),
            "trade_report_generate_on_open": bool(trade_report_generate_on_open),
            "strategist_strict_mode": bool(strict_mode),
            "allow_legacy_rule": bool(allow_legacy_rule),
            "allow_legacy_strategy_v1": bool(allow_legacy_strategy_v1),
            "strategy_memory_feedback_enabled": bool(memory_feedback_enabled),
            "monitor_only_when_holding": bool(monitor_only_when_holding),
            "cached_strategist_when_flat": bool(cached_strategist_when_flat),
            "exit_policy_enabled": bool(exit_policy_enabled),
            "exit_policy_use_eod_flat": bool(exit_policy_use_eod_flat),
            "block_buy_when_open_position": bool(block_buy_when_open_position),
            "monitor_scoring_enabled": bool(monitor_scoring_enabled),
            "monitor_scoring_shadow_mode": bool(monitor_scoring_shadow_mode),
            "reporter_feedback_mode": str(feedback_policy.get("reporter_feedback_mode") or "auto"),
            "universe_fields": {
                "asset_type": str(universe_asset_type or "common_stock_only").strip().lower() or "common_stock_only",
            },
            "scanner_fields": {
                "source_type": normalize_scanner_source_type(scanner_source_type),
                "strict_only": bool(scanner_strict_only),
                "block_static_when_empty": bool(scanner_block_static_when_empty),
                "live_fetch": bool(scanner_live_fetch),
                "include_change_rate": bool(scanner_include_change_rate),
            },
            "llm_profiles": {
                "strategist": {
                    "profile": str(strategist_llm.get("profile") or "balanced"),
                    "primary": str(strategist_llm.get("primary") or ""),
                    "fallback": str(strategist_llm.get("fallback") or ""),
                },
                "reporter_intraday": {
                    "profile": str(reporter_intraday_llm.get("profile") or "fast_free"),
                    "primary": str(reporter_intraday_llm.get("primary") or ""),
                    "fallback": str(reporter_intraday_llm.get("fallback") or ""),
                },
                "reporter_daily": {
                    "profile": str(reporter_daily_llm.get("profile") or "strong_reasoning"),
                    "primary": str(reporter_daily_llm.get("primary") or ""),
                    "fallback": str(reporter_daily_llm.get("fallback") or ""),
                },
            },
            "llm_execution_profiles": {
                "default": {
                    "profile_name": str(default_execution_profile.get("profile_name") or default_execution_profile.get("name") or "default_intraday"),
                    "temperature": float(_runtime_float(default_execution_profile.get("temperature"), 0.2)),
                    "max_tokens": max(256, _coerce_int(default_execution_profile.get("max_tokens"), 8192)),
                    "timeout_sec": max(1, _coerce_int(default_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((default_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((default_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                },
                "strategist": {
                    "profile_name": str(strategist_execution_profile.get("profile_name") or strategist_execution_profile.get("name") or "balanced_reasoning"),
                    "temperature": float(_runtime_float(strategist_execution_profile.get("temperature"), 0.1)),
                    "max_tokens": max(256, _coerce_int(strategist_execution_profile.get("max_tokens"), 8192)),
                    "timeout_sec": max(1, _coerce_int(strategist_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((strategist_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((strategist_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                },
                "reporter_intraday": {
                    "profile_name": str(reporter_intraday_execution_profile.get("profile_name") or reporter_intraday_execution_profile.get("name") or "concise_review"),
                    "temperature": float(_runtime_float(reporter_intraday_execution_profile.get("temperature"), 0.2)),
                    "max_tokens": max(256, _coerce_int(reporter_intraday_execution_profile.get("max_tokens"), 8192)),
                    "timeout_sec": max(1, _coerce_int(reporter_intraday_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((reporter_intraday_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((reporter_intraday_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                },
                "reporter_daily": {
                    "profile_name": str(reporter_daily_execution_profile.get("profile_name") or reporter_daily_execution_profile.get("name") or "deep_review"),
                    "temperature": float(_runtime_float(reporter_daily_execution_profile.get("temperature"), 0.2)),
                    "max_tokens": max(256, _coerce_int(reporter_daily_execution_profile.get("max_tokens"), 8192)),
                    "timeout_sec": max(1, _coerce_int(reporter_daily_execution_profile.get("timeout_sec"), 15)),
                    "retry": {
                        "max_attempts": max(0, _coerce_int((reporter_daily_execution_profile.get("retry") or {}).get("max_attempts"), 2)),
                        "backoff_sec": max(0.0, float(_runtime_float((reporter_daily_execution_profile.get("retry") or {}).get("backoff_sec"), 0.0))),
                    },
                },
            },
            "numeric_fields": {
                "post_exit_cooldown_sec": max(0, _coerce_int(post_exit_cooldown_sec, 180)),
                "sell_cooldown_sec": max(0, _coerce_int(sell_cooldown_sec, 300)),
                "min_hold_seconds": max(0, _coerce_int(min_hold_seconds, 600)),
                "exit_confirm_ticks": max(1, _coerce_int(exit_confirm_ticks, 2)),
                "eod_flat_cutoff_min": max(0, _coerce_int(eod_flat_cutoff_min, 10)),
                "top_candidate_pool": max(1, _coerce_int(top_candidate_pool, 30)),
                "kiwoom_condition_limit": max(0, _coerce_int(kiwoom_condition_limit, 200)),
                "monitor_entry_scoring_threshold": max(0.0, float(_runtime_float(monitor_scoring_threshold, 3.0))),
                "strategy_memory_recent_runs": max(1, _coerce_int(strategy_memory_recent_runs, 12)),
            },
        },
    }


def _commander_trade_report_enabled(state: Dict[str, Any]) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    reporter = applied_policy.get("reporter") if isinstance(applied_policy.get("reporter"), dict) else {}
    trade_report = reporter.get("trade_report") if isinstance(reporter.get("trade_report"), dict) else {}
    enabled = trade_report.get("enabled")
    if enabled is None:
        return False
    return bool(enabled)


def _attach_commander_behavior_policy(
    state: Dict[str, Any],
    *,
    selected_route: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    behavior_policy = _resolve_commander_behavior_policy(
        state,
        selected_route=selected_route,
        phase=phase,
    )
    applied_policy = dict(state.get("applied_policy") or {}) if isinstance(state.get("applied_policy"), dict) else {}
    for section_name in ("execution", "llm", "reporter", "strategist", "commander", "scanner", "monitor", "universe", "policy_sources"):
        section_value = behavior_policy.get(section_name)
        if not isinstance(section_value, dict):
            continue
        existing = dict(applied_policy.get(section_name) or {}) if isinstance(applied_policy.get(section_name), dict) else {}
        applied_policy[section_name] = _merge_nested_policy_dict(existing, section_value)
    applied_policy["reporter_feedback_mode"] = str(
        ((behavior_policy.get("strategist") or {}).get("reporter_feedback_mode") or "auto")
    )
    applied_policy["reporter_feedback_mode_source"] = str(
        ((behavior_policy.get("strategist") or {}).get("reporter_feedback_mode_source") or "commander_applied_policy")
    )
    applied_policy["reporter_feedback_mode_reason"] = str(
        ((behavior_policy.get("strategist") or {}).get("reporter_feedback_mode_reason") or "")
    )
    state["applied_policy"] = applied_policy
    state["commander_behavior_policy"] = dict(behavior_policy)
    state["commander_applied_policy_summary"] = dict(behavior_policy.get("commander_applied_policy_summary") or {})
    return state


def _attach_commander_reporter_feedback_policy(
    state: Dict[str, Any],
    *,
    selected_route: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    feedback_policy = _resolve_commander_reporter_feedback_policy(
        state,
        selected_route=selected_route,
        phase=phase,
    )
    state = _attach_commander_behavior_policy(
        state,
        selected_route=selected_route,
        phase=phase,
    )
    state["commander_reporter_feedback_policy"] = dict(feedback_policy)
    return state


def _attach_commander_applied_policy(state: Dict[str, Any]) -> Dict[str, Any]:
    policy_meta = _resolve_commander_applied_policy(state)
    applied_policy = dict(policy_meta.get("applied_policy") or {})
    state["commander_applied_policy"] = dict(applied_policy)
    state["commander_applied_policy_meta"] = dict(policy_meta)
    state["monitor_entry_policy"] = dict(applied_policy)
    applied_policy_wrapper = dict(state.get("applied_policy") or {}) if isinstance(state.get("applied_policy"), dict) else {}
    strategist_policy = (
        dict(applied_policy_wrapper.get("strategist") or {})
        if isinstance(applied_policy_wrapper.get("strategist"), dict)
        else {}
    )
    merged_applied_policy = dict(applied_policy_wrapper)
    merged_applied_policy.update(applied_policy)
    if strategist_policy:
        merged_applied_policy["strategist"] = strategist_policy
    for section_name in ("execution", "llm", "reporter", "commander", "scanner", "monitor", "universe", "policy_sources"):
        section_value = applied_policy_wrapper.get(section_name)
        if isinstance(section_value, dict):
            merged_applied_policy[section_name] = dict(section_value)
    if applied_policy_wrapper.get("reporter_feedback_mode") not in (None, ""):
        merged_applied_policy["reporter_feedback_mode"] = applied_policy_wrapper.get("reporter_feedback_mode")
    if applied_policy_wrapper.get("reporter_feedback_mode_source") not in (None, ""):
        merged_applied_policy["reporter_feedback_mode_source"] = applied_policy_wrapper.get("reporter_feedback_mode_source")
    if applied_policy_wrapper.get("reporter_feedback_mode_reason") not in (None, ""):
        merged_applied_policy["reporter_feedback_mode_reason"] = applied_policy_wrapper.get("reporter_feedback_mode_reason")
    state["applied_policy"] = merged_applied_policy

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


def _resolve_commander_route_toggle(
    state: Dict[str, Any],
    *,
    nested_path: tuple[str, ...],
    state_key: str,
    default: bool,
) -> tuple[bool, str]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    cursor: Any = applied_policy
    for key in nested_path:
        if not isinstance(cursor, dict):
            cursor = None
            break
        cursor = cursor.get(key)
    if cursor is not None:
        return _is_trueish(cursor), "commander_applied_policy"
    if state.get(state_key) is not None:
        return _is_trueish(state.get(state_key)), "state_fallback"
    return bool(default), "default"


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
    reporter_feedback_policy = (
        dict(state.get("commander_reporter_feedback_policy") or {})
        if isinstance(state.get("commander_reporter_feedback_policy"), dict)
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
    commander_behavior_policy = (
        dict(state.get("commander_behavior_policy") or {})
        if isinstance(state.get("commander_behavior_policy"), dict)
        else {}
    )
    commander_override = (
        dict(state.get("commander_open_position_override") or {})
        if isinstance(state.get("commander_open_position_override"), dict)
        else {}
    )
    open_position_refresh_context = (
        dict(state.get("commander_open_position_refresh_context") or {})
        if isinstance(state.get("commander_open_position_refresh_context"), dict)
        else dict(commander_override.get("strategist_refresh_context") or {})
        if isinstance(commander_override.get("strategist_refresh_context"), dict)
        else {}
    )
    if str(commander_override.get("override_action") or "").strip().lower() == "strategist_refresh":
        strategist_refresh_requested = True
        strategist_refresh_reason = strategist_refresh_reason or str(
            commander_override.get("override_reason") or "repeated_hold_monitor_only"
        )
        strategist_refresh_context = {
            **strategist_refresh_context,
            **open_position_refresh_context,
        }
    commander_applied_policy_summary = dict(state.get("commander_applied_policy_summary") or {})
    policy_sources = (
        dict(applied_policy.get("policy_sources") or {})
        if isinstance(applied_policy.get("policy_sources"), dict)
        else dict(commander_behavior_policy.get("policy_sources") or {})
        if isinstance(commander_behavior_policy.get("policy_sources"), dict)
        else {}
    )

    decision_summary = (
        f"Commander set regime={market_regime}, session_bias={session_bias}, risk_mode={risk_mode}; "
        f"allowed_playbooks={', '.join(allowed_playbooks) if allowed_playbooks else 'none'}."
    )
    if shadow_reason_summary:
        decision_summary = shadow_reason_summary
    if reason_text:
        decision_summary = f"{decision_summary} Runtime note: {str(reason_text).strip()[:180]}"
    if bool(commander_override.get("override_triggered")):
        decision_summary = (
            f"{decision_summary} Commander override requested "
            f"{str(commander_override.get('override_action') or 'force_exit_review')} "
            f"because {str(commander_override.get('override_reason') or 'open_position_risk')}."
        )
    if strategist_refresh_requested:
        decision_summary = (
            f"{decision_summary} Commander requested fresh strategist context "
            f"before rebuilding the entry frame ({strategist_refresh_reason or 'strategy_refresh'})."
        )
        refresh_summary = str(open_position_refresh_context.get("refresh_summary") or "").strip()
        if refresh_summary:
            decision_summary = f"{decision_summary} {refresh_summary}"
    elif strategist_invocation == "SKIP" and strategist_cache_preferred:
        decision_summary = (
            f"{decision_summary} Commander preferred cached strategist context "
            f"for this cycle ({strategist_cache_preference_reason or 'context_reuse'})."
        )
        
    strategist_call_decision = strategist_invocation
    strategist_call_reason = strategist_refresh_reason if strategist_refresh_requested else ("normal_cycle" if strategist_invocation == "RUN" else "")
    strategist_skip_reason = strategist_cache_preference_reason if strategist_cache_preferred else ("open_positions_present" if open_position_count > 0 else "")

    # Task 2: Explicit Strategy Decision Rules
    cache_payload_for_state = _strategist_cache_payload(state)
    cached_output_for_state = cache_payload_for_state.get("output") if isinstance(cache_payload_for_state.get("output"), dict) else {}
    generated_epoch_for_state = max(0, _coerce_int(cache_payload_for_state.get("generated_epoch"), 0))
    now_epoch_for_state = _runtime_now_epoch(state)
    cache_age_sec_for_state = max(0, now_epoch_for_state - generated_epoch_for_state) if generated_epoch_for_state > 0 else 10**9
    reuse_sec_for_state = max(0, _coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600"), 600))
    is_cache_stale = cache_age_sec_for_state > reuse_sec_for_state

    if not cached_output_for_state:
        strategy_state = "INVALID"
    elif strategist_refresh_requested:
        strategy_state = "REBUILD_REQUIRED"
    elif is_cache_stale:
        strategy_state = "STALE"
    else:
        strategy_state = "ACTIVE"

    if _is_trueish(state.get("force_refresh_strategist")):
        strategy_selection_mode = "force_fresh"
    elif strategist_refresh_requested:
        strategy_selection_mode = "prefer_fresh"
    else:
        strategy_selection_mode = "prefer_cache"

    if open_position_count > 0:
        strategist_invocation_mode = "SKIP_MONITOR_ONLY"
    elif not cached_output_for_state:
        strategist_invocation_mode = "RUN"
    elif strategist_refresh_requested and is_cache_stale:
        strategist_invocation_mode = "RUN_REFRESH"
    elif strategist_refresh_requested and not is_cache_stale:
        strategist_invocation_mode = "SKIP_USE_CACHE"
    elif open_position_count == 0 and is_cache_stale:
        strategist_invocation_mode = "RUN"
    else:
        strategist_invocation_mode = "SKIP_USE_CACHE"

    # Task 4: Monitor feedback and adaptive policy
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    monitor_last_states = persisted.get("monitor_last_state_by_symbol") if isinstance(persisted.get("monitor_last_state_by_symbol"), dict) else {}
    
    recent_feedback = state.get("recent_strategy_feedback") if isinstance(state.get("recent_strategy_feedback"), dict) else {}
    recent_monitor_issues = list(recent_feedback.get("recent_monitor_issues") or [])
    
    blocker_counts = {}
    for issue in recent_monitor_issues:
        issue_str = str(issue).strip()
        if issue_str:
            blocker_counts[issue_str] = blocker_counts.get(issue_str, 0) + 1
            
    avg_distance = 0.0
    total_wait = 0
    near_ready_count = 0
    
    for sym, m_state in monitor_last_states.items():
        if not isinstance(m_state, dict): continue
        posture = str(m_state.get("posture") or "").upper()
        if posture in ("WAIT", "HOLD"):
            reason = str(m_state.get("reason") or "")
            if reason:
                blocker_counts[reason] = blocker_counts.get(reason, 0) + 1
                
            entry_state = m_state.get("entry_state") if isinstance(m_state.get("entry_state"), dict) else {}
            score = _runtime_float(entry_state.get("transition_readiness_score"), 0.0)
            if score > 0:
                avg_distance += score
                total_wait += 1
            if score >= 0.7:
                near_ready_count += 1
                
    dominant_blocker = ""
    blocker_count = 0
    if blocker_counts:
        dominant_blocker = max(blocker_counts, key=blocker_counts.get)
        blocker_count = blocker_counts[dominant_blocker]
        
    avg_distance_to_ready = avg_distance / total_wait if total_wait > 0 else 0.0
    near_ready_flag = near_ready_count > 0
    failure_streak = blocker_count
    
    injected_feedback = state.get("mock_monitor_feedback")
    if isinstance(injected_feedback, dict):
        dominant_blocker = injected_feedback.get("dominant_blocker", dominant_blocker)
        blocker_count = injected_feedback.get("blocker_count", blocker_count)
        failure_streak = injected_feedback.get("failure_streak", failure_streak)
        near_ready_flag = injected_feedback.get("near_ready_flag", near_ready_flag)
        avg_distance_to_ready = injected_feedback.get("avg_distance_to_ready", avg_distance_to_ready)

    monitor_feedback = {
        "dominant_blocker": str(dominant_blocker),
        "blocker_count": int(blocker_count),
        "failure_streak": int(failure_streak),
        "near_ready_flag": bool(near_ready_flag),
        "avg_distance_to_ready": float(avg_distance_to_ready),
    }

    adaptive_policy = {
        "entry_bias_adjustment": 0.0,
        "diversification_adjustment": 0.0,
        "reentry_penalty_adjustment": 0.0,
        "scan_aggressiveness": 0.0,
    }
    policy_adjustment_trace = []

    if monitor_feedback["dominant_blocker"] and monitor_feedback["failure_streak"] >= 3:
        adaptive_policy["entry_bias_adjustment"] += 0.02
        adaptive_policy["scan_aggressiveness"] += 0.05
        policy_adjustment_trace.append(f"failure_streak>={monitor_feedback['failure_streak']} for {monitor_feedback['dominant_blocker']} -> increased entry_bias_adjustment and scan_aggressiveness")

    if monitor_feedback["near_ready_flag"]:
        adaptive_policy["entry_bias_adjustment"] += 0.015
        adaptive_policy["reentry_penalty_adjustment"] -= 0.02
        policy_adjustment_trace.append("near_ready_flag=True -> increased entry_bias_adjustment, decreased reentry_penalty_adjustment")

    if monitor_feedback["failure_streak"] >= 5:
        adaptive_policy["diversification_adjustment"] += 0.03
        policy_adjustment_trace.append(f"failure_streak>={monitor_feedback['failure_streak']} -> increased diversification_adjustment")

    scanner_policy = {
        "avoid_recent_symbol": False,
        "recent_symbol_penalty": round(max(0.0, 0.05 + adaptive_policy["reentry_penalty_adjustment"]), 6),
        "diversification_bias": round(max(0.0, 0.02 + adaptive_policy["diversification_adjustment"]), 6),
        "entry_bias_cap": round(max(0.0, 0.0 + adaptive_policy["entry_bias_adjustment"]), 6),
        "allow_same_symbol_reentry": True,
        "reentry_score_gap_threshold": 0.03,
    }
    shadow_runtime = _ensure_commander_shadow_runtime(state)
    prior_context = dict(shadow_runtime.get("prior_context") or {}) if isinstance(shadow_runtime.get("prior_context"), dict) else {}
    prior_monitor_entry_policy_summary = (
        dict(prior_context.get("monitor_entry_policy_summary") or {})
        if isinstance(prior_context.get("monitor_entry_policy_summary"), dict)
        else {}
    )
    current_monitor_entry_policy_summary = dict(
        applied_policy_meta.get("monitor_entry_policy_summary")
        or _summarize_monitor_entry_policy(applied_policy)
        or {}
    )
    if (
        strategist_refresh_requested
        and open_position_refresh_context
        and not current_monitor_entry_policy_summary
        and prior_monitor_entry_policy_summary
    ):
        current_monitor_entry_policy_summary = dict(prior_monitor_entry_policy_summary)
    strategist_refresh_evaluated = bool(
        str(commander_override.get("override_action") or "").strip().lower() == "strategist_refresh"
        or strategist_invocation == "RUN_REFRESH"
    )
    strategist_refresh_policy_delta_fields = (
        _monitor_entry_policy_delta_fields(
            prior_monitor_entry_policy_summary,
            current_monitor_entry_policy_summary,
        )
        if strategist_refresh_evaluated
        else []
    )
    if strategist_refresh_requested:
        strategist_refresh_context = {
            **dict(strategist_refresh_context or {}),
            "prior_monitor_entry_policy_summary": dict(prior_monitor_entry_policy_summary),
            "current_monitor_entry_policy_summary": dict(current_monitor_entry_policy_summary),
        }
    strategist_refresh_effective = bool(
        strategist_refresh_evaluated and bool(strategist_refresh_policy_delta_fields)
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
        "scanner_policy": dict(scanner_policy),
        "monitor_feedback": dict(monitor_feedback),
        "adaptive_policy": dict(adaptive_policy),
        "policy_adjustment_trace": list(policy_adjustment_trace),
        "command_intent": command_intent,
        "strategist_invocation": strategist_invocation,
        "strategist_invocation_mode": strategist_invocation_mode,
        "strategy_selection_mode": strategy_selection_mode,
        "strategy_state": strategy_state,
        "strategist_call_decision": strategist_call_decision,
        "strategist_call_reason": strategist_call_reason,
        "strategist_skip_reason": strategist_skip_reason,
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
        "strategist_refresh_context": dict(strategist_refresh_context),
        "open_position_refresh_context": dict(open_position_refresh_context),
        "strategist_refresh_evaluated": strategist_refresh_evaluated,
        "strategist_refresh_effective": strategist_refresh_effective,
        "strategist_refresh_policy_delta_fields": list(strategist_refresh_policy_delta_fields),
        "strategist_refresh_policy_delta_count": int(len(strategist_refresh_policy_delta_fields)),
        "prior_monitor_entry_policy_summary": dict(prior_monitor_entry_policy_summary),
        "current_monitor_entry_policy_summary": dict(current_monitor_entry_policy_summary),
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
        "override_triggered": bool(commander_override.get("override_triggered")),
        "override_reason": str(
            commander_override.get("override_reason")
            or applied_policy_meta.get("override_reason")
            or ""
        ),
        "override_action": str(commander_override.get("override_action") or ""),
        "override_context": dict(commander_override),
        "applied_policy_source_chain": list(applied_policy_meta.get("applied_policy_source_chain") or []),
        "commander_applied_policy_summary": dict(commander_applied_policy_summary),
        "policy_sources": dict(policy_sources),
        "strategist_runtime_policy_source": "commander_applied_policy",
        "llm_policy_source": "commander_applied_policy",
        "llm_execution_profile_source": "commander_applied_policy",
        "reporter_policy_source": "commander_applied_policy",
        "monitor_policy_source": "commander_applied_policy",
        "scanner_policy_source": "commander_applied_policy",
        "execution_policy_source": "commander_applied_policy",
        "reporter_feedback_mode": str(reporter_feedback_policy.get("reporter_feedback_mode") or "auto"),
        "reporter_feedback_mode_source": str(reporter_feedback_policy.get("reporter_feedback_mode_source") or "default_auto"),
        "reporter_feedback_mode_reason": str(reporter_feedback_policy.get("reporter_feedback_mode_reason") or ""),
        "reporter_feedback_semantics": "advisory_only",
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
        "monitor_entry_policy_summary": _summarize_monitor_entry_policy_from_strategist_output(baseline_output),
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


def _derive_commander_selected_route(state: Dict[str, Any]) -> str:
    status_text = str(state.get("runtime_status") or "").strip()
    path_text = str(state.get("path") or "").strip()
    phase_text = str(state.get("runtime_phase") or "").strip()
    if "monitor_only" in path_text:
        return "monitor_only"
    if "cached" in path_text:
        return "cached_strategist"
    if phase_text == "preopen" or "preopen" in path_text:
        return "preopen"
    if phase_text == "closeout" or "closeout" in path_text:
        return "closeout"
    if "blocked" in path_text or status_text in {"blocked", "preflight_blocked"}:
        return "blocked"
    if status_text in {"error", "cooldown_wait", "degraded"}:
        return "degraded"
    return "full_cycle"


def _normalize_reporter_integration_config(state: Dict[str, Any]) -> Dict[str, Any]:
    config = state.get("reporter_integration") if isinstance(state.get("reporter_integration"), dict) else {}
    hooks = config.get("hooks") if isinstance(config.get("hooks"), dict) else {}
    return {
        "enabled": _is_trueish(config.get("enabled")),
        "emit_reports": _is_trueish(config.get("emit_reports")),
        "hooks": dict(hooks),
        "event_log_path": str(config.get("event_log_path") or state.get("event_log_path") or "data/logs/events.jsonl"),
        "reports_root": str(config.get("reports_root") or state.get("reports_root") or "reports"),
        "day": str(config.get("day") or state.get("day") or ""),
    }


def _reporter_hook_requested(config: Dict[str, Any], hook_name: str, *, default: bool = False) -> bool:
    hooks = config.get("hooks") if isinstance(config.get("hooks"), dict) else {}
    if hook_name in hooks:
        return _is_trueish(hooks.get(hook_name))
    direct_key = f"{hook_name}_enabled"
    if direct_key in config:
        return _is_trueish(config.get(direct_key))
    return bool(default)


def _resolve_reporter_agent(state: Dict[str, Any]) -> Any:
    injected = state.get("reporter_agent") or state.get("reporter")
    if injected is not None:
        return injected
    from libs.agent.reporter import Reporter

    return Reporter()


def _invoke_reporter_hook(
    state: Dict[str, Any],
    *,
    hook_name: str,
    hook_fn: Callable[..., Dict[str, Any]],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        result = hook_fn(
            enabled=True,
            emit_reports=bool(config.get("emit_reports")),
            event_log_path=str(config.get("event_log_path") or "data/logs/events.jsonl"),
            reports_root=str(config.get("reports_root") or "reports"),
            day=str(config.get("day") or ""),
        )
    except TypeError:
        # Some hook placeholders intentionally accept a smaller surface.
        result = hook_fn(
            enabled=True,
            day=str(config.get("day") or ""),
            reports_root=str(config.get("reports_root") or "reports"),
        )
    except Exception as exc:
        return {
            "hook_name": hook_name,
            "enabled": True,
            "status": "failed",
            "executed": False,
            "reason": f"hook_exception:{type(exc).__name__}",
            "report_only": True,
            "execution_authority": False,
            "route_override_authority": False,
            "threshold_override_authority": False,
            "warnings": [str(exc)],
        }
    return dict(result or {})


def _maybe_run_reporter_hooks(
    state: Dict[str, Any],
    *,
    mode_value: str,
    phase_value: str,
) -> Dict[str, Any]:
    config = _normalize_reporter_integration_config(state)
    if not bool(config.get("enabled")):
        return state

    reporter = _resolve_reporter_agent(state)
    requested_hooks: list[tuple[str, Callable[..., Dict[str, Any]]]] = []
    if str(phase_value or "").strip() == "session":
        if _reporter_hook_requested(config, "intraday_summary", default=True):
            requested_hooks.append(("intraday_summary", reporter.maybe_generate_intraday_summary))
    elif str(phase_value or "").strip() == "closeout":
        if _reporter_hook_requested(config, "eod_reports", default=True):
            requested_hooks.append(("eod_reports", reporter.maybe_generate_eod_reports))
        if _reporter_hook_requested(config, "strategist_feedback", default=True):
            requested_hooks.append(("strategist_feedback", reporter.maybe_generate_strategist_feedback))

    if not requested_hooks:
        return state

    results: Dict[str, Any] = {}
    for hook_name, hook_fn in requested_hooks:
        hook_result = _invoke_reporter_hook(state, hook_name=hook_name, hook_fn=hook_fn, config=config)
        hook_result.setdefault("hook_name", hook_name)
        hook_result.setdefault("report_only", True)
        hook_result.setdefault("execution_authority", False)
        hook_result.setdefault("route_override_authority", False)
        hook_result.setdefault("threshold_override_authority", False)
        hook_result.setdefault("mode", str(mode_value or ""))
        hook_result.setdefault("phase", str(phase_value or ""))
        results[hook_name] = hook_result
        _log_commander_event(
            state,
            "reporter_hook",
            {
                "hook_name": hook_name,
                "mode": str(mode_value or ""),
                "phase": str(phase_value or ""),
                "status": str(hook_result.get("status") or ""),
                "executed": bool(hook_result.get("executed")),
                "report_only": True,
                "execution_authority": False,
                "route_override_authority": False,
                "threshold_override_authority": False,
            },
        )

    state["reporter_hook_results"] = results
    state["reporter_hook_summary"] = {
        "enabled": True,
        "mode": str(mode_value or ""),
        "phase": str(phase_value or ""),
        "requested_hooks": [name for name, _ in requested_hooks],
        "emit_reports": bool(config.get("emit_reports")),
        "report_only": True,
        "execution_authority": False,
        "route_override_authority": False,
        "threshold_override_authority": False,
    }
    return state


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


def _normalize_position_ratio(value: Any) -> float | None:
    if value in (None, ""):
        return None
    ratio = _runtime_float(value, 0.0)
    return float(ratio)


def _assess_open_position_commander_override(state: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    monitor_last_state = (
        persisted.get("monitor_last_state_by_symbol")
        if isinstance(persisted.get("monitor_last_state_by_symbol"), dict)
        else {}
    )
    prior_hold_counts = (
        persisted.get("commander_open_position_hold_repeat_by_symbol")
        if isinstance(persisted.get("commander_open_position_hold_repeat_by_symbol"), dict)
        else {}
    )
    prior_refresh_cooldowns = (
        persisted.get("commander_open_position_refresh_cooldown_until_by_symbol")
        if isinstance(persisted.get("commander_open_position_refresh_cooldown_until_by_symbol"), dict)
        else {}
    )

    next_hold_counts: Dict[str, int] = {}
    next_refresh_cooldowns: Dict[str, int] = {}
    reasons: list[str] = []
    rows_summary: list[Dict[str, Any]] = []
    repeated_hold_rows: list[Dict[str, Any]] = []
    anomaly_found = False
    risk_found = False
    max_hold_repeat = 0
    min_effective_loss_ratio: float | None = None
    now_epoch = _runtime_now_epoch(state)

    for row in rows:
        if not isinstance(row, dict):
            continue
        qty = max(0, _coerce_int(row.get("qty"), 0))
        if qty <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        avg_price = _runtime_float(row.get("avg_price"), 0.0)
        current_price = _runtime_float(
            row.get("current_price")
            if row.get("current_price") not in (None, "")
            else row.get("price"),
            0.0,
        )
        unrealized_pnl = _runtime_float(row.get("unrealized_pnl"), 0.0)
        account_pnl_ratio = _normalize_position_ratio(row.get("account_pnl_ratio"))
        account_mark_price = 0.0
        price_anomaly = False
        price_anomaly_reason = ""
        if account_pnl_ratio is not None and avg_price > 0.0:
            account_mark_price = float(avg_price * (1.0 + float(account_pnl_ratio)))
            if current_price > 0.0 and account_mark_price > 0.0:
                mark_ratio = float(account_mark_price / current_price)
                if mark_ratio < 0.5:
                    price_anomaly = True
                    price_anomaly_reason = f"account_mark_below_reference_ratio:{mark_ratio:.4f}"
                elif mark_ratio > 1.5:
                    price_anomaly = True
                    price_anomaly_reason = f"account_mark_above_reference_ratio:{mark_ratio:.4f}"

        raw_loss_ratio = (
            float((current_price / avg_price) - 1.0)
            if current_price > 0.0 and avg_price > 0.0
            else None
        )
        unrealized_loss_ratio = (
            float(unrealized_pnl / float(avg_price * qty))
            if avg_price > 0.0 and qty > 0
            else None
        )
        candidate_loss_ratios = [x for x in (raw_loss_ratio, unrealized_loss_ratio) if x is not None]
        if account_pnl_ratio is not None and not price_anomaly:
            candidate_loss_ratios.append(float(account_pnl_ratio))
        effective_loss_ratio = min(candidate_loss_ratios) if candidate_loss_ratios else None

        previous = monitor_last_state.get(symbol) if isinstance(monitor_last_state, dict) else {}
        previous_posture = str((previous or {}).get("posture") or "").strip().lower()
        hold_repeat_count = max(0, _coerce_int(prior_hold_counts.get(symbol), 0))
        if previous_posture == "hold":
            hold_repeat_count += 1
        else:
            hold_repeat_count = 0
        next_hold_counts[symbol] = int(hold_repeat_count)
        max_hold_repeat = max(max_hold_repeat, int(hold_repeat_count))
        refresh_cooldown_until = max(0, _coerce_int(prior_refresh_cooldowns.get(symbol), 0))
        if refresh_cooldown_until > now_epoch:
            next_refresh_cooldowns[symbol] = int(refresh_cooldown_until)

        if effective_loss_ratio is not None:
            min_effective_loss_ratio = (
                float(effective_loss_ratio)
                if min_effective_loss_ratio is None
                else min(float(min_effective_loss_ratio), float(effective_loss_ratio))
            )

        if price_anomaly:
            anomaly_found = True
            reasons.append(f"{symbol}:price_anomaly:{price_anomaly_reason}")
        if effective_loss_ratio is not None and effective_loss_ratio <= -0.01:
            risk_found = True
            reasons.append(f"{symbol}:loss_threshold:{effective_loss_ratio:.4f}")
        if hold_repeat_count >= 3:
            reasons.append(f"{symbol}:hold_repeat:{hold_repeat_count}")
            repeated_hold_rows.append(
                {
                    "symbol": symbol,
                    "hold_repeat_count": int(hold_repeat_count),
                    "refresh_cooldown_until": int(refresh_cooldown_until) if refresh_cooldown_until > 0 else 0,
                    "refresh_cooldown_remaining_sec": max(0, int(refresh_cooldown_until - now_epoch))
                    if refresh_cooldown_until > now_epoch
                    else 0,
                }
            )

        rows_summary.append(
            {
                "symbol": symbol,
                "qty": int(qty),
                "effective_loss_ratio": effective_loss_ratio,
                "raw_loss_ratio": raw_loss_ratio,
                "account_pnl_ratio": account_pnl_ratio,
                "price_anomaly": bool(price_anomaly),
                "price_anomaly_reason": str(price_anomaly_reason),
                "hold_repeat_count": int(hold_repeat_count),
                "posture": str(previous_posture or ""),
                "reason": str((previous or {}).get("reason") or ""),
                "active_exit_axis": str((previous or {}).get("active_exit_axis") or ""),
                "entry_state": _compact_monitor_entry_state_for_refresh((previous or {}).get("entry_state") or {}),
                "position_age_seconds": row.get("position_age_seconds"),
                "refresh_cooldown_until": int(refresh_cooldown_until) if refresh_cooldown_until > 0 else None,
                "refresh_cooldown_remaining_sec": max(0, int(refresh_cooldown_until - now_epoch))
                if refresh_cooldown_until > now_epoch
                else 0,
            }
        )

    if next_hold_counts:
        persisted["commander_open_position_hold_repeat_by_symbol"] = dict(next_hold_counts)
    elif "commander_open_position_hold_repeat_by_symbol" in persisted:
        persisted.pop("commander_open_position_hold_repeat_by_symbol", None)

    override_triggered = bool(anomaly_found or risk_found or max_hold_repeat >= 3)
    override_action = ""
    override_reason = ""
    override_suppressed = False
    override_suppressed_reason = ""
    refresh_cooldown_symbol = ""
    refresh_cooldown_until = 0
    refresh_cooldown_remaining_sec = 0
    strategist_refresh_context: Dict[str, Any] = {}
    if override_triggered:
        if anomaly_found:
            override_action = "force_exit_review"
            override_reason = "price_pnl_anomaly"
        elif risk_found:
            override_action = "force_exit_review"
            override_reason = "loss_threshold_exceeded"
        else:
            repeated_hold_rows = sorted(
                repeated_hold_rows,
                key=lambda item: (
                    -_coerce_int(item.get("hold_repeat_count"), 0),
                    str(item.get("symbol") or ""),
                ),
            )
            selected_row = repeated_hold_rows[0] if repeated_hold_rows else {}
            refresh_cooldown_symbol = str(selected_row.get("symbol") or "")
            refresh_cooldown_until = max(0, _coerce_int(selected_row.get("refresh_cooldown_until"), 0))
            if refresh_cooldown_until > now_epoch:
                override_triggered = False
                override_suppressed = True
                override_suppressed_reason = "repeated_hold_monitor_only_refresh_cooldown"
                refresh_cooldown_remaining_sec = max(0, int(refresh_cooldown_until - now_epoch))
                reasons.append(
                    f"{refresh_cooldown_symbol}:refresh_cooldown_active:{refresh_cooldown_remaining_sec}"
                )
            else:
                override_action = "strategist_refresh"
                override_reason = "repeated_hold_monitor_only"
                refresh_cooldown_until = int(now_epoch + _OPEN_POSITION_STRATEGIST_REFRESH_COOLDOWN_SEC)
                refresh_cooldown_remaining_sec = int(_OPEN_POSITION_STRATEGIST_REFRESH_COOLDOWN_SEC)
                if refresh_cooldown_symbol:
                    next_refresh_cooldowns[refresh_cooldown_symbol] = int(refresh_cooldown_until)
                strategist_refresh_context = _build_open_position_strategist_refresh_context(
                    {
                        "refresh_cooldown_symbol": refresh_cooldown_symbol,
                        "hold_repeat_count_max": max_hold_repeat,
                        "effective_loss_ratio_min": min_effective_loss_ratio,
                        "price_anomaly_flag": anomaly_found,
                        "reason_chain": list(reasons),
                        "positions": rows_summary,
                    }
                )

    if next_refresh_cooldowns:
        persisted["commander_open_position_refresh_cooldown_until_by_symbol"] = dict(next_refresh_cooldowns)
    elif "commander_open_position_refresh_cooldown_until_by_symbol" in persisted:
        persisted.pop("commander_open_position_refresh_cooldown_until_by_symbol", None)
    state["persisted_state"] = persisted

    return {
        "override_triggered": bool(override_triggered),
        "override_reason": str(override_reason),
        "override_action": str(override_action),
        "override_suppressed": bool(override_suppressed),
        "override_suppressed_reason": str(override_suppressed_reason),
        "reason_chain": list(reasons[:8]),
        "hold_repeat_count_max": int(max_hold_repeat),
        "effective_loss_ratio_min": min_effective_loss_ratio,
        "price_anomaly_flag": bool(anomaly_found),
        "refresh_cooldown_sec": int(_OPEN_POSITION_STRATEGIST_REFRESH_COOLDOWN_SEC),
        "refresh_cooldown_symbol": str(refresh_cooldown_symbol),
        "refresh_cooldown_until": int(refresh_cooldown_until) if refresh_cooldown_until > 0 else None,
        "refresh_cooldown_remaining_sec": int(refresh_cooldown_remaining_sec),
        "strategist_refresh_context": dict(strategist_refresh_context),
        "policy_source": "commander_open_position_override",
        "positions": rows_summary,
    }


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
    enabled, policy_source = _resolve_commander_route_toggle(
        state,
        nested_path=("commander", "route", "monitor_only_when_holding"),
        state_key="enable_monitor_only_fast_path",
        default=True,
    )
    open_position_count = _portfolio_open_position_count(state)
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_entry = (applied_policy.get("monitor") or {}).get("entry") if isinstance((applied_policy.get("monitor") or {}), dict) else {}
    block_buy_when_open_position = _is_trueish(
        applied_entry.get("block_buy_when_open_position")
        if isinstance(applied_entry, dict) and applied_entry.get("block_buy_when_open_position") is not None
        else (
            state.get("monitor_block_buy_when_open_position")
            if state.get("monitor_block_buy_when_open_position") is not None
            else True
        )
    )
    payload = {
        "enabled": bool(enabled),
        "policy_source": str(policy_source),
        "open_position_count": int(open_position_count),
        "block_buy_when_open_position": bool(block_buy_when_open_position),
        "reason": "",
    }
    state["commander_open_position_override"] = {
        "override_triggered": False,
        "override_reason": "",
        "override_action": "",
        "policy_source": "commander_open_position_override",
    }
    state.pop("force_refresh_strategist", None)
    state.pop("commander_open_position_refresh_context", None)
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count <= 0:
        payload["reason"] = "no_open_position"
        return False, payload
    override_assessment = _assess_open_position_commander_override(state)
    state["commander_open_position_override"] = dict(override_assessment)
    if bool(override_assessment.get("override_triggered")):
        override_action = str(override_assessment.get("override_action") or "").strip().lower()
        if override_action == "strategist_refresh":
            state["force_refresh_strategist"] = True
            refresh_context = (
                dict(override_assessment.get("strategist_refresh_context") or {})
                if isinstance(override_assessment.get("strategist_refresh_context"), dict)
                else {}
            )
            if refresh_context:
                state["commander_open_position_refresh_context"] = dict(refresh_context)
        payload.update(
            {
                "override_triggered": True,
                "override_reason": str(override_assessment.get("override_reason") or ""),
                "override_action": str(override_assessment.get("override_action") or ""),
                "effective_loss_ratio_min": override_assessment.get("effective_loss_ratio_min"),
                "hold_repeat_count_max": int(override_assessment.get("hold_repeat_count_max") or 0),
                "price_anomaly_flag": bool(override_assessment.get("price_anomaly_flag")),
                "override_suppressed": bool(override_assessment.get("override_suppressed")),
                "override_suppressed_reason": str(override_assessment.get("override_suppressed_reason") or ""),
                "refresh_cooldown_sec": int(override_assessment.get("refresh_cooldown_sec") or 0),
                "refresh_cooldown_symbol": str(override_assessment.get("refresh_cooldown_symbol") or ""),
                "refresh_cooldown_until": override_assessment.get("refresh_cooldown_until"),
                "refresh_cooldown_remaining_sec": int(
                    override_assessment.get("refresh_cooldown_remaining_sec") or 0
                ),
                "strategist_refresh_context": dict(
                    override_assessment.get("strategist_refresh_context") or {}
                )
                if isinstance(override_assessment.get("strategist_refresh_context"), dict)
                else {},
            }
        )
        if override_action == "force_exit_review":
            payload["reason"] = "holding_position_force_exit_review_monitor_only"
            return True, payload
        payload["reason"] = "holding_position_override_full_cycle"
        return False, payload
    if bool(override_assessment.get("override_suppressed")):
        payload.update(
            {
                "override_suppressed": True,
                "override_suppressed_reason": str(override_assessment.get("override_suppressed_reason") or ""),
                "hold_repeat_count_max": int(override_assessment.get("hold_repeat_count_max") or 0),
                "refresh_cooldown_sec": int(override_assessment.get("refresh_cooldown_sec") or 0),
                "refresh_cooldown_symbol": str(override_assessment.get("refresh_cooldown_symbol") or ""),
                "refresh_cooldown_until": override_assessment.get("refresh_cooldown_until"),
                "refresh_cooldown_remaining_sec": int(
                    override_assessment.get("refresh_cooldown_remaining_sec") or 0
                ),
            }
        )
    if not block_buy_when_open_position:
        payload["reason"] = "buy_not_blocked_when_open_position"
        return False, payload
    payload["reason"] = "holding_position_monitor_only"
    return True, payload


def _should_use_session_closeout_fast_path(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    monitor_exit = (
        ((applied_policy.get("monitor") or {}).get("exit") or {})
        if isinstance((applied_policy.get("monitor") or {}).get("exit"), dict)
        else {}
    )
    eod_flat = (
        (monitor_exit.get("eod_flat") or {})
        if isinstance(monitor_exit.get("eod_flat"), dict)
        else {}
    )
    if not eod_flat and isinstance((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")), dict):
        eod_flat = dict((((policy.get("monitor") or {}).get("exit") or {}).get("eod_flat")) or {})
    use_eod_flat = (
        eod_flat.get("enabled")
        if eod_flat.get("enabled") is not None
        else (
            (policy.get("exit_policy") or {}).get("use_eod_flat")
            if isinstance(policy.get("exit_policy"), dict)
            else None
        )
    )
    cutoff_min = (
        eod_flat.get("cutoff_min")
        if eod_flat.get("cutoff_min") not in (None, "")
        else (
            (policy.get("exit_policy") or {}).get("eod_flat_cutoff_min")
            if isinstance(policy.get("exit_policy"), dict)
            else None
        )
    )
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    raw_minutes_to_close = market_context.get("minutes_to_close")
    minutes_to_close = None if raw_minutes_to_close in (None, "") else float(_runtime_float(raw_minutes_to_close, 0.0))
    active = bool(
        _is_trueish(use_eod_flat if use_eod_flat is not None else True)
        and minutes_to_close is not None
        and minutes_to_close >= 0.0
        and minutes_to_close <= float(_coerce_int(cutoff_min, 10))
    )
    payload = {
        "active": bool(active),
        "minutes_to_close": minutes_to_close,
        "cutoff_min": int(_coerce_int(cutoff_min, 10)),
        "use_eod_flat": bool(_is_trueish(use_eod_flat if use_eod_flat is not None else True)),
        "open_position_count": int(_portfolio_open_position_count(state)),
        "reason": "session_closeout_window" if active else (
            "minutes_to_close_unavailable"
            if minutes_to_close is None
            else "outside_closeout_window"
        ),
    }
    return bool(active), payload


def _strategist_cache_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = persisted_state.get("strategist_output_cache") if isinstance(persisted_state.get("strategist_output_cache"), dict) else {}
    if isinstance(raw_cached.get("output"), dict):
        return dict(raw_cached)
    if raw_cached:
        return {"output": dict(raw_cached), "generated_epoch": 0, "source": "legacy_cache"}
    return {}


def _assess_cached_strategist_reuse_preference(state: Dict[str, Any]) -> Dict[str, Any]:
    enabled, policy_source = _resolve_commander_route_toggle(
        state,
        nested_path=("commander", "route", "cached_strategist_when_flat"),
        state_key="enable_cached_strategist_when_flat",
        default=False,
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
        "policy_source": str(policy_source),
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
    enabled, policy_source = _resolve_commander_route_toggle(
        state,
        nested_path=("commander", "route", "cached_strategist_when_flat"),
        state_key="enable_cached_strategist_when_flat",
        default=False,
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
        "policy_source": str(policy_source),
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
    from graphs.nodes.reporter_node import reporter_node
    from graphs.nodes.update_state_after_execution import update_state_after_execution
    from libs.reporting.intraday_trade_reports import generate_intraday_trade_artifacts

    def _emit_intraday_trade_report(local_state: Dict[str, Any]) -> Dict[str, Any]:
        if _commander_trade_report_enabled(local_state):
            try:
                local_state["intraday_trade_report"] = reporter_node(local_state)
            except Exception as exc:
                local_state["intraday_trade_report"] = {
                    "ok": False,
                    "status": "failed",
                    "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
                }
        else:
            local_state["intraday_trade_report"] = {
                "ok": False,
                "status": "disabled",
                "reason": "reporter.trade_report.enabled is false",
                "policy_source": "commander_applied_policy",
            }
        return local_state

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

    use_closeout_guard, closeout_payload = _should_use_session_closeout_fast_path(state)
    if use_closeout_guard:
        shadow_runtime["strategist_executed"] = False
        shadow_runtime["strategist_called"] = False
        shadow_runtime["llm_called_by_strategist"] = False
        shadow_runtime["used_cached_strategist"] = False
        state = _hydrate_strategist_output_cache(state)
        state = _attach_commander_reporter_feedback_policy(state, selected_route="closeout", phase="session")
        state = _attach_commander_applied_policy(state)
        state["runtime_fast_path"] = dict(closeout_payload)
        state["session_closeout_guard"] = dict(closeout_payload)
        state["commander_decision"] = _build_commander_decision(
            state,
            mode_value="integrated_chain",
            phase_value=str(state.get("runtime_phase") or "session"),
            status_value=str(state.get("runtime_status") or "planning"),
            path_value="integrated_chain_closeout_guard",
            reason_text=str(closeout_payload.get("reason") or ""),
        )
        held_symbols = _portfolio_open_position_symbols(state)
        if held_symbols:
            state["selected"] = {
                "symbol": held_symbols[0],
                "_monitor_synthetic_selected": True,
                "_closeout_guard_selected": True,
            }
        else:
            state.pop("selected", None)
        state.pop("scanner_output", None)
        _log_commander_event(state, "fast_path", {"path": "integrated_chain_closeout_guard", **closeout_payload})
        state = _hydrate_monitor_symbol_features(state)
        state = monitor_node(state)
        shadow_runtime["monitor_decision"] = str(((state.get("monitor_output") or {}).get("intent_side") or "NOOP"))
        state = decision_node(state)
        decision = str(state.get("decision") or "").strip().lower()
        if decision == "approve":
            intent = _intent_from_monitor_state(state)
            state["decision_packet"] = _build_packet_from_state(state, intent=intent)
            state = execute_fn(state)
            shadow_runtime["executor_action"] = str(
                (((state.get("execution") or {}).get("order") or {}).get("action") or ((state.get("decision_packet") or {}).get("intent") or {}).get("action") or "")
            )
            shadow_runtime["executor_status"] = str(((state.get("execution") or {}).get("reason") or ((state.get("execution") or {}).get("ok_source") or "")))
            state = _emit_intraday_trade_report(state)
            state = update_state_after_execution(state)
        state["path"] = "integrated_chain_closeout_guard"
        return state

    use_monitor_only, fast_path_payload = _should_use_monitor_only_fast_path(state)
    if use_monitor_only:
        shadow_runtime["strategist_executed"] = False
        shadow_runtime["strategist_called"] = False
        shadow_runtime["llm_called_by_strategist"] = False
        shadow_runtime["used_cached_strategist"] = False
        state = _hydrate_strategist_output_cache(state)
        state = _attach_commander_reporter_feedback_policy(state, selected_route="monitor_only", phase="session")
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
            state = _emit_intraday_trade_report(state)
            state = update_state_after_execution(state)
        state["path"] = "integrated_chain_monitor_only"
        return state

    state["commander_decision"] = _build_commander_decision(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value="integrated_chain_pre_strategist",
        reason_text=str(fast_path_payload.get("reason") or ""),
    )

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
        state = _attach_commander_reporter_feedback_policy(state, selected_route="full_cycle", phase="session")
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
    if reused_strategist_cache:
        state = _attach_commander_reporter_feedback_policy(state, selected_route="cached_strategist", phase="session")
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
        state = _emit_intraday_trade_report(state)
        state = update_state_after_execution(state)

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
    state = _attach_commander_reporter_feedback_policy(state, selected_route="full_cycle", phase="preopen")
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
    state = _attach_commander_reporter_feedback_policy(state, selected_route="full_cycle", phase="closeout")
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
    _ensure_market_context_clock_fields(state)
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
    _log_commander_event(
        state,
        "route_selected",
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
            state = _maybe_run_reporter_hooks(state, mode_value=selected, phase_value=selected_phase)
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
            state = _maybe_run_reporter_hooks(state, mode_value=selected, phase_value=selected_phase)
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
            state = _maybe_run_reporter_hooks(state, mode_value=selected, phase_value=selected_phase)
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
        state = _maybe_run_reporter_hooks(state, mode_value=selected, phase_value=selected_phase)
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
