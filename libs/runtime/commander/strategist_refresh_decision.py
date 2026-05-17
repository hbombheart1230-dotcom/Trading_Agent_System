from __future__ import annotations

from typing import Any, Dict

from libs.runtime.commander.env_overrides import is_trueish
from libs.runtime.commander.policy_readers import coerce_int
from libs.runtime.commander.policy_surface import (
    PRE_BUY_STRATEGIST_REFRESH_FORCE_SIGNALS,
    PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC,
    PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD,
)
from libs.runtime.commander.strategist_cache_decision import (
    portfolio_open_position_count,
    runtime_now_epoch,
    strategist_cache_payload,
)
from libs.runtime.commander.strategist_fingerprint import (
    assess_cached_strategist_input_drift,
    portfolio_open_position_symbols,
    post_scanner_candidate_snapshot,
    post_scanner_selected_symbol,
    shadow_float,
)


def resolve_risk_max_positions(state: Dict[str, Any] | None = None) -> int:
    obj = state if isinstance(state, dict) else {}
    for value in (
        ((obj.get("risk_context") or {}).get("max_positions") if isinstance(obj.get("risk_context"), dict) else None),
        ((obj.get("risk") or {}).get("max_positions") if isinstance(obj.get("risk"), dict) else None),
    ):
        try:
            if value not in (None, ""):
                return max(1, int(float(value)))
        except Exception:
            continue
    return 1


def assess_pre_buy_strategist_refresh_need(
    state: Dict[str, Any],
    *,
    commander_market_regime: str = "",
) -> Dict[str, Any]:
    min_cache_age_sec = int(PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC)
    readiness_threshold = float(PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD)
    open_position_count = portfolio_open_position_count(state)
    max_positions = resolve_risk_max_positions(state)
    entry_capacity_available = open_position_count < max_positions
    cache_payload = strategist_cache_payload(state)
    cached_output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = runtime_now_epoch(state)
    generated_epoch = max(0, coerce_int(cache_payload.get("generated_epoch"), 0))
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
    readiness_score = shadow_float(
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
        "max_positions": int(max_positions),
        "entry_capacity_available": bool(entry_capacity_available),
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
        "fresh_cache_signal_override": bool(signal in PRE_BUY_STRATEGIST_REFRESH_FORCE_SIGNALS),
        "cache_freshness_gate_bypassed": False,
        "reason": "",
    }
    if open_position_count > 0 and not entry_capacity_available:
        payload["reason"] = "max_positions_reached"
        return payload
    if is_trueish(state.get("force_refresh_strategist")):
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
        if not signal or signal not in PRE_BUY_STRATEGIST_REFRESH_FORCE_SIGNALS:
            payload["reason"] = "cache_too_fresh_for_refresh"
            return payload
        payload["cache_freshness_gate_bypassed"] = True
    if not signal:
        payload["reason"] = "no_pre_buy_refresh_signal"
        return payload
    input_drift = assess_cached_strategist_input_drift(state)
    payload["strategist_input_drift"] = dict(input_drift)
    if bool(input_drift.get("comparable")) and not bool(input_drift.get("material_change")):
        payload["reason"] = "strategist_input_context_unchanged"
        payload["refresh_signal_suppressed"] = str(signal)
        return payload
    payload["requested"] = True
    payload["reason"] = "commander_requested_refresh"
    return payload


def force_selected_symbol_tactical_refresh_decision(
    state: Dict[str, Any],
    commander_decision: Dict[str, Any],
) -> Dict[str, Any]:
    if bool(commander_decision.get("strategist_refresh_requested")):
        return commander_decision
    open_position_count = portfolio_open_position_count(state)
    max_positions = resolve_risk_max_positions(state)
    if open_position_count >= max_positions:
        return commander_decision
    selected_symbol = post_scanner_selected_symbol(state)
    if not selected_symbol:
        return commander_decision
    if selected_symbol in set(portfolio_open_position_symbols(state)):
        return commander_decision
    snapshot = post_scanner_candidate_snapshot(state, selected_symbol)
    primary = dict(snapshot.get("primary") or {})
    input_drift = assess_cached_strategist_input_drift(state)
    if bool(input_drift.get("comparable")) and not bool(input_drift.get("material_change")):
        out = dict(commander_decision)
        refresh_context = (
            dict(out.get("strategist_refresh_context") or {})
            if isinstance(out.get("strategist_refresh_context"), dict)
            else {}
        )
        refresh_context.update(
            {
                "refresh_scope": "selected_symbol_tactical_refresh",
                "refresh_signal": "selected_symbol_tactical_refresh",
                "selected_symbol": selected_symbol,
                "selected_rank": int(primary.get("rank") or 0),
                "selected_score": primary.get("score"),
                "post_scanner_refresh_required": False,
                "post_scanner_refresh_suppressed": True,
                "post_scanner_refresh_suppressed_reason": "strategist_input_context_unchanged",
                "strategist_input_drift": dict(input_drift),
            }
        )
        out["strategist_refresh_context"] = dict(refresh_context)
        observations = out.get("observations") if isinstance(out.get("observations"), dict) else {}
        out["observations"] = {
            **dict(observations),
            "post_scanner_refresh_requested": False,
            "post_scanner_refresh_suppressed": True,
            "post_scanner_refresh_suppressed_reason": "strategist_input_context_unchanged",
            "strategist_input_change_score": input_drift.get("change_score"),
        }
        return out
    refresh_context = (
        dict(commander_decision.get("strategist_refresh_context") or {})
        if isinstance(commander_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    refresh_context.update(
        {
            "refresh_scope": "selected_symbol_tactical_refresh",
            "refresh_signal": "selected_symbol_tactical_refresh",
            "selected_symbol": selected_symbol,
            "selected_rank": int(primary.get("rank") or 0),
            "selected_score": primary.get("score"),
            "scanner_primary_candidate": dict(primary),
            "actual_selected_candidate": dict(snapshot.get("selected_candidate") or primary),
            "scanner_rank1_candidate": dict(snapshot.get("scanner_rank1_candidate") or {}),
            "scanner_runner_ups": list(snapshot.get("runner_ups") or []),
            "scanner_top_candidates": list(snapshot.get("rows") or []),
            "selected_symbol_was_rank1": bool(snapshot.get("selected_symbol_was_rank1")),
            "stage2_context_quality": str(snapshot.get("stage2_context_quality") or ""),
            "stage2_context_quality_reasons": list(snapshot.get("stage2_context_quality_reasons") or []),
            "strategist_input_drift": dict(input_drift),
            "post_scanner_refresh_required": True,
            "refresh_summary": f"Selected-symbol tactical refresh after scanner ranking for {selected_symbol}.",
        }
    )
    out = dict(commander_decision)
    out["strategist_refresh_requested"] = True
    out["strategist_refresh_reason"] = "selected_symbol_tactical_refresh"
    out["strategist_refresh_context"] = dict(refresh_context)
    out["strategist_invocation"] = "RUN_REFRESH"
    out["strategist_invocation_mode"] = "selected_symbol_tactical_refresh"
    out["llm_policy"] = "allow_context_refresh"
    out["flow_instruction"] = "REFRESH_SELECTED_SYMBOL_TACTICAL_FRAME"
    observations = out.get("observations") if isinstance(out.get("observations"), dict) else {}
    out["observations"] = {
        **dict(observations),
        "post_scanner_refresh_requested": True,
        "post_scanner_refresh_reason": "selected_symbol_tactical_refresh",
        "post_scanner_refresh_selected_symbol": selected_symbol,
    }
    return out
