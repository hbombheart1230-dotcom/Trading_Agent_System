from __future__ import annotations

"""Canonical Monitor node for integrated runtime.

Role boundary:
- monitors selected stock / active position state
- emits entry/exit intents only
- never re-ranks symbol universe and never executes orders
"""

import os
import time
from functools import partial
from pathlib import Path
from typing import Any, Dict, List

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_market_quotes,
    extract_minute_ohlcv_by_symbol,
    extract_order_status,
)
from libs.core.symbols import normalize_symbol
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.canonical_artifacts import write_monitor_artifact
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.decision_observability import (
    build_entry_blocker_surface,
    build_monitor_no_trade_surface,
    build_scanner_monitor_handoff_surface,
)
from libs.runtime.etf_deviation import extract_etf_deviation_signal
from libs.runtime.monitor_candidate_cascade import build_entry_candidate_cascade_plan
from libs.runtime.monitor_runner_up_quality import evaluate_runner_up_entry_quality
from libs.runtime.commander_memory_application_trace import build_monitor_commander_memory_application_trace
from libs.runtime.monitor_entry_blockers import evaluate_entry_guard
from libs.runtime.monitor_entry_quality import (
    classify_vwap_reclaim_pullback_candidate as _classify_vwap_reclaim_pullback_candidate,
    evaluate_entry_quality_gate as _evaluate_entry_quality_gate,
)
from libs.runtime.monitor_entry_cost_filter import (
    evaluate_entry_cost_filter as _evaluate_entry_cost_filter,
    resolve_entry_cost_filter_config as _resolve_entry_cost_filter_config,
)
from libs.runtime.monitor_entry_controls import (
    features_pending_order_count as _features_pending_order_count,
    pending_buy_symbols_from_account_orders as _pending_buy_symbols_from_account_orders,
    pending_order_symbols_from_account_orders as _pending_order_symbols_from_account_orders,
    resolve_block_buy_when_open_position as _resolve_block_buy_when_open_position,
    resolve_entry_closeout_window_guard as _resolve_entry_closeout_window_guard,
    resolve_max_positions as _resolve_max_positions,
)
from libs.runtime.monitor_entry_policy_context import (
    build_monitor_effective_policy_trace as _build_monitor_effective_policy_trace,
    resolve_commander_entry_control_for_monitor as _resolve_commander_entry_control_for_monitor,
    resolve_entry_candidate_cascade_config as _resolve_entry_candidate_cascade_config,
    resolve_monitor_entry_scoring_config as _resolve_monitor_entry_scoring_config,
    resolve_monitor_memory_bias_payload as _resolve_monitor_memory_bias_payload,
)
from libs.runtime.monitor_entry_sizing import (
    build_sizing_risk_context as _build_sizing_risk_context,
    derive_position_sizing_stop_context as _derive_position_sizing_stop_context,
    position_by_symbol as _position_by_symbol,
    resolve_cash as _resolve_cash,
    resolve_position_sizing_config as _resolve_position_sizing_config,
)
from libs.runtime.monitor_entry_state import (
    build_monitor_entry_state_snapshot as _build_monitor_entry_state_snapshot,
    build_monitor_entry_transition_trace as _build_monitor_entry_transition_trace,
    load_previous_monitor_state as _load_previous_monitor_state,
    monitor_posture_for_cycle as _monitor_posture_for_cycle,
    save_current_monitor_state as _save_current_monitor_state,
)
from libs.runtime.quant.decision import build_entry_quant_decision, build_exit_quant_decision
from libs.runtime.quant.enforcement import build_entry_quant_enforcement
from libs.runtime.quant.factors import build_factor_snapshot_from_monitor_entry
from libs.runtime.intraday_monitor_signals import (
    evaluate_intraday_entry_signal,
    resolve_intraday_entry_policy,
)
from libs.runtime.monitor_exit.hold_controls import (
    resolve_exit_confirm_ticks as _resolve_exit_confirm_ticks,
    resolve_min_hold_sec as _resolve_min_hold_sec,
    resolve_post_exit_cooldown_sec as _resolve_post_exit_cooldown_sec,
    resolve_sell_cooldown_sec as _resolve_sell_cooldown_sec,
    resolve_use_exit_policy as _resolve_use_exit_policy,
)
from libs.runtime.monitor_exit.observability import build_monitor_exit_payload
from libs.runtime.monitor_exit.overnight_carry import (
    evaluate_overnight_carry_decision,
    persist_eod_carry_decisions_for_open_positions,
    persist_overnight_decision,
)
from libs.runtime.monitor_exit.order_lifecycle import derive_order_lifecycle as _derive_order_lifecycle
from libs.runtime.monitor_exit.policy_config import resolve_exit_policy_config as _resolve_exit_policy_config
from libs.runtime.monitor_exit.post_exit_shadow import (
    active_post_exit_shadow_watches as _active_post_exit_shadow_watches,
    refresh_post_exit_shadow_watchlist_minute_rows as _refresh_post_exit_shadow_watchlist_minute_rows,
)
from libs.runtime.monitor_exit.position_tracking import (
    ensure_position_peak_price_map as _ensure_position_peak_price_map,
    position_hold_seconds as _position_hold_seconds,
)
from libs.runtime.monitor_exit.price_resolution import (
    resolve_price as _resolve_price,
    resolve_price_with_source as _resolve_price_with_source,
)
from libs.runtime.monitor_exit.preview import preview_exit_decision_for_symbol
from libs.runtime.monitor_exit.reasons import (
    friendly_exit_axis as _friendly_exit_axis,
    is_emergency_exit_reason as _is_emergency_exit_reason,
    is_hard_exit_reason as _is_hard_exit_reason,
    monitor_watch_axes as _monitor_watch_axes,
)
from libs.runtime.monitor_exit.selection import select_exit_symbol
from libs.runtime.monitor_exit.selected_snapshot import (
    monitor_selected_snapshot_for_symbol as _monitor_selected_snapshot_for_symbol,
)
from libs.runtime.monitor_memory_bias import (
    apply_monitor_memory_bias_to_exit_policy,
    apply_monitor_memory_bias_to_hold_controls,
    apply_monitor_memory_bias_to_entry_policy,
    summarize_monitor_memory_bias,
)
from libs.runtime.monitor_minute_ohlcv import (
    _ensure_monitor_minute_ohlcv_for_symbol,
    _extract_monitor_minute_rows,
    _fresh_monitor_skill_runner,
    _is_trueish,
    _latest_row_ts,
    _minute_snapshot_age_minutes,
    _minute_snapshot_stale_reason,
    _monitor_skill_output_to_record,
    _recover_monitor_minute_rows_from_history,
    _recover_monitor_minute_rows_from_persisted_cache,
    _remember_monitor_minute_rows_in_persisted_cache,
    _resolve_monitor_skill_runner,
    _run_monitor_minute_skill,
)
from libs.runtime.monitor_policy import (
    MonitorEntryPolicy,
    build_monitor_entry_policy_contract,
)
from libs.runtime.monitor_strategy_frame import (
    build_monitor_policy_trace as _build_monitor_policy_trace,
    extract_monitor_strategy_frame as _extract_monitor_strategy_frame,
    position_strategy_frame_for_symbol as _position_strategy_frame_for_symbol,
    apply_exit_policy_strategy_frame as _apply_exit_policy_strategy_frame,
    apply_monitor_strategy_frame as _apply_monitor_strategy_frame,
    harmonize_exit_policy_with_monitor_guards as _harmonize_exit_policy_with_monitor_guards,
)
from libs.runtime.position_sizing import evaluate_position_size
from libs.runtime.strategy_horizon_feedback import build_exit_vs_strategy_intent

_preview_exit_decision_for_symbol = partial(
    preview_exit_decision_for_symbol,
    selected_snapshot_resolver=_monitor_selected_snapshot_for_symbol,
)
_persist_overnight_decision = persist_overnight_decision
_evaluate_overnight_carry_decision = evaluate_overnight_carry_decision
_persist_eod_carry_decisions_for_open_positions = partial(
    persist_eod_carry_decisions_for_open_positions,
    preview_resolver=_preview_exit_decision_for_symbol,
    hold_seconds_resolver=_position_hold_seconds,
)
_select_exit_symbol = partial(
    select_exit_symbol,
    preview_resolver=_preview_exit_decision_for_symbol,
)


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _memory_bias_observation_only(state: Dict[str, Any] | None = None) -> bool:
    if isinstance(state, dict):
        for key in ("memory_bias_observation_only", "commander_memory_bias_observation_only"):
            if state.get(key) not in (None, ""):
                return _is_trueish(state.get(key))
    for name in ("MEMORY_BIAS_OBSERVATION_ONLY", "COMMANDER_MEMORY_BIAS_OBSERVATION_ONLY"):
        raw = str(os.getenv(name, "") or "").strip()
        if raw:
            return _is_trueish(raw)
    return False


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _optional_float(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    tick_ts = state.get("tick_ts")
    try:
        if tick_ts is not None:
            return int(float(tick_ts))
    except Exception:
        pass
    return int(time.time())


def _norm_symbol(v: Any) -> str:
    return normalize_symbol(v)


def _clear_symbol_confirm_keys(confirm_map: Dict[str, Any], symbol: str) -> None:
    prefix = f"{_norm_symbol(symbol)}:"
    for key in list(confirm_map.keys()):
        if str(key).startswith(prefix):
            confirm_map.pop(key, None)


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _emit_monitor_event(
    state: Dict[str, Any],
    *,
    name: str,
    payload: Dict[str, Any],
    level: str = "info",
    symbol: str = "",
) -> None:
    try:
        logger = _make_event_logger(state)
        from libs.core.event_logger import log_state_event

        log_state_event(
            logger,
            state,
            stage="monitor",
            event=name,
            event_name=f"monitor.{name}",
            payload=dict(payload or {}),
            level=level,
            agent="monitor",
            symbol=str(symbol or ""),
        )
    except Exception:
        return


def _log_monitor_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "monitor-node")
        logger.log(run_id=run_id, stage="monitor", event="summary", payload=dict(payload))
    except Exception:
        return


def _evaluate_monitor_entry_candidate(
    *,
    state: Dict[str, Any],
    selected: Dict[str, Any],
    plan: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    strategy_monitor_policy: Dict[str, Any],
    strategy_frame: Dict[str, Any],
    commander_context: Dict[str, Any],
    entry_policy_contract: Dict[str, Any],
    entry_policy_input: Dict[str, Any],
    entry_policy_origin: str,
    all_pos_map: Dict[str, Any],
    open_position_count: int,
    block_buy_open_position: bool,
    post_exit_cooldown_sec: int,
    entry_cooldown_map: Dict[str, Any],
    now_epoch_for_entry: int,
    prefer_fresh_minute_runner: bool = False,
) -> Dict[str, Any]:
    symbol = _norm_symbol(selected.get("symbol"))
    qty = 1
    max_positions = _resolve_max_positions(state, policy)
    held_symbols = {
        _norm_symbol(sym)
        for sym, row in all_pos_map.items()
        if _norm_symbol(sym) and max(0, _to_int((row or {}).get("qty"))) > 0
    }
    pending_buy_symbols = _pending_buy_symbols_from_account_orders(state)
    selected_already_held = bool(symbol and symbol in held_symbols)
    selected_features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    selected_pending_buy = bool(
        symbol
        and (
            symbol in pending_buy_symbols
            or _features_pending_order_count(selected_features) > 0
        )
    )
    strategist_output_for_sizing = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    strategy_policy_for_sizing = (
        dict(strategist_output_for_sizing.get("strategy_policy") or {})
        if isinstance(strategist_output_for_sizing.get("strategy_policy"), dict)
        else dict(state.get("strategy_policy") or {})
        if isinstance(state.get("strategy_policy"), dict)
        else {}
    )
    use_position_sizing, position_sizing_policy = _resolve_position_sizing_config(
        state,
        policy=policy,
        strategy_policy=strategy_policy_for_sizing,
    )
    sizing_info: Dict[str, Any] = {
        "enabled": bool(use_position_sizing),
        "evaluated": False,
        "qty": 1 if not use_position_sizing else 0,
        "reason": "pending" if use_position_sizing else "disabled",
        "price": None,
        "cash": None,
        "inputs": {},
        "stop_context": {},
    }

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
    last_trade_symbol = _norm_symbol(persisted.get("last_trade_symbol"))
    post_exit_cooldown_symbol_match = bool(not last_trade_symbol or last_trade_symbol == symbol)
    post_exit_cooldown_scope = "same_symbol" if last_trade_symbol else "legacy_global_no_symbol"
    closeout_window_guard = _resolve_entry_closeout_window_guard(state, policy)
    buy_blocked_post_exit_cooldown = False
    post_exit_cooldown_remaining_sec = 0
    if (
        open_position_count <= 0
        and post_exit_cooldown_sec > 0
        and last_trade_side == "SELL"
        and last_trade_epoch > 0
        and post_exit_cooldown_symbol_match
    ):
        elapsed = max(0, int(now_epoch_for_entry - last_trade_epoch))
        remaining = max(0, int(post_exit_cooldown_sec - elapsed))
        if remaining > 0:
            buy_blocked_post_exit_cooldown = True
            post_exit_cooldown_remaining_sec = remaining

    monitor_memory_bias = _resolve_monitor_memory_bias_payload(
        strategy_monitor_policy=strategy_monitor_policy,
        commander_context=commander_context,
        state=state,
    )
    monitor_memory_bias_summary = summarize_monitor_memory_bias(monitor_memory_bias)
    entry_received_policy = MonitorEntryPolicy.from_mapping(entry_policy_input or monitor_policy).to_dict()
    commander_entry_control = (
        dict(commander_context.get("commander_entry_control") or commander_context.get("entry_control") or {})
        if isinstance(commander_context, dict)
        else {}
    )
    if commander_entry_control:
        entry_policy_input = dict(entry_policy_input or monitor_policy or {})
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    monitor_memory_bias_result = apply_monitor_memory_bias_to_entry_policy(
        entry_policy=entry_policy_input or monitor_policy,
        monitor_memory_bias=monitor_memory_bias,
    )
    monitor_memory_bias_observation_only = _memory_bias_observation_only(state)
    monitor_memory_bias_observed_entry_result = dict(monitor_memory_bias_result)
    if monitor_memory_bias_observation_only:
        monitor_memory_bias_result = {
            "policy": MonitorEntryPolicy.from_mapping(entry_policy_input or monitor_policy).to_dict(),
            "applied": False,
            "deltas": [],
            "observation_only": True,
            "observed_deltas": list(monitor_memory_bias_observed_entry_result.get("deltas") or []),
        }
    entry_policy_input = dict(monitor_memory_bias_result.get("policy") or {})
    if commander_entry_control:
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    entry_policy = resolve_intraday_entry_policy(entry_policy_input or monitor_policy, frame=strategy_frame)
    state = _ensure_monitor_minute_ohlcv_for_symbol(
        state,
        symbol=symbol,
        timeframe_minutes=int(entry_policy.timeframe_minutes or 1),
        now_epoch=now_epoch_for_entry,
        prefer_fresh_runner=prefer_fresh_minute_runner,
    )
    entry_rows = []
    minute_ohlcv_by_symbol, minute_ohlcv_meta = extract_minute_ohlcv_by_symbol(state)
    entry_row_source = str((minute_ohlcv_meta or {}).get("source") or "")
    minute_fetch_meta = (
        dict(state.get("monitor_minute_ohlcv_fetch") or {})
        if isinstance(state.get("monitor_minute_ohlcv_fetch"), dict)
        else {}
    )
    entry_scoring_policy = _resolve_monitor_entry_scoring_config(state, policy)
    if symbol and isinstance(minute_ohlcv_by_symbol.get(symbol), list):
        entry_rows = list(minute_ohlcv_by_symbol.get(symbol) or [])
    quotes_for_entry, _quote_meta_for_entry = extract_market_quotes(state)
    quote_for_entry = (
        quotes_for_entry.get(_norm_symbol(symbol))
        if isinstance(quotes_for_entry.get(_norm_symbol(symbol)), dict)
        else {}
    )
    deviation_signal = extract_etf_deviation_signal(
        symbol=symbol,
        candidate=selected,
        features=selected_features,
        quote=quote_for_entry,
        state=state,
        asset_class_detected=selected_features.get("asset_class_detected") or selected.get("asset_class_detected"),
    )
    entry_features = dict(selected_features)
    if deviation_signal.get("etf_deviation_pct") is not None:
        entry_features["etf_deviation_pct"] = deviation_signal.get("etf_deviation_pct")
        entry_features["etf_deviation_source"] = deviation_signal.get("etf_deviation_source")
        entry_features["etf_deviation_available"] = bool(deviation_signal.get("available"))
    if deviation_signal.get("asset_class_detected"):
        entry_features["asset_class_detected"] = deviation_signal.get("asset_class_detected")
    entry_features["etf_deviation_entry_score"] = deviation_signal.get("entry_discount_score")
    entry_features["etf_deviation_premium_score"] = deviation_signal.get("exit_premium_score")
    selected["features"] = entry_features
    entry_info = evaluate_intraday_entry_signal(
        entry_rows,
        current_price=selected.get("price") if isinstance(selected, dict) else None,
        features=entry_features,
        policy=entry_policy,
        scoring=entry_scoring_policy,
        frame=strategy_frame,
        policy_contract=entry_policy_contract,
    )
    entry_info["closeout_window_guard"] = dict(closeout_window_guard)
    entry_info["minutes_to_close"] = closeout_window_guard.get("minutes_to_close")
    entry_info["eod_flat_cutoff_min"] = int(closeout_window_guard.get("cutoff_min") or 0)
    entry_info["buy_closeout_cutoff_min"] = int(closeout_window_guard.get("buy_cutoff_min") or 0)
    entry_info["closeout_window_active"] = bool(closeout_window_guard.get("active"))
    entry_info["symbol"] = symbol
    entry_info["selected_symbol"] = symbol
    entry_info["max_positions"] = int(max_positions)
    entry_info["multi_position_capacity_remaining"] = max(0, int(max_positions) - int(open_position_count))
    entry_info["held_symbols"] = sorted(held_symbols)
    entry_info["pending_buy_symbols"] = sorted(pending_buy_symbols)
    entry_info["selected_symbol_already_held"] = bool(selected_already_held)
    entry_info["selected_symbol_pending_buy"] = bool(selected_pending_buy)
    entry_info["post_exit_cooldown_scope"] = str(post_exit_cooldown_scope)
    entry_info["post_exit_cooldown_last_trade_symbol"] = str(last_trade_symbol)
    entry_info["post_exit_cooldown_symbol_match"] = bool(post_exit_cooldown_symbol_match)
    if commander_entry_control:
        entry_info["commander_entry_control"] = dict(commander_entry_control)
    entry_info["applied_policy"] = dict(entry_info.get("applied_policy") or entry_info.get("thresholds") or entry_policy.to_dict())
    entry_applied_policy = dict(entry_info.get("applied_policy") or {})
    effective_policy_trace = _build_monitor_effective_policy_trace(
        received_policy=entry_received_policy,
        effective_policy=entry_applied_policy,
        frame=strategy_frame,
        received_policy_source=entry_policy_origin,
    )
    if bool(monitor_memory_bias_result.get("applied")):
        source_chain = list(effective_policy_trace.get("effective_policy_source_chain") or [])
        effective_policy_trace["effective_policy_source_chain"] = (
            [source_chain[0], "commander_memory_bias", *source_chain[1:]]
            if source_chain
            else ["commander_memory_bias", "monitor_effective_policy"]
        )
        effective_policy_trace["effective_policy_source"] = "monitor_memory_bias_adjusted"
        policy_adjustment_summary = str(effective_policy_trace.get("policy_adjustment_summary") or "").strip()
        effective_policy_trace["policy_adjustment_summary"] = (
            f"{policy_adjustment_summary} | memory_bias=commander"
            if policy_adjustment_summary
            else "commander memory bias adjusted entry policy"
        )
        policy_adjustment_reasoning = str(effective_policy_trace.get("policy_adjustment_reasoning") or "").strip()
        prefix = "Commander-approved memory bias adjusted the entry baseline before strategy-frame normalization."
        effective_policy_trace["policy_adjustment_reasoning"] = (
            f"{prefix} {policy_adjustment_reasoning}".strip()
        )
    entry_info["received_policy"] = dict(effective_policy_trace.get("received_policy") or {})
    entry_info["received_policy_source"] = str(effective_policy_trace.get("received_policy_source") or "")
    entry_info["policy_contract"] = dict(entry_policy_contract)
    entry_info["effective_policy"] = dict(effective_policy_trace.get("effective_policy") or {})
    entry_info["effective_policy_source"] = str(effective_policy_trace.get("effective_policy_source") or "")
    entry_info["effective_policy_source_chain"] = list(effective_policy_trace.get("effective_policy_source_chain") or [])
    entry_info["policy_adjustments"] = dict(effective_policy_trace.get("policy_adjustments") or {})
    entry_info["policy_adjustment_summary"] = str(effective_policy_trace.get("policy_adjustment_summary") or "")
    entry_info["policy_adjustment_reasoning"] = str(effective_policy_trace.get("policy_adjustment_reasoning") or "")
    entry_info["effective_policy_deltas"] = list(effective_policy_trace.get("effective_policy_deltas") or [])
    entry_info["monitor_memory_bias_applied"] = bool(monitor_memory_bias_result.get("applied"))
    entry_info["monitor_memory_bias_observation_only"] = bool(monitor_memory_bias_observation_only)
    entry_info["monitor_memory_bias"] = dict(monitor_memory_bias)
    entry_info["monitor_memory_bias_summary"] = dict(monitor_memory_bias_summary)
    entry_info["monitor_memory_bias_deltas"] = list(monitor_memory_bias_result.get("deltas") or [])
    entry_info["monitor_memory_bias_observed_deltas"] = list(
        monitor_memory_bias_observed_entry_result.get("deltas") or []
    )
    entry_memory_application_trace = build_monitor_commander_memory_application_trace(
        monitor_memory_bias=monitor_memory_bias,
        entry_result=monitor_memory_bias_result,
        hold_result={"applied": False, "deltas": []},
        exit_result={"applied": False, "deltas": []},
        monitor_memory_bias_summary=monitor_memory_bias_summary,
        effective_policy_source=str(effective_policy_trace.get("effective_policy_source") or ""),
        effective_policy_source_chain=list(effective_policy_trace.get("effective_policy_source_chain") or []),
    )
    entry_info["commander_memory_application_trace"] = dict(entry_memory_application_trace)
    entry_info["monitor_memory_application_trace"] = dict(entry_memory_application_trace)
    entry_metrics = entry_info.get("metrics") if isinstance(entry_info.get("metrics"), dict) else {}
    entry_metrics["minute_source_present"] = bool(entry_rows)
    entry_metrics["minute_source_used"] = entry_row_source or ""
    latest_candle_ts = None
    if entry_rows and isinstance(entry_rows[-1], dict):
        latest_candle_ts = entry_rows[-1].get("ts")
    entry_metrics["latest_candle_ts"] = latest_candle_ts
    entry_metrics["minute_snapshot_age_minutes"] = minute_fetch_meta.get("minute_snapshot_age_minutes")
    entry_metrics["minute_snapshot_was_stale"] = bool(minute_fetch_meta.get("minute_snapshot_was_stale"))
    entry_metrics["minute_refetch_attempted"] = bool(minute_fetch_meta.get("minute_refetch_attempted"))
    entry_metrics["minute_refetch_succeeded"] = bool(minute_fetch_meta.get("minute_refetch_succeeded"))
    entry_metrics["minute_refetch_reason"] = str(minute_fetch_meta.get("minute_refetch_reason") or "")
    entry_metrics["minute_refetch_trigger_reason"] = str(minute_fetch_meta.get("minute_refetch_trigger_reason") or "")
    entry_metrics["minute_refetch_failure_reason"] = str(minute_fetch_meta.get("minute_refetch_failure_reason") or "")
    entry_metrics["minute_refetch_failure_detail"] = str(minute_fetch_meta.get("minute_refetch_failure_detail") or "")
    entry_metrics["minute_refetch_runner_source"] = str(minute_fetch_meta.get("minute_refetch_runner_source") or "")
    entry_metrics["minute_refetch_produced_fresh_snapshot"] = bool(
        minute_fetch_meta.get("minute_refetch_produced_fresh_snapshot")
    )
    entry_metrics["minute_cache_fallback_used"] = bool(minute_fetch_meta.get("minute_cache_fallback_used"))
    entry_metrics["minute_cache_fallback_source"] = str(minute_fetch_meta.get("minute_cache_fallback_source") or "")
    entry_info["metrics"] = entry_metrics
    entry_info["minute_source_meta"] = dict(minute_ohlcv_meta or {})
    entry_info["minute_fetch_meta"] = minute_fetch_meta
    if use_position_sizing:
        px = _resolve_price(state, symbol, selected)
        cash = _resolve_cash(state)
        sizing_risk_context = _build_sizing_risk_context(state, selected, symbol)
        effective_sizing_policy = dict(position_sizing_policy if position_sizing_policy else policy)
        stop_context = _derive_position_sizing_stop_context(
            state=state,
            symbol=symbol,
            selected=selected,
            entry_info=entry_info,
            price=px,
            sizing_policy=effective_sizing_policy,
        )
        if bool(stop_context.get("applied")):
            effective_sizing_policy["stop_loss_pct"] = stop_context.get("stop_loss_pct")
            effective_sizing_policy["stop_loss_source"] = stop_context.get("stop_loss_source")
            effective_sizing_policy["invalidation_price"] = stop_context.get("invalidation_price")
            effective_sizing_policy["raw_structure_stop_loss_pct"] = stop_context.get("raw_stop_loss_pct")
            effective_sizing_policy["min_structure_stop_loss_pct"] = stop_context.get("min_structure_stop_loss_pct")
        sz = evaluate_position_size(
            price=px,
            cash=cash if cash > 0.0 else None,
            policy=effective_sizing_policy,
            risk_context=sizing_risk_context,
        )
        qty = max(0, _to_int(sz.get("qty")))
        sizing_info = {
            "enabled": True,
            "evaluated": bool(sz.get("evaluated")),
            "qty": int(qty),
            "reason": str(sz.get("reason") or ""),
            "price": sz.get("price"),
            "cash": sz.get("cash"),
            "inputs": sz.get("inputs") if isinstance(sz.get("inputs"), dict) else {},
            "stop_context": dict(stop_context),
        }
    entry_cost_filter_config = _resolve_entry_cost_filter_config(
        state=state,
        policy=policy,
        monitor_policy=monitor_policy,
        strategy_monitor_policy=strategy_monitor_policy,
        entry_policy_input=entry_policy_input,
        commander_entry_control=commander_entry_control,
    )
    entry_cost_filter = _evaluate_entry_cost_filter(
        entry_info=entry_info,
        selected=selected,
        qty=int(qty),
        config=entry_cost_filter_config,
    )
    entry_info["entry_cost_filter"] = dict(entry_cost_filter)
    entry_info["cost_adjusted_edge_ok"] = bool(entry_cost_filter.get("cost_adjusted_edge_ok"))
    entry_info["cost_adjusted_edge_pct"] = entry_cost_filter.get("cost_adjusted_edge_pct")
    entry_info["cost_drag_pct"] = entry_cost_filter.get("cost_drag_pct")
    entry_quality_gate = _evaluate_entry_quality_gate(
        selected=selected,
        entry_info=entry_info,
        entry_cost_filter=entry_cost_filter,
    )
    entry_info["entry_quality_gate"] = dict(entry_quality_gate)
    entry_info["entry_lane"] = "strict"
    entry_info["scoring_mode"] = str(entry_info.get("scoring_mode") or "disabled")
    tactic_id_for_quant_entry = str(
        plan.get("tactical_strategy")
        or strategy_frame.get("tactical_strategy")
        or ""
    )
    playbook_for_quant_entry = str(
        plan.get("selected_playbook")
        or plan.get("playbook")
        or strategy_frame.get("playbook")
        or ""
    )
    quant_entry_factor_snapshot = build_factor_snapshot_from_monitor_entry(
        entry_info,
        selected=selected,
        tactic_id=tactic_id_for_quant_entry,
        playbook=playbook_for_quant_entry,
    )
    quant_entry_decision = build_entry_quant_decision(
        entry_info,
        selected=selected,
        factor_snapshot=quant_entry_factor_snapshot,
        state=state,
        tactic_id=tactic_id_for_quant_entry,
        playbook=playbook_for_quant_entry,
    )
    quant_entry_enforcement = build_entry_quant_enforcement(quant_entry_decision)
    entry_info["quant_factor_snapshot"] = dict(quant_entry_factor_snapshot)
    entry_info["entry_quant_decision"] = dict(quant_entry_decision)
    entry_info["quant_entry_enforcement"] = dict(quant_entry_enforcement)
    entry_intent_cooldown_sec = max(0, _to_int((entry_info.get("thresholds") or {}).get("intent_cooldown_sec")))
    cooldown_until = max(0, _to_int(entry_cooldown_map.get(symbol)))
    if cooldown_until > 0 and cooldown_until <= now_epoch_for_entry:
        entry_cooldown_map.pop(symbol, None)
        cooldown_until = 0
    if max(0, _to_int((all_pos_map.get(symbol) or {}).get("qty"))) > 0:
        entry_cooldown_map.pop(symbol, None)
        cooldown_until = 0
    entry_info["intent_cooldown_sec"] = int(entry_intent_cooldown_sec)
    entry_info["intent_cooldown_until"] = int(cooldown_until) if cooldown_until > 0 else None

    max_positions_reached = bool(open_position_count >= max_positions)
    entry_guard = evaluate_entry_guard(
        entry_info=entry_info,
        entry_quality_gate=entry_quality_gate,
        entry_cost_filter=entry_cost_filter,
        selected_already_held=selected_already_held,
        selected_pending_buy=selected_pending_buy,
        max_positions_reached=max_positions_reached,
        closeout_window_active=bool(closeout_window_guard.get("active")),
        buy_blocked_post_exit_cooldown=buy_blocked_post_exit_cooldown,
        entry_intent_cooldown_sec=int(entry_intent_cooldown_sec),
        cooldown_until=int(cooldown_until),
        now_epoch=int(now_epoch_for_entry),
    )
    entry_info = dict(entry_guard.get("entry_info") or entry_info)
    entry_guard_blocked = bool(entry_guard.get("entry_guard_blocked"))
    entry_guard_reason = str(entry_guard.get("entry_guard_reason") or "")
    buy_blocked_open_position = bool(entry_guard.get("buy_blocked_open_position"))
    buy_blocked_closeout_window = bool(entry_guard.get("buy_blocked_closeout_window"))
    buy_blocked_same_symbol = bool(entry_guard.get("buy_blocked_same_symbol"))
    buy_blocked_pending_buy = bool(entry_guard.get("buy_blocked_pending_buy"))
    entry_info["legacy_fallback_used"] = False
    entry_info["decision"] = "WAIT"
    entry_info["cascade_candidate"] = str(plan.get("cascade_candidate") or "")
    if (
        bool(quant_entry_enforcement.get("blocked"))
        and not entry_guard_blocked
        and bool(entry_info.get("triggered"))
    ):
        entry_guard_blocked = True
        entry_guard_reason = str(quant_entry_enforcement.get("reason") or "quant_entry_block")
        entry_info["guard_blocked"] = True
        entry_info["guard_reason"] = entry_guard_reason
        entry_info["reason"] = entry_guard_reason

    if symbol and qty > 0 and not entry_guard_blocked and bool(entry_info.get("triggered")):
        entry_info["intent_submitted"] = True
        if entry_intent_cooldown_sec > 0:
            entry_cooldown_map[symbol] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
            entry_info["intent_cooldown_until"] = int(now_epoch_for_entry + entry_intent_cooldown_sec)
        entry_info["decision"] = "BUY"
    else:
        entry_info["intent_submitted"] = False

    return {
        "state": state,
        "selected": selected,
        "symbol": symbol,
        "qty": int(qty),
        "sizing_info": sizing_info,
        "entry_info": entry_info,
        "entry_guard_blocked": bool(entry_guard_blocked),
        "entry_guard_reason": str(entry_guard_reason),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "buy_blocked_same_symbol": bool(buy_blocked_same_symbol),
        "buy_blocked_pending_buy": bool(buy_blocked_pending_buy),
        "max_positions_reached": bool(max_positions_reached),
        "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
        "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
        "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
        "entry_received_policy": entry_received_policy,
        "entry_applied_policy": entry_applied_policy,
        "effective_policy_trace": effective_policy_trace,
        "entry_cooldown_map": entry_cooldown_map,
        "entry_signal_detected": bool(entry_info.get("triggered")),
    }


def monitor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Monitor.

    Responsibility:
      - emit at most one intent from selected candidate
      - attach optional order status/lifecycle observation from skill DTOs
      - keep stock-selection and execution out of monitor scope
    """
    run_id = str(state.get("run_id") or "").strip() or "monitor-unknown"
    selected = state.get("selected")
    plan = state.get("plan") or {}
    if isinstance(selected, dict) and selected.get("symbol"):
        selected = _monitor_selected_snapshot_for_symbol(state, str(selected.get("symbol") or ""), selected)

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
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
    monitor_policy: Dict[str, Any] = {}
    if isinstance(policy.get("monitor_policy"), dict):
        monitor_policy.update(dict(policy.get("monitor_policy") or {}))
    if isinstance(strategy_monitor_policy.get("position_guards"), dict):
        monitor_policy.update(dict(strategy_monitor_policy.get("position_guards") or {}))
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy.update(dict(strategist_output.get("monitor_policy") or {}))
    if isinstance(state.get("monitor_policy"), dict):
        monitor_policy.update(dict(state.get("monitor_policy") or {}))
    all_pos_map = _position_by_symbol(state)
    _ensure_position_peak_price_map(state, all_pos_map)
    open_position_count = sum(1 for row in all_pos_map.values() if max(0, _to_int((row or {}).get("qty"))) > 0)
    max_positions = _resolve_max_positions(state, policy)
    held_symbols_for_entry = {
        _norm_symbol(sym)
        for sym, row in all_pos_map.items()
        if _norm_symbol(sym) and max(0, _to_int((row or {}).get("qty"))) > 0
    }
    pending_buy_symbols_for_entry = _pending_buy_symbols_from_account_orders(state)
    block_buy_open_position = _resolve_block_buy_when_open_position(state, policy, monitor_policy)
    post_exit_cooldown_sec = _resolve_post_exit_cooldown_sec(state, policy, monitor_policy)
    strategy_frame = _extract_monitor_strategy_frame(state)
    commander_context = (
        dict(strategy_frame.get("commander_context") or {})
        if isinstance(strategy_frame.get("commander_context"), dict)
        else {}
    )
    commander_entry_control = _resolve_commander_entry_control_for_monitor(
        commander_context=commander_context,
        strategy_monitor_policy=strategy_monitor_policy,
        state=state,
    )
    if commander_entry_control:
        commander_context["entry_control"] = dict(commander_entry_control)
        commander_context["commander_entry_control"] = dict(commander_entry_control)
        strategy_frame["commander_context"] = commander_context
    monitor_memory_bias = _resolve_monitor_memory_bias_payload(
        strategy_monitor_policy=strategy_monitor_policy,
        commander_context=commander_context,
        state=state,
    )
    monitor_memory_bias_summary = summarize_monitor_memory_bias(monitor_memory_bias)
    monitor_memory_bias_observation_only = _memory_bias_observation_only(state)
    strategist_plan = (
        dict(strategy_frame.get("strategist_plan") or {})
        if isinstance(strategy_frame.get("strategist_plan"), dict)
        else {}
    )
    policy_provenance = (
        dict(strategy_frame.get("policy_provenance") or {})
        if isinstance(strategy_frame.get("policy_provenance"), dict)
        else {}
    )
    commander_applied_policy = {}
    if isinstance(strategy_monitor_policy.get("applied_policy"), dict) and strategy_monitor_policy.get("applied_policy"):
        commander_applied_policy = dict(strategy_monitor_policy.get("applied_policy") or {})
    elif isinstance(commander_context.get("applied_policy"), dict) and commander_context.get("applied_policy"):
        commander_applied_policy = dict(commander_context.get("applied_policy") or {})
    elif isinstance(state.get("commander_applied_policy"), dict) and state.get("commander_applied_policy"):
        commander_applied_policy = dict(state.get("commander_applied_policy") or {})
    elif isinstance((state.get("commander_decision") or {}).get("applied_policy"), dict):
        commander_applied_policy = dict((state.get("commander_decision") or {}).get("applied_policy") or {})

    entry_policy_contract = build_monitor_entry_policy_contract(
        commander_applied_policy=commander_applied_policy,
        strategist_monitor_entry_policy=(
            dict(strategist_output.get("monitor_entry_policy") or {})
            if isinstance(strategist_output.get("monitor_entry_policy"), dict)
            else {}
        ),
        state_monitor_entry_policy=(
            dict(state.get("monitor_entry_policy") or {})
            if isinstance(state.get("monitor_entry_policy"), dict)
            else {}
        ),
        strategy_monitor_entry_policy=(
            dict(strategy_monitor_policy.get("entry_policy") or {})
            if isinstance(strategy_monitor_policy.get("entry_policy"), dict)
            else {}
        ),
    )
    entry_policy_input: Dict[str, Any] = dict(entry_policy_contract.get("selected_policy") or {})
    if commander_entry_control:
        entry_policy_input["commander_entry_control"] = dict(commander_entry_control)
        entry_policy_input["entry_control"] = dict(commander_entry_control)
    entry_policy_origin = str(entry_policy_contract.get("selected_source") or "monitor_policy")
    buy_blocked_open_position = False
    buy_blocked_same_symbol = False
    buy_blocked_pending_buy = False
    max_positions_reached = bool(open_position_count >= max_positions)
    buy_blocked_post_exit_cooldown = False
    buy_blocked_closeout_window = False
    post_exit_cooldown_remaining_sec = 0
    entry_info: Dict[str, Any] = {
        "enabled": True,
        "evaluated": False,
        "triggered": False,
        "reason": "",
        "pattern": "",
        "signal_chain": [],
        "metrics": {},
        "thresholds": {},
        "guard_blocked": False,
        "guard_reason": "",
        "intent_cooldown_sec": 0,
        "intent_cooldown_until": None,
        "intent_submitted": False,
        "legacy_fallback_used": False,
    }
    entry_signal_detected = False
    entry_guard_blocked = False
    entry_guard_reason = ""
    entry_applied_policy: Dict[str, Any] = {}
    entry_received_policy: Dict[str, Any] = {}
    effective_policy_trace: Dict[str, Any] = {}
    hold_bias_result: Dict[str, Any] = {"controls": {}, "applied": False, "deltas": []}
    exit_bias_result: Dict[str, Any] = {"policy": {}, "applied": False, "deltas": []}
    entry_symbol = _norm_symbol(selected.get("symbol")) if isinstance(selected, dict) and selected.get("symbol") else ""
    entry_cooldown_map = state.get("_monitor_entry_cooldown_until")
    if not isinstance(entry_cooldown_map, dict):
        entry_cooldown_map = {}
    now_epoch_for_entry = _resolve_now_epoch(state)
    state = _refresh_post_exit_shadow_watchlist_minute_rows(
        state,
        now_epoch=now_epoch_for_entry,
    )
    try:
        record_raw_input(
            run_id=run_id,
            agent="monitor",
            stage="entry_exit_decision",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "selected_snapshot": (
                    {
                        "symbol": str(selected.get("symbol") or ""),
                        "score": selected.get("score"),
                        "risk_score": selected.get("risk_score"),
                        "confidence": selected.get("confidence"),
                        "price_source": str(selected.get("_monitor_price_source") or ""),
                        "feature_source": str(selected.get("_monitor_feature_source") or ""),
                    }
                    if isinstance(selected, dict)
                    else {}
                ),
                "open_position_count": int(open_position_count),
                "positions": {
                    str(k): {"qty": _to_int((v or {}).get("qty")), "avg_price": (v or {}).get("avg_price")}
                    for k, v in list(all_pos_map.items())[:20]
                },
                "monitor_policy": dict(monitor_policy),
                "strategist_guidance": {
                    "playbook": str(strategist_output.get("playbook") or ""),
                    "monitor_guidance": str(strategist_output.get("monitor_guidance") or ""),
                    "risk_tone": str(strategist_output.get("risk_tone") or ""),
                    "trade_aggressiveness": str(strategist_output.get("trade_aggressiveness") or ""),
                },
                "commander_context": {
                    "monitor_mission": str(commander_context.get("monitor_mission") or ""),
                    "flow_instruction": str(commander_context.get("flow_instruction") or ""),
                    "command_intent": str(commander_context.get("command_intent") or ""),
                    "risk_mode": str(commander_context.get("risk_mode") or ""),
                    "no_trade_reason_code": str(commander_context.get("no_trade_reason_code") or ""),
                    "llm_policy": str(commander_context.get("llm_policy") or ""),
                    "source_priority": list(commander_context.get("source_priority") or []),
                    "entry_control": dict(commander_entry_control),
                },
                "strategist_plan": {
                    "selected_playbook": str(strategist_plan.get("selected_playbook") or ""),
                    "entry_plan": dict(strategist_plan.get("entry_plan") or {}),
                    "exit_plan": dict(strategist_plan.get("exit_plan") or {}),
                    "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
                    "strategy_summary": str(strategist_plan.get("strategy_summary") or ""),
                },
            },
            decision_link={"stage": "monitor_input_snapshot"},
        )
    except Exception:
        pass

    intents = []
    sizing_info: Dict[str, Any] = {
        "enabled": False,
        "evaluated": False,
        "qty": 1,
        "reason": "disabled",
        "price": None,
        "cash": None,
        "inputs": {},
    }
    scanner_selected_snapshot = dict(selected) if isinstance(selected, dict) else {}
    entry_cascade_config = _resolve_entry_candidate_cascade_config(commander_entry_control)
    entry_cascade_max_rank = int(entry_cascade_config.get("max_priority_rank") if entry_cascade_config.get("max_priority_rank") not in (None, "") else 10)
    entry_cascade_max_runner_ups = int(entry_cascade_config.get("max_runner_ups") if entry_cascade_config.get("max_runner_ups") not in (None, "") else 9)
    entry_candidate_cascade: Dict[str, Any] = {
        "attempted": False,
        "eligible": False,
        "reason": "",
        "top_pick_symbol": "",
        "max_priority_rank": int(entry_cascade_max_rank),
        "max_runner_ups": int(entry_cascade_max_runner_ups),
        "cascade_enabled": bool(entry_cascade_config.get("cascade_enabled", True)),
        "cascade_allowed_reasons": list(entry_cascade_config.get("cascade_allowed_reasons") or []),
        "cascade_blocked_reasons": list(entry_cascade_config.get("cascade_blocked_reasons") or []),
        "control_source": str(entry_cascade_config.get("source") or "default"),
        "control_mode": str(entry_cascade_config.get("mode") or "default"),
        "runner_up_symbols": [],
        "skipped": [],
        "fallback_used": False,
        "fallback_to_symbol": "",
        "fallback_trace": [],
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "excluded_symbols": sorted(held_symbols_for_entry | pending_buy_symbols_for_entry),
    }
    if isinstance(selected, dict) and selected.get("symbol"):
        top_pick_result = _evaluate_monitor_entry_candidate(
            state=state,
            selected=dict(selected),
            plan=plan,
            policy=policy,
            monitor_policy=monitor_policy,
            strategy_monitor_policy=strategy_monitor_policy,
            strategy_frame=strategy_frame,
            commander_context=commander_context,
            entry_policy_contract=entry_policy_contract,
            entry_policy_input=entry_policy_input,
            entry_policy_origin=entry_policy_origin,
            all_pos_map=all_pos_map,
            open_position_count=open_position_count,
            block_buy_open_position=block_buy_open_position,
            post_exit_cooldown_sec=post_exit_cooldown_sec,
            entry_cooldown_map=entry_cooldown_map,
            now_epoch_for_entry=now_epoch_for_entry,
            prefer_fresh_minute_runner=False,
        )
        state = top_pick_result.get("state") if isinstance(top_pick_result.get("state"), dict) else state
        selected = dict(top_pick_result.get("selected") or selected)
        sizing_info = dict(top_pick_result.get("sizing_info") or sizing_info)
        entry_info = dict(top_pick_result.get("entry_info") or entry_info)
        entry_guard_blocked = bool(top_pick_result.get("entry_guard_blocked"))
        entry_guard_reason = str(top_pick_result.get("entry_guard_reason") or "")
        buy_blocked_open_position = bool(top_pick_result.get("buy_blocked_open_position"))
        buy_blocked_same_symbol = bool(top_pick_result.get("buy_blocked_same_symbol"))
        buy_blocked_pending_buy = bool(top_pick_result.get("buy_blocked_pending_buy"))
        max_positions_reached = bool(top_pick_result.get("max_positions_reached"))
        buy_blocked_post_exit_cooldown = bool(top_pick_result.get("buy_blocked_post_exit_cooldown"))
        buy_blocked_closeout_window = bool(top_pick_result.get("buy_blocked_closeout_window"))
        post_exit_cooldown_remaining_sec = int(top_pick_result.get("post_exit_cooldown_remaining_sec") or 0)
        entry_received_policy = dict(top_pick_result.get("entry_received_policy") or {})
        entry_applied_policy = dict(top_pick_result.get("entry_applied_policy") or {})
        effective_policy_trace = dict(top_pick_result.get("effective_policy_trace") or {})
        entry_cooldown_map = dict(top_pick_result.get("entry_cooldown_map") or entry_cooldown_map)
        entry_signal_detected = bool(top_pick_result.get("entry_signal_detected"))
        symbol = str(top_pick_result.get("symbol") or "")
        qty = int(top_pick_result.get("qty") or 0)
        entry_candidate_cascade["top_pick_symbol"] = symbol
        entry_candidate_cascade["top_pick_triggered"] = bool(entry_info.get("triggered"))
        entry_candidate_cascade["top_pick_reason"] = str(entry_info.get("reason") or "")
        entry_candidate_cascade["top_pick_guard_blocked"] = bool(entry_guard_blocked)

        cascade_plan = build_entry_candidate_cascade_plan(
            selected_symbol=symbol,
            ranked_candidates=[row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)],
            scanner_output=state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {},
            open_position_count=open_position_count,
            max_positions=max_positions,
            entry_guard_blocked=entry_guard_blocked,
            entry_guard_reason=entry_guard_reason,
            entry_triggered=bool(entry_info.get("triggered")),
            entry_reason=str(entry_info.get("reason") or ""),
            max_runner_ups=int(entry_cascade_max_runner_ups),
            cascade_enabled=bool(entry_cascade_config.get("cascade_enabled", True)),
            cascade_allowed_reasons=list(entry_cascade_config.get("cascade_allowed_reasons") or []),
            cascade_blocked_reasons=list(entry_cascade_config.get("cascade_blocked_reasons") or []),
            hard_block_override_enabled=bool(entry_cascade_config.get("hard_block_override_enabled")),
            hard_block_override_reason=str(entry_cascade_config.get("hard_block_override_reason") or ""),
            excluded_symbols=sorted(held_symbols_for_entry | pending_buy_symbols_for_entry),
        )
        entry_candidate_cascade.update(dict(cascade_plan))
        fallback_trace = list(entry_candidate_cascade.get("fallback_trace") or [])
        if bool(cascade_plan.get("attempted")):
            for runner_row in list(cascade_plan.get("runner_rows") or []):
                if not isinstance(runner_row, dict):
                    continue
                runner_symbol = _norm_symbol(runner_row.get("symbol"))
                if not runner_symbol:
                    continue
                runner_selected = _monitor_selected_snapshot_for_symbol(state, runner_symbol, dict(runner_row))
                runner_result = _evaluate_monitor_entry_candidate(
                    state=state,
                    selected=runner_selected,
                    plan=plan,
                    policy=policy,
                    monitor_policy=monitor_policy,
                    strategy_monitor_policy=strategy_monitor_policy,
                    strategy_frame=strategy_frame,
                    commander_context=commander_context,
                    entry_policy_contract=entry_policy_contract,
                    entry_policy_input=entry_policy_input,
                    entry_policy_origin=entry_policy_origin,
                    all_pos_map=all_pos_map,
                    open_position_count=open_position_count,
                    block_buy_open_position=block_buy_open_position,
                    post_exit_cooldown_sec=post_exit_cooldown_sec,
                    entry_cooldown_map=entry_cooldown_map,
                    now_epoch_for_entry=now_epoch_for_entry,
                    prefer_fresh_minute_runner=True,
                )
                state = runner_result.get("state") if isinstance(runner_result.get("state"), dict) else state
                entry_cooldown_map = dict(runner_result.get("entry_cooldown_map") or entry_cooldown_map)
                runner_entry = dict(runner_result.get("entry_info") or {})
                runner_metrics = (
                    dict(runner_entry.get("metrics") or {})
                    if isinstance(runner_entry.get("metrics"), dict)
                    else {}
                )
                runner_scores = (
                    dict(runner_entry.get("condition_scores") or {})
                    if isinstance(runner_entry.get("condition_scores"), dict)
                    else {}
                )
                fallback_trace.append(
                    {
                        "symbol": runner_symbol,
                        "rank": runner_row.get("rank") or runner_row.get("priority_rank"),
                        "score_total": runner_row.get("score_total") or runner_row.get("score"),
                        "triggered": bool(runner_entry.get("triggered")),
                        "reason": str(runner_entry.get("reason") or ""),
                        "primary_failure_axis": str(runner_entry.get("primary_failure_axis") or ""),
                        "transition_readiness_score": runner_entry.get("transition_readiness_score")
                        or runner_metrics.get("transition_readiness_score")
                        or runner_scores.get("transition_readiness_score"),
                        "vwap_distance": runner_metrics.get("vwap_distance"),
                        "max_extended_from_vwap_pct": (
                            (runner_entry.get("thresholds") or {}).get("max_extended_from_vwap_pct")
                            if isinstance(runner_entry.get("thresholds"), dict)
                            else None
                        ),
                        "volume_ratio": runner_metrics.get("volume_ratio"),
                        "breakout_ok": runner_metrics.get("breakout_ok"),
                        "pullback_ok": runner_metrics.get("pullback_ok"),
                        "extension_ok": runner_metrics.get("extension_ok"),
                        "confidence_score": runner_scores.get("confidence_score")
                        or runner_metrics.get("confidence_score"),
                        "confidence_threshold": runner_scores.get("confidence_threshold")
                        or runner_metrics.get("confidence_threshold"),
                        "minute_source_present": runner_metrics.get("minute_source_present"),
                        "minute_refetch_succeeded": runner_metrics.get("minute_refetch_succeeded"),
                        "minute_cache_fallback_used": runner_metrics.get("minute_cache_fallback_used"),
                        "guard_blocked": bool(runner_result.get("entry_guard_blocked")),
                    }
                )
                if not bool(runner_entry.get("intent_submitted")):
                    continue
                runner_quality = evaluate_runner_up_entry_quality(
                    runner_row=runner_row,
                    runner_entry=runner_entry,
                    runner_guard_blocked=bool(runner_result.get("entry_guard_blocked")),
                )
                if fallback_trace and isinstance(fallback_trace[-1], dict):
                    fallback_trace[-1]["runner_up_quality_gate"] = dict(runner_quality)
                if not bool(runner_quality.get("passed")):
                    runner_entry["intent_submitted"] = False
                    runner_entry["triggered"] = False
                    runner_entry["reason"] = str(runner_quality.get("reason") or "runner_up_quality_gate_failed")
                    runner_entry["runner_up_quality_gate"] = dict(runner_quality)
                    if fallback_trace and isinstance(fallback_trace[-1], dict):
                        fallback_trace[-1]["triggered"] = False
                        fallback_trace[-1]["reason"] = str(runner_entry.get("reason") or "")
                        fallback_trace[-1]["runner_up_quality_blocked"] = True
                    continue
                runner_rank = int(_to_int(runner_row.get("rank") or runner_row.get("priority_rank")))
                runner_subtype = _classify_vwap_reclaim_pullback_candidate(
                    candidate_row=dict(runner_row),
                    selected_rank=runner_rank,
                    fallback_used=True,
                    entry_info=runner_entry,
                )
                if fallback_trace and isinstance(fallback_trace[-1], dict):
                    fallback_trace[-1]["pullback_evidence_profile"] = dict(runner_subtype)
                if not bool(runner_subtype.get("fallback_qualified")):
                    runner_entry["intent_submitted"] = False
                    runner_entry["triggered"] = False
                    runner_entry["reason"] = str(
                        runner_subtype.get("fallback_rejection_reason")
                        or "weak_fallback_pullback"
                    )
                    runner_entry["pullback_evidence_profile"] = dict(runner_subtype)
                    runner_entry["weak_fallback_blocked"] = True
                    if fallback_trace and isinstance(fallback_trace[-1], dict):
                        fallback_trace[-1]["triggered"] = False
                        fallback_trace[-1]["reason"] = str(runner_entry.get("reason") or "")
                        fallback_trace[-1]["weak_fallback_blocked"] = True
                    continue
                entry_candidate_cascade["fallback_used"] = True
                entry_candidate_cascade["fallback_to_symbol"] = runner_symbol
                entry_candidate_cascade["fallback_to_rank"] = runner_row.get("rank") or runner_row.get("priority_rank")
                entry_candidate_cascade["pullback_evidence_profile"] = dict(runner_subtype)
                entry_candidate_cascade["fallback_candidate_subtype"] = str(runner_subtype.get("subtype") or "")
                entry_candidate_cascade["fallback_from_symbol"] = symbol
                selected = dict(runner_result.get("selected") or runner_selected)
                sizing_info = dict(runner_result.get("sizing_info") or sizing_info)
                entry_info = runner_entry
                entry_guard_blocked = bool(runner_result.get("entry_guard_blocked"))
                entry_guard_reason = str(runner_result.get("entry_guard_reason") or "")
                buy_blocked_open_position = bool(runner_result.get("buy_blocked_open_position"))
                buy_blocked_same_symbol = bool(runner_result.get("buy_blocked_same_symbol"))
                buy_blocked_pending_buy = bool(runner_result.get("buy_blocked_pending_buy"))
                max_positions_reached = bool(runner_result.get("max_positions_reached"))
                buy_blocked_post_exit_cooldown = bool(runner_result.get("buy_blocked_post_exit_cooldown"))
                buy_blocked_closeout_window = bool(runner_result.get("buy_blocked_closeout_window"))
                post_exit_cooldown_remaining_sec = int(runner_result.get("post_exit_cooldown_remaining_sec") or 0)
                entry_received_policy = dict(runner_result.get("entry_received_policy") or {})
                entry_applied_policy = dict(runner_result.get("entry_applied_policy") or {})
                effective_policy_trace = dict(runner_result.get("effective_policy_trace") or {})
                entry_signal_detected = bool(runner_result.get("entry_signal_detected"))
                symbol = str(runner_result.get("symbol") or runner_symbol)
                qty = int(runner_result.get("qty") or 0)
                entry_info["fallback_from_symbol"] = entry_candidate_cascade.get("fallback_from_symbol")
                entry_info["fallback_to_symbol"] = runner_symbol
                entry_info["pullback_evidence_profile"] = dict(runner_subtype)
                break
        entry_candidate_cascade["fallback_trace"] = fallback_trace
        entry_candidate_cascade["final_selected_symbol"] = symbol
        entry_candidate_cascade["final_selected_rank"] = (
            entry_candidate_cascade.get("fallback_to_rank")
            or selected.get("rank")
            or selected.get("priority_rank")
            or selected.get("scanner_rank")
        )

        if symbol and qty > 0 and not entry_guard_blocked and bool(entry_info.get("intent_submitted")):
            entry_metrics_for_order = (
                dict(entry_info.get("metrics") or {})
                if isinstance(entry_info.get("metrics"), dict)
                else {}
            )
            entry_cost_filter_for_order = (
                dict(entry_info.get("entry_cost_filter") or {})
                if isinstance(entry_info.get("entry_cost_filter"), dict)
                else {}
            )
            order_price_source = ""
            order_price = 0.0
            for source_name, candidate in (
                ("entry_cost_filter.price", entry_cost_filter_for_order.get("price")),
                ("selected.price", selected.get("price")),
                ("entry.metrics.current_price", entry_metrics_for_order.get("current_price")),
                ("entry.metrics.price", entry_metrics_for_order.get("price")),
                ("sizing.price", sizing_info.get("price")),
            ):
                candidate_price = _to_float(candidate)
                if candidate_price > 0.0:
                    order_price = float(candidate_price)
                    order_price_source = source_name
                    break
            intent = {
                "symbol": symbol,
                "side": "BUY",
                "qty": int(qty),
                "price": order_price if order_price > 0.0 else None,
                "thesis": str(plan.get("thesis") or ""),
                "meta": {
                    "score": selected.get("score"),
                    "risk_score": selected.get("risk_score"),
                    "confidence": selected.get("confidence"),
                    "price": order_price if order_price > 0.0 else None,
                    "current_price": order_price if order_price > 0.0 else None,
                    "price_source": order_price_source,
                    "order_price_source": order_price_source,
                    "entry_signal_source": "monitor_intraday_entry",
                    "entry_pattern": str(entry_info.get("pattern") or ""),
                    "entry_reason": str(entry_info.get("reason") or ""),
                    "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                    "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
                    "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
                    "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
                    "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
                    "entry_metrics": dict(entry_info.get("metrics") or {}),
                    "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
                    "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
                    "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
                    "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
                    "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
                    "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
                    "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
                    "entry_lane": str(entry_info.get("entry_lane") or "strict"),
                    "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
                    "entry_quality_gate": dict(entry_info.get("entry_quality_gate") or {}),
                    "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
                    "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
                    "cost_drag_pct": entry_info.get("cost_drag_pct"),
                    "entry_scoring": {
                        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
                        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
                        "total_score": entry_info.get("total_score"),
                        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
                        "entry_threshold": entry_info.get("entry_threshold"),
                        "score_passed": bool(entry_info.get("score_passed")),
                        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
                        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
                        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
                    },
                    "entry_candidate_cascade": dict(entry_candidate_cascade),
                    "quant_factor_snapshot": dict(entry_info.get("quant_factor_snapshot") or {}),
                    "entry_quant_decision": dict(entry_info.get("entry_quant_decision") or {}),
                    "quant_entry_enforcement": dict(entry_info.get("quant_entry_enforcement") or {}),
                },
            }
            if bool(sizing_info.get("enabled")):
                intent["meta"]["sizing"] = {
                    "reason": str(sizing_info.get("reason") or ""),
                    "price": sizing_info.get("price"),
                    "cash": sizing_info.get("cash"),
                    "inputs": sizing_info.get("inputs"),
                }
            if post_exit_cooldown_sec > 0:
                intent["meta"]["post_exit_cooldown_sec"] = int(post_exit_cooldown_sec)
            if int(entry_info.get("intent_cooldown_sec") or 0) > 0:
                intent["meta"]["entry_intent_cooldown_sec"] = int(entry_info.get("intent_cooldown_sec") or 0)
            intents = [intent]
        else:
            intents = []
    if bool(intents) and open_position_count >= max_positions:
        intents = []
        buy_blocked_open_position = True
        entry_info["guard_blocked"] = True
        entry_info["guard_reason"] = "max_positions_reached"
        entry_info["max_positions_reached"] = True
        entry_info["decision"] = "WAIT"
    state["_monitor_entry_cooldown_until"] = entry_cooldown_map
    if isinstance(selected, dict) and selected.get("symbol"):
        state["selected"] = dict(selected)
    if isinstance(scanner_selected_snapshot, dict) and scanner_selected_snapshot:
        state["scanner_selected_snapshot"] = dict(scanner_selected_snapshot)
    state["monitor_entry_cascade"] = dict(entry_candidate_cascade)

    # Optional M29-2 exit policy (default disabled for backward compatibility).
    use_exit_policy = _resolve_use_exit_policy(state, policy)
    exit_policy_base = _resolve_exit_policy_config(state, policy)
    exit_info: Dict[str, Any] = {
        "enabled": bool(use_exit_policy),
        "evaluated": False,
        "triggered": False,
        "reason": "",
        "symbol": None,
        "qty": 0,
        "pnl_ratio": None,
        "price": None,
        "avg_price": None,
        "position_age_seconds": None,
        "exit_signal_detected": False,
        "exit_confirm_count": 0,
        "min_hold_blocked": False,
        "sell_cooldown_blocked": False,
        "sell_cooldown_until": None,
        "pending_exit_lock_active": False,
        "pending_exit_lock_until": None,
        "monitor_reason": "hold",
        "emergency_exit": False,
    }
    hold_bias_result: Dict[str, Any] = {"applied": False, "deltas": []}
    exit_bias_result: Dict[str, Any] = {"applied": False, "deltas": []}
    selected_snapshot = dict(selected) if isinstance(selected, dict) else {}
    selected_symbol = _norm_symbol(selected_snapshot.get("symbol"))
    has_open_position_for_exit = any(
        max(0, _to_int((row or {}).get("qty"))) > 0
        for row in list(all_pos_map.values())
    )
    if use_exit_policy and (selected_symbol or has_open_position_for_exit):
        pos_map = all_pos_map
        preliminary_exit_symbol = _select_exit_symbol(
            selected_symbol,
            pos_map,
            state=state,
            selected=selected_snapshot,
            policy=policy,
            exit_policy_base=exit_policy_base,
        )
        exit_strategy_frame = _position_strategy_frame_for_symbol(
            state,
            preliminary_exit_symbol,
            strategy_frame,
        )
        min_hold_sec = _resolve_min_hold_sec(state, monitor_policy)
        sell_cooldown_sec = _resolve_sell_cooldown_sec(state, monitor_policy)
        confirm_ticks = _resolve_exit_confirm_ticks(state, monitor_policy)
        frame_applied = _apply_monitor_strategy_frame(
            min_hold_sec=min_hold_sec,
            sell_cooldown_sec=sell_cooldown_sec,
            confirm_ticks=confirm_ticks,
            frame=exit_strategy_frame,
        )
        min_hold_sec = int(frame_applied.get("min_hold_sec") or min_hold_sec)
        sell_cooldown_sec = int(frame_applied.get("sell_cooldown_sec") or sell_cooldown_sec)
        confirm_ticks = int(frame_applied.get("confirm_ticks") or confirm_ticks)
        hold_bias_result = apply_monitor_memory_bias_to_hold_controls(
            min_hold_sec=min_hold_sec,
            sell_cooldown_sec=sell_cooldown_sec,
            confirm_ticks=confirm_ticks,
            monitor_memory_bias=monitor_memory_bias,
        )
        hold_bias_observed_result = dict(hold_bias_result)
        if monitor_memory_bias_observation_only:
            hold_bias_result = {
                "controls": {
                    "min_hold_sec": int(min_hold_sec),
                    "sell_cooldown_sec": int(sell_cooldown_sec),
                    "confirm_ticks": int(confirm_ticks),
                },
                "applied": False,
                "deltas": [],
                "observation_only": True,
                "observed_deltas": list(hold_bias_observed_result.get("deltas") or []),
            }
        hold_controls = dict(hold_bias_result.get("controls") or {})
        min_hold_sec = int(hold_controls.get("min_hold_sec") or min_hold_sec)
        sell_cooldown_sec = int(hold_controls.get("sell_cooldown_sec") or sell_cooldown_sec)
        confirm_ticks = int(hold_controls.get("confirm_ticks") or confirm_ticks)
        exit_policy_harmonized = _harmonize_exit_policy_with_monitor_guards(
            exit_policy_base=exit_policy_base,
            min_hold_sec=min_hold_sec,
        )
        effective_exit_policy_base = dict(exit_policy_harmonized.get("policy") or {})
        effective_exit_policy_base["policy_source"] = str(
            effective_exit_policy_base.get("policy_source")
            or effective_exit_policy_base.get("effective_policy_source")
            or "monitor_effective_exit_policy"
        )
        effective_exit_policy_base["effective_policy_source"] = str(
            effective_exit_policy_base.get("effective_policy_source")
            or effective_exit_policy_base.get("policy_source")
            or "monitor_effective_exit_policy"
        )
        exit_policy_guard_adjustments = list(exit_policy_harmonized.get("adjustments") or [])
        exit_policy_strategy = _apply_exit_policy_strategy_frame(
            state=state,
            exit_policy_base=effective_exit_policy_base,
            selected=selected_snapshot,
            position=pos_map.get(selected_symbol, {}) if selected_symbol else {},
            frame=frame_applied,
        )
        effective_exit_policy_base = dict(exit_policy_strategy.get("policy") or effective_exit_policy_base)
        effective_exit_policy_base["policy_source"] = str(
            effective_exit_policy_base.get("policy_source")
            or effective_exit_policy_base.get("effective_policy_source")
            or "monitor_effective_exit_policy"
        )
        effective_exit_policy_base["effective_policy_source"] = str(
            effective_exit_policy_base.get("effective_policy_source")
            or effective_exit_policy_base.get("policy_source")
            or "monitor_effective_exit_policy"
        )
        exit_policy_guard_adjustments.extend(list(exit_policy_strategy.get("adjustments") or []))
        exit_bias_result = apply_monitor_memory_bias_to_exit_policy(
            exit_policy=effective_exit_policy_base,
            monitor_memory_bias=monitor_memory_bias,
        )
        exit_bias_observed_result = dict(exit_bias_result)
        if monitor_memory_bias_observation_only:
            exit_bias_result = {
                "policy": dict(effective_exit_policy_base),
                "applied": False,
                "deltas": [],
                "observation_only": True,
                "observed_deltas": list(exit_bias_observed_result.get("deltas") or []),
            }
        effective_exit_policy_base = dict(exit_bias_result.get("policy") or effective_exit_policy_base)
        if bool(hold_bias_result.get("applied")):
            for row in list(hold_bias_result.get("deltas") or [])[:6]:
                exit_policy_guard_adjustments.append(
                    f"commander_memory_bias_hold:{str((row or {}).get('field') or '')}:{(row or {}).get('from')}->{(row or {}).get('to')}"
                )
        if bool(exit_bias_result.get("applied")):
            for row in list(exit_bias_result.get("deltas") or [])[:6]:
                exit_policy_guard_adjustments.append(
                    f"commander_memory_bias_exit:{str((row or {}).get('field') or '')}:{(row or {}).get('from')}->{(row or {}).get('to')}"
                )
        now_epoch = _resolve_now_epoch(state)
        eod_carry_sweep = _persist_eod_carry_decisions_for_open_positions(
            state=state,
            pos_map=pos_map,
            selected=selected_snapshot,
            exit_policy_base=effective_exit_policy_base,
            frame=frame_applied,
            now_epoch=now_epoch,
        )
        symbol = _select_exit_symbol(
            selected_symbol,
            pos_map,
            state=state,
            selected=selected_snapshot,
            policy=policy,
            exit_policy_base=effective_exit_policy_base,
        )
        if preliminary_exit_symbol and symbol != preliminary_exit_symbol:
            exit_policy_guard_adjustments.append(
                f"exit_symbol_reselected_after_policy:{preliminary_exit_symbol}->{symbol}"
            )
        selected_for_exit: Dict[str, Any] = dict(selected_snapshot)
        if symbol and symbol != selected_symbol:
            selected_for_exit = {"symbol": symbol}
        features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
        pending_order_symbols_for_exit = _pending_order_symbols_from_account_orders(state)
        selected_pending_order_for_exit = bool(
            symbol
            and (
                _norm_symbol(symbol) in pending_order_symbols_for_exit
                or _features_pending_order_count(features) > 0
            )
        )
        pos = pos_map.get(symbol, {})
        qty = max(0, _to_int(pos.get("qty")))
        entry_intent_symbol = _norm_symbol((intents[0] or {}).get("symbol")) if intents else ""
        # Suppress fresh BUY only when it targets the same symbol as an existing position.
        if qty > 0 and entry_intent_symbol and entry_intent_symbol == _norm_symbol(symbol):
            intents = []
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=effective_exit_policy_base,
        )
        avg_price = _to_float(decision.get("_avg_price"))
        price = decision.get("_price")
        hold_sec = _to_int(decision.get("_hold_sec"))
        if hold_sec <= 0:
            hold_sec = _position_hold_seconds(state, symbol, pos)
        eod_carry = _evaluate_overnight_carry_decision(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=effective_exit_policy_base,
            primary_decision=decision,
            frame=frame_applied,
            hold_sec=hold_sec,
        )
        if bool(eod_carry.get("approved")):
            decision["triggered"] = False
            decision["reason"] = "carry_overnight_approved"
        if qty > 0 and bool(eod_carry.get("evaluated")):
            _persist_overnight_decision(
                state,
                symbol=symbol,
                decision={
                    "approved": bool(eod_carry.get("approved")),
                    "action": str(eod_carry.get("action") or ""),
                    "reason": str(eod_carry.get("reason") or ""),
                    "minutes_to_close": eod_carry.get("minutes_to_close"),
                    "cutoff_min": eod_carry.get("cutoff_min"),
                    "positive_signals": list(eod_carry.get("positive_signals") or []),
                    "blockers": list(eod_carry.get("blockers") or []),
                    "carry_calendar": dict(eod_carry.get("carry_calendar") or {}),
                    "weekend_carry": bool(eod_carry.get("weekend_carry")),
                    "allow_weekend_carry": bool(eod_carry.get("allow_weekend_carry")),
                    "holding_gap_days": eod_carry.get("holding_gap_days"),
                    "decided_at_epoch": int(now_epoch),
                    "symbol": str(symbol or ""),
                },
            )
        elif qty <= 0:
            _persist_overnight_decision(state, symbol=symbol, clear=True)
        confirm_map = state.get("_monitor_exit_confirm")
        if not isinstance(confirm_map, dict):
            confirm_map = {}
        cooldown_map = state.get("_monitor_sell_cooldown_until")
        if not isinstance(cooldown_map, dict):
            cooldown_map = {}
        pending_exit_lock = state.get("_monitor_pending_exit_lock")
        if not isinstance(pending_exit_lock, dict):
            pending_exit_lock = {}
        prev_qty_map = state.get("_monitor_prev_position_qty")
        if not isinstance(prev_qty_map, dict):
            prev_qty_map = {}

        prev_qty = max(0, _to_int(prev_qty_map.get(symbol)))
        if prev_qty > 0 and qty <= 0 and sell_cooldown_sec > 0:
            cooldown_map[symbol] = int(now_epoch + sell_cooldown_sec)
        prev_qty_map[symbol] = int(qty)

        cooldown_until = max(0, _to_int(cooldown_map.get(symbol)))
        if cooldown_until > 0 and cooldown_until <= now_epoch:
            cooldown_map.pop(symbol, None)
            cooldown_until = 0

        lock_until = max(0, _to_int(pending_exit_lock.get(symbol)))
        if lock_until > 0 and lock_until <= now_epoch:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        confirm_key = f"{symbol}:{str(decision.get('reason') or '').strip()}"
        confirm_count = 0
        sell_guard_blocked = False
        sell_guard_reason = ""
        hold_block_reason = str(decision.get("hold_block_reason") or "")
        monitor_reason = "hold"
        min_hold_blocked = False
        sell_cooldown_blocked = False
        exit_signal_detected = bool(decision.get("triggered"))
        emergency_exit = _is_emergency_exit_reason(str(decision.get("reason") or ""))
        hard_exit = _is_hard_exit_reason(str(decision.get("reason") or ""))
        decision_reason = str(decision.get("reason") or "").strip()
        decision_thresholds = (
            decision.get("thresholds")
            if isinstance(decision.get("thresholds"), dict)
            else {}
        )
        effective_confirm_ticks = max(1, int(confirm_ticks))
        peak_drawdown_confirm_ticks = 0
        if decision_reason == "peak_drawdown":
            peak_drawdown_confirm_ticks = max(
                1,
                _to_int(decision_thresholds.get("confirm_required_for_peak_drawdown") or 2),
            )
            if bool(decision.get("peak_drawdown_profit_protection_urgent")):
                peak_drawdown_confirm_ticks = 1
                effective_confirm_ticks = 1
            else:
                effective_confirm_ticks = max(effective_confirm_ticks, peak_drawdown_confirm_ticks)

        if exit_signal_detected:
            if qty <= 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_no_position"
                monitor_reason = "no_position"
            elif _is_trueish(state.get("execution_pending")):
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_execution_pending"
                monitor_reason = "pending_exit_lock"
            elif selected_pending_order_for_exit:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_open_order_pending"
                monitor_reason = "pending_exit_lock"
            elif lock_until > now_epoch:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_pending_exit_lock"
                monitor_reason = "pending_exit_lock"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and min_hold_sec > 0 and hold_sec > 0 and hold_sec < min_hold_sec:
                sell_guard_blocked = True
                min_hold_blocked = True
                sell_guard_reason = f"sell_guard_min_hold:{hold_sec}s<{min_hold_sec}s"
                monitor_reason = "min_hold_active"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and sell_cooldown_sec > 0 and cooldown_until > now_epoch:
                sell_guard_blocked = True
                sell_cooldown_blocked = True
                sell_guard_reason = f"sell_guard_cooldown:{max(0, cooldown_until - now_epoch)}s_remaining"
                monitor_reason = "cooldown_active"
                hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            elif not emergency_exit and not hard_exit and effective_confirm_ticks > 1:
                confirm_count = _to_int(confirm_map.get(confirm_key)) + 1
                confirm_map[confirm_key] = int(confirm_count)
                if confirm_count < int(effective_confirm_ticks):
                    sell_guard_blocked = True
                    sell_guard_reason = f"exit_confirmation_pending:{confirm_count}/{effective_confirm_ticks}"
                    monitor_reason = "exit_signal_pending_confirmation"
                    hold_block_reason = f"{str(decision.get('reason') or 'exit_signal')}:{sell_guard_reason}"
            if not sell_guard_blocked and not monitor_reason:
                monitor_reason = "confirmed_exit_signal"
        else:
            _clear_symbol_confirm_keys(confirm_map, symbol)
            if bool(eod_carry.get("approved")) and qty > 0:
                monitor_reason = "eod_carry_approved"
            elif qty <= 0 and bool(entry_info.get("guard_blocked")):
                monitor_reason = str(entry_info.get("guard_reason") or "entry_guard_blocked")
            elif qty <= 0 and str(entry_info.get("reason") or "").strip():
                monitor_reason = str(entry_info.get("reason") or "entry_wait")
            elif qty <= 0 and bool(entry_info.get("triggered")) and bool(entry_info.get("intent_submitted")):
                monitor_reason = str(entry_info.get("reason") or "entry_signal_confirmed")
            else:
                monitor_reason = "hold" if qty > 0 else "no_position"

        if not sell_guard_blocked and exit_signal_detected:
            if not emergency_exit and not hard_exit and confirm_count <= 0:
                confirm_count = max(1, int(effective_confirm_ticks))
            _clear_symbol_confirm_keys(confirm_map, symbol)
            lock_sec = max(30, int(sell_cooldown_sec))
            pending_exit_lock[symbol] = int(now_epoch + lock_sec)
            lock_until = int(now_epoch + lock_sec)
            if sell_cooldown_sec > 0:
                cooldown_until = int(now_epoch + sell_cooldown_sec)
                cooldown_map[symbol] = int(cooldown_until)
            if emergency_exit:
                monitor_reason = "emergency_exit_signal"
            elif monitor_reason not in ("confirmed_exit_signal", "emergency_exit_signal"):
                monitor_reason = "confirmed_exit_signal"

        if qty <= 0:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        state["_monitor_exit_confirm"] = confirm_map
        state["_monitor_sell_cooldown_until"] = cooldown_map
        state["_monitor_pending_exit_lock"] = pending_exit_lock
        state["_monitor_prev_position_qty"] = prev_qty_map

        exit_info = build_monitor_exit_payload(
            decision=decision,
            features=features,
            entry_info=entry_info,
            frame_applied=frame_applied,
            eod_carry=eod_carry,
            eod_carry_sweep=eod_carry_sweep,
            effective_exit_policy_base=effective_exit_policy_base,
            decision_thresholds=decision_thresholds,
            context={
                "symbol": symbol,
                "selected_symbol": selected_symbol,
                "qty": qty,
                "price": price,
                "avg_price": avg_price,
                "hold_sec": hold_sec,
                "exit_signal_detected": exit_signal_detected,
                "sell_guard_blocked": sell_guard_blocked,
                "sell_guard_reason": sell_guard_reason,
                "min_hold_sec": min_hold_sec,
                "sell_cooldown_sec": sell_cooldown_sec,
                "effective_confirm_ticks": effective_confirm_ticks,
                "confirm_count": confirm_count,
                "peak_drawdown_confirm_ticks": peak_drawdown_confirm_ticks,
                "min_hold_blocked": min_hold_blocked,
                "sell_cooldown_blocked": sell_cooldown_blocked,
                "hold_block_reason": hold_block_reason,
                "cooldown_until": cooldown_until,
                "lock_until": lock_until,
                "now_epoch": now_epoch,
                "monitor_reason": monitor_reason,
                "emergency_exit": emergency_exit,
                "hard_exit": hard_exit,
                "exit_policy_guard_adjustments": exit_policy_guard_adjustments,
                "monitor_memory_bias_observation_only": monitor_memory_bias_observation_only,
                "hold_bias_result": hold_bias_result,
                "hold_bias_observed_result": hold_bias_observed_result,
                "exit_bias_result": exit_bias_result,
                "exit_bias_observed_result": exit_bias_observed_result,
                "active_exit_axis": _friendly_exit_axis(str(decision.get("reason") or monitor_reason or "hold")),
                "watch_axes": _monitor_watch_axes(decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {}),
            },
        )
        sell_would_submit = bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0
        exit_vs_strategy_intent = build_exit_vs_strategy_intent(
            state=state,
            exit_info=exit_info,
            sell_submitted=sell_would_submit,
        )
        exit_info["exit_vs_strategy_intent"] = dict(exit_vs_strategy_intent)
        if bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0:
            exit_order_qty = max(1, min(int(qty), _to_int(decision.get("exit_qty") or qty)))
            exit_info["exit_qty"] = int(exit_order_qty)
            intents = [
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": int(exit_order_qty),
                    "thesis": str(plan.get("thesis") or ""),
                    "meta": {
                        "exit_reason": str(decision.get("reason") or ""),
                        "exit_qty": int(exit_order_qty),
                        "position_qty": int(qty),
                        "partial_exit": bool(decision.get("partial_exit")),
                        "exit_qty_fraction": decision.get("exit_qty_fraction"),
                        "profit_ladder_level_pct": decision.get("profit_ladder_level_pct"),
                        "profit_ladder_level_index": decision.get("profit_ladder_level_index"),
                        "risk_reward_take_profit_rung": decision.get("risk_reward_take_profit_rung"),
                        "pnl_ratio": decision.get("pnl_ratio"),
                        "raw_pnl_ratio": decision.get("raw_pnl_ratio"),
                        "gross_pnl_ratio": decision.get("gross_pnl_ratio"),
                        "technical_pnl_ratio": decision.get("technical_pnl_ratio"),
                        "effective_pnl_ratio": decision.get("effective_pnl_ratio"),
                        "stop_pnl_ratio": decision.get("stop_pnl_ratio"),
                        "stop_pnl_ratio_source": str(decision.get("stop_pnl_ratio_source") or ""),
                        "hard_stop_pnl_ratio": decision.get("hard_stop_pnl_ratio"),
                        "hard_stop_pnl_ratio_source": str(decision.get("hard_stop_pnl_ratio_source") or ""),
                        "cost_drag_pressure": bool(decision.get("cost_drag_pressure")),
                        "cost_drag_pressure_pct": decision.get("cost_drag_pressure_pct"),
                        "cost_drag_pressure_reason": str(decision.get("cost_drag_pressure_reason") or ""),
                        "stop_loss_cost_drag_blocked": bool(decision.get("stop_loss_cost_drag_blocked")),
                        "stop_loss_cost_drag_blocked_reason": str(decision.get("stop_loss_cost_drag_blocked_reason") or ""),
                        "etf_deviation_pct": decision.get("etf_deviation_pct"),
                        "etf_deviation_source": str(decision.get("etf_deviation_source") or ""),
                        "asset_class_detected": str(decision.get("asset_class_detected") or ""),
                        "avg_price": avg_price if avg_price > 0.0 else None,
                        "price": price,
                        "technical_price": decision.get("technical_price"),
                        "technical_price_source": str(decision.get("technical_price_source") or ""),
                        "effective_price": decision.get("effective_price"),
                        "account_current_price": decision.get("account_current_price"),
                        "account_mark_price": decision.get("account_mark_price"),
                        "account_unrealized_pnl": decision.get("account_unrealized_pnl"),
                        "account_pnl_ratio_source": str(decision.get("account_pnl_ratio_source") or ""),
                        "pnl_crosscheck_applied": bool(decision.get("pnl_crosscheck_applied")),
                        "pnl_crosscheck_reason": str(decision.get("pnl_crosscheck_reason") or ""),
                        "source": "monitor_exit_policy",
                        "reason": str(decision.get("reason") or ""),
                        "signal_source": "monitor_exit_policy",
                        "position_age_sec": hold_sec if hold_sec > 0 else None,
                        "position_age_seconds": hold_sec if hold_sec > 0 else None,
                        "monitor_reason": str(monitor_reason or ""),
                        "exit_signal_detected": bool(exit_signal_detected),
                        "exit_confirm_count": int(confirm_count),
                        "min_hold_blocked": bool(min_hold_blocked),
                        "sell_cooldown_blocked": bool(sell_cooldown_blocked),
                        "emergency_exit": bool(emergency_exit),
                        "playbook": str(frame_applied.get("playbook") or ""),
                        "monitor_guidance": str(frame_applied.get("monitor_guidance") or ""),
                        "risk_tone": str(frame_applied.get("risk_tone") or ""),
                        "trade_aggressiveness": str(frame_applied.get("trade_aggressiveness") or ""),
                        "strategy_horizon": str(frame_applied.get("strategy_horizon") or ""),
                        "source_strategy_horizon": str(frame_applied.get("source_strategy_horizon") or ""),
                        "horizon_behavior_translation": dict(frame_applied.get("horizon_behavior_translation") or {}),
                        "position_strategy_context_applied": bool(frame_applied.get("position_strategy_context_applied")),
                        "position_strategy_context_symbol": str(frame_applied.get("position_strategy_context_symbol") or ""),
                        "position_strategy_context_source": str(frame_applied.get("position_strategy_context_source") or ""),
                        "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
                        "exit_policy_guard_adjustments": list(exit_policy_guard_adjustments),
                        "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
                    },
                }
            ]

    commander_memory_application_trace = build_monitor_commander_memory_application_trace(
        monitor_memory_bias=monitor_memory_bias,
        entry_result={
            "applied": bool(entry_info.get("monitor_memory_bias_applied")),
            "deltas": list(entry_info.get("monitor_memory_bias_deltas") or []),
        },
        hold_result=hold_bias_result,
        exit_result=exit_bias_result,
        monitor_memory_bias_summary=monitor_memory_bias_summary,
        effective_policy_source=str(entry_info.get("effective_policy_source") or ""),
        effective_policy_source_chain=list(entry_info.get("effective_policy_source_chain") or []),
    )
    entry_info["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    entry_info["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
    exit_info["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    exit_info["monitor_memory_application_trace"] = dict(commander_memory_application_trace)

    order_status, order_status_meta = extract_order_status(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    fallback_reasons = list(order_status_meta.get("errors") or [])

    state["intents"] = intents
    state["monitor"] = {
        "skill_contract_version": SKILL_CONTRACT_VERSION,
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
        "order_status_present": bool(order_status_meta.get("present")),
        "order_status_fallback": bool(fallback_reasons),
        "order_status_fallback_reasons": fallback_reasons,
        "order_status_error_count": len(fallback_reasons),
        "order_lifecycle_loaded": bool(order_lifecycle),
        "order_lifecycle": order_lifecycle,
        "exit_policy_enabled": bool(exit_info.get("enabled")),
        "exit_evaluated": bool(exit_info.get("evaluated")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_reason": str(exit_info.get("reason") or ""),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "exit_pnl_ratio": exit_info.get("pnl_ratio"),
        "exit_raw_pnl_ratio": exit_info.get("raw_pnl_ratio"),
        "exit_gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
        "exit_technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
        "exit_effective_pnl_ratio": exit_info.get("effective_pnl_ratio"),
        "exit_stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
        "exit_stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
        "exit_hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
        "exit_hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
        "exit_cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
        "exit_cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
        "exit_cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
        "exit_stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
        "exit_stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
        "exit_symbol": exit_info.get("symbol"),
        "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
        "exit_qty": int(exit_info.get("exit_qty") or exit_info.get("qty") or 0),
        "exit_raw_price": exit_info.get("raw_price"),
        "exit_technical_price": exit_info.get("technical_price"),
        "exit_technical_price_source": str(exit_info.get("technical_price_source") or ""),
        "exit_effective_price": exit_info.get("effective_price"),
        "exit_effective_price_source": str(exit_info.get("effective_price_source") or ""),
        "exit_account_current_price": exit_info.get("account_current_price"),
        "exit_account_mark_price": exit_info.get("account_mark_price"),
        "exit_account_unrealized_pnl": exit_info.get("account_unrealized_pnl"),
        "exit_account_pnl_ratio": exit_info.get("account_pnl_ratio"),
        "exit_account_pnl_ratio_source": str(exit_info.get("account_pnl_ratio_source") or ""),
        "exit_pnl_crosscheck_applied": bool(exit_info.get("pnl_crosscheck_applied")),
        "exit_pnl_crosscheck_reason": str(exit_info.get("pnl_crosscheck_reason") or ""),
        "exit_pnl_crosscheck_gap": exit_info.get("pnl_crosscheck_gap"),
        "exit_position_age_seconds": exit_info.get("position_age_seconds"),
        "exit_min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
        "exit_sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
        "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "exit_min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
        "exit_sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
        "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "peak_drawdown_blocked": bool(exit_info.get("peak_drawdown_blocked")),
        "peak_drawdown_block_reason": str(exit_info.get("peak_drawdown_block_reason") or ""),
        "peak_drawdown_profit_floor_required_pct": exit_info.get("peak_drawdown_profit_floor_required_pct"),
        "peak_drawdown_profit_floor_met": bool(exit_info.get("peak_drawdown_profit_floor_met")),
        "exit_expected_exit_price": exit_info.get("expected_exit_price"),
        "exit_expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "exit_expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "exit_expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "exit_expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "exit_expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "exit_expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "exit_expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "exit_expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "exit_expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "eod_carry_evaluated": bool(exit_info.get("eod_carry_evaluated")),
        "eod_carry_approved": bool(exit_info.get("eod_carry_approved")),
        "eod_carry_action": str(exit_info.get("eod_carry_action") or ""),
        "eod_carry_reason": str(exit_info.get("eod_carry_reason") or ""),
        "position_sizing_enabled": bool(sizing_info.get("enabled")),
        "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
        "position_sizing_qty": int(sizing_info.get("qty") or 0),
        "position_sizing_reason": str(sizing_info.get("reason") or ""),
        "position_sizing_stop_loss_pct": (sizing_info.get("inputs") or {}).get("stop_loss_pct")
        if isinstance(sizing_info.get("inputs"), dict)
        else None,
        "position_sizing_stop_loss_source": str(
            ((sizing_info.get("inputs") or {}).get("stop_loss_source") if isinstance(sizing_info.get("inputs"), dict) else "")
            or ""
        ),
        "position_sizing_invalidation_price": (sizing_info.get("inputs") or {}).get("invalidation_price")
        if isinstance(sizing_info.get("inputs"), dict)
        else None,
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "multi_position_capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "block_buy_when_open_position": bool(block_buy_open_position),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "buy_blocked_same_symbol": bool(buy_blocked_same_symbol),
        "buy_blocked_pending_buy": bool(buy_blocked_pending_buy),
        "max_positions_reached": bool(max_positions_reached),
        "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
        "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
        "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
        "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
        "minutes_to_close": entry_info.get("minutes_to_close"),
        "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
        "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
        "closeout_window_active": bool(entry_info.get("closeout_window_active")),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_reason": str(entry_info.get("reason") or ""),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_signal_chain": list(entry_info.get("signal_chain") or []),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
        "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "entry_metrics": dict(entry_info.get("metrics") or {}),
        "entry_received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "entry_received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
        "entry_policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "entry_applied_policy": dict(entry_applied_policy),
        "entry_effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "entry_effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "entry_effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "commander_entry_control": dict(entry_info.get("commander_entry_control") or {}),
        "entry_policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "entry_policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "entry_effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "monitor_memory_bias_applied": bool(entry_info.get("monitor_memory_bias_applied")),
        "monitor_memory_bias_observation_only": bool(entry_info.get("monitor_memory_bias_observation_only")),
        "monitor_memory_bias": dict(entry_info.get("monitor_memory_bias") or {}),
        "monitor_memory_bias_summary": dict(entry_info.get("monitor_memory_bias_summary") or {}),
        "monitor_memory_bias_deltas": list(entry_info.get("monitor_memory_bias_deltas") or []),
        "monitor_memory_bias_observed_deltas": list(entry_info.get("monitor_memory_bias_observed_deltas") or []),
        "monitor_memory_bias_hold_applied": bool(exit_info.get("monitor_memory_bias_hold_applied")),
        "monitor_memory_bias_hold_deltas": list(exit_info.get("monitor_memory_bias_hold_deltas") or []),
        "monitor_memory_bias_exit_applied": bool(exit_info.get("monitor_memory_bias_exit_applied")),
        "monitor_memory_bias_exit_deltas": list(exit_info.get("monitor_memory_bias_exit_deltas") or []),
        "commander_memory_application_trace": dict(commander_memory_application_trace),
        "monitor_memory_application_trace": dict(commander_memory_application_trace),
        "entry_thresholds": dict(entry_info.get("thresholds") or {}),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "entry_hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "entry_total_score": entry_info.get("total_score"),
        "entry_score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "entry_quality_gate": dict(entry_info.get("entry_quality_gate") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "entry_score_threshold": entry_info.get("entry_threshold"),
        "entry_score_passed": bool(entry_info.get("score_passed")),
        "entry_scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "entry_legacy_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "entry_scoring_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
        "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        "entry_intent_submitted": bool(entry_info.get("intent_submitted")),
        "entry_legacy_fallback_used": bool(entry_info.get("legacy_fallback_used")),
        "entry_intent_cooldown_sec": int(entry_info.get("intent_cooldown_sec") or 0),
        "entry_intent_cooldown_until": entry_info.get("intent_cooldown_until"),
        "entry_candidate_cascade": dict(entry_candidate_cascade),
    }
    if bool(exit_info.get("enabled")) and bool(exit_info.get("exit_signal_detected")):
        monitor_entry_exit_reason = str(exit_info.get("reason") or "")
    elif bool(buy_blocked_post_exit_cooldown):
        monitor_entry_exit_reason = "post_exit_cooldown"
    elif bool(buy_blocked_closeout_window):
        monitor_entry_exit_reason = "buy_blocked_closeout_window"
    elif bool(buy_blocked_pending_buy):
        monitor_entry_exit_reason = "same_symbol_pending_buy"
    elif bool(buy_blocked_same_symbol):
        monitor_entry_exit_reason = "same_symbol_position_open"
    elif bool(max_positions_reached and buy_blocked_open_position):
        monitor_entry_exit_reason = "max_positions_reached"
    elif bool(buy_blocked_open_position):
        monitor_entry_exit_reason = "buy_blocked_open_position"
    elif bool(entry_info.get("guard_blocked")):
        monitor_entry_exit_reason = str(entry_info.get("guard_reason") or "")
    else:
        monitor_entry_exit_reason = str(entry_info.get("reason") or "entry_wait")
    tactic_id = str(
        strategist_output.get("tactical_strategy")
        or strategist_plan.get("tactical_strategy")
        or ""
    )
    tactic_playbook = str(strategist_output.get("playbook") or strategist_plan.get("selected_playbook") or "")
    quant_entry_factor_snapshot = (
        dict(entry_info.get("quant_factor_snapshot") or {})
        if isinstance(entry_info.get("quant_factor_snapshot"), dict)
        else build_factor_snapshot_from_monitor_entry(
            entry_info,
            selected=selected if isinstance(selected, dict) else {},
            tactic_id=tactic_id,
            playbook=tactic_playbook,
        )
    )
    quant_entry_decision = (
        dict(entry_info.get("entry_quant_decision") or {})
        if isinstance(entry_info.get("entry_quant_decision"), dict)
        else build_entry_quant_decision(
            entry_info,
            selected=selected if isinstance(selected, dict) else {},
            factor_snapshot=quant_entry_factor_snapshot,
            state=state,
            tactic_id=tactic_id,
            playbook=tactic_playbook,
        )
    )
    quant_entry_enforcement = (
        dict(entry_info.get("quant_entry_enforcement") or {})
        if isinstance(entry_info.get("quant_entry_enforcement"), dict)
        else build_entry_quant_enforcement(quant_entry_decision)
    )
    quant_exit_decision = build_exit_quant_decision(
        exit_info,
        state=state,
        tactic_id=tactic_id,
        playbook=tactic_playbook,
    )
    entry_info["quant_factor_snapshot"] = dict(quant_entry_factor_snapshot)
    entry_info["entry_quant_decision"] = dict(quant_entry_decision)
    entry_info["quant_entry_enforcement"] = dict(quant_entry_enforcement)
    exit_info["exit_quant_decision"] = dict(quant_exit_decision)
    state["monitor_output"] = {
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "intent_side": (str(intents[0].get("side")) if intents else "NOOP"),
        "intent_qty": (int(intents[0].get("qty") or 0) if intents else 0),
        "entry_exit_reason": monitor_entry_exit_reason,
        "entry_candidate_cascade": dict(entry_candidate_cascade),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "entry_quality_gate": dict(entry_info.get("entry_quality_gate") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "quant_factor_snapshot": dict(quant_entry_factor_snapshot),
        "entry_quant_decision": dict(quant_entry_decision),
        "quant_entry_enforcement": dict(quant_entry_enforcement),
        "exit_quant_decision": dict(quant_exit_decision),
    }
    state["monitor_entry"] = dict(entry_info)
    state["monitor_exit"] = exit_info
    state["monitor_sizing"] = sizing_info
    monitor_symbol = str(exit_info.get("symbol") or (selected.get("symbol") if isinstance(selected, dict) else "") or "")
    current_posture = _monitor_posture_for_cycle(
        open_position_count=open_position_count,
        intents=intents,
        exit_info=exit_info,
        buy_blocked_open_position=buy_blocked_open_position,
        buy_blocked_post_exit_cooldown=buy_blocked_post_exit_cooldown,
    )
    current_reason = str(exit_info.get("monitor_reason") or exit_info.get("reason") or (state.get("monitor_output") or {}).get("entry_exit_reason") or "").strip()
    previous_monitor_state = _load_previous_monitor_state(state, monitor_symbol) if monitor_symbol else {}
    previous_posture = str(previous_monitor_state.get("posture") or "").strip()
    previous_reason = str(previous_monitor_state.get("reason") or "").strip()
    entry_transition_trace = _build_monitor_entry_transition_trace(previous_monitor_state, entry_info)
    entry_info.update(dict(entry_transition_trace))
    entry_info["entry_transition_trace"] = dict(entry_transition_trace)
    state_changed = bool(previous_posture != current_posture or previous_reason != current_reason)
    if monitor_symbol:
        _save_current_monitor_state(
            state,
            monitor_symbol,
            posture=current_posture,
            reason=current_reason,
            active_exit_axis=str(exit_info.get("active_exit_axis") or ""),
            entry_state=_build_monitor_entry_state_snapshot(entry_info),
        )
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["entry_transition_trace"] = dict(entry_transition_trace)
        state["monitor"]["entry_became_ready_this_cycle"] = bool(entry_transition_trace.get("became_ready_this_cycle"))
        state["monitor"]["entry_last_blocking_axis"] = str(entry_transition_trace.get("last_blocking_axis") or "")
        state["monitor"]["entry_transition_readiness_score"] = entry_transition_trace.get("transition_readiness_score")
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["entry_transition_trace"] = dict(entry_transition_trace)
        state["monitor_output"]["entry_became_ready_this_cycle"] = bool(entry_transition_trace.get("became_ready_this_cycle"))
        state["monitor_output"]["entry_last_blocking_axis"] = str(entry_transition_trace.get("last_blocking_axis") or "")
        state["monitor_output"]["entry_transition_readiness_score"] = entry_transition_trace.get("transition_readiness_score")

    thresholds = dict(exit_info.get("thresholds") or {}) if isinstance(exit_info.get("thresholds"), dict) else {}
    entry_metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    entry_thresholds = dict(entry_info.get("thresholds") or {}) if isinstance(entry_info.get("thresholds"), dict) else {}
    entry_applied_policy = (
        dict(entry_info.get("applied_policy") or {})
        if isinstance(entry_info.get("applied_policy"), dict)
        else dict(entry_applied_policy or entry_thresholds)
    )
    monitor_policy_trace = _build_monitor_policy_trace(
        commander_context=commander_context,
        monitor_policy=strategy_monitor_policy,
        strategist_plan=strategist_plan,
        policy_provenance=policy_provenance,
        entry_info=entry_info,
        exit_info=exit_info,
        current_reason=current_reason,
    )
    policy_ref = dict(monitor_policy_trace.get("policy_ref") or {})
    policy_ref["received_policy"] = dict(entry_info.get("received_policy") or entry_received_policy or {})
    policy_ref["received_policy_source"] = str(entry_info.get("received_policy_source") or entry_policy_origin or "")
    policy_ref["effective_policy"] = dict(entry_info.get("effective_policy") or entry_applied_policy or {})
    policy_ref["effective_policy_source"] = str(entry_info.get("effective_policy_source") or "")
    policy_ref["effective_policy_source_chain"] = list(entry_info.get("effective_policy_source_chain") or [])
    policy_ref["policy_adjustments"] = dict(entry_info.get("policy_adjustments") or {})
    policy_ref["policy_adjustment_summary"] = str(entry_info.get("policy_adjustment_summary") or "")
    policy_ref["policy_adjustment_reasoning"] = str(entry_info.get("policy_adjustment_reasoning") or "")
    policy_ref["effective_policy_deltas"] = list(entry_info.get("effective_policy_deltas") or [])
    policy_ref["monitor_memory_bias_applied"] = bool(entry_info.get("monitor_memory_bias_applied"))
    policy_ref["monitor_memory_bias_observation_only"] = bool(entry_info.get("monitor_memory_bias_observation_only"))
    policy_ref["monitor_memory_bias"] = dict(entry_info.get("monitor_memory_bias") or {})
    policy_ref["monitor_memory_bias_summary"] = dict(entry_info.get("monitor_memory_bias_summary") or {})
    policy_ref["monitor_memory_bias_deltas"] = list(entry_info.get("monitor_memory_bias_deltas") or [])
    policy_ref["monitor_memory_bias_observed_deltas"] = list(entry_info.get("monitor_memory_bias_observed_deltas") or [])
    policy_ref["monitor_memory_bias_hold_applied"] = bool(exit_info.get("monitor_memory_bias_hold_applied"))
    policy_ref["monitor_memory_bias_hold_deltas"] = list(exit_info.get("monitor_memory_bias_hold_deltas") or [])
    policy_ref["monitor_memory_bias_exit_applied"] = bool(exit_info.get("monitor_memory_bias_exit_applied"))
    policy_ref["monitor_memory_bias_exit_deltas"] = list(exit_info.get("monitor_memory_bias_exit_deltas") or [])
    policy_ref["commander_memory_application_trace"] = dict(commander_memory_application_trace)
    policy_ref["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
    monitor_policy_trace["policy_ref"] = policy_ref
    pnl_ratio = _to_float(exit_info.get("pnl_ratio")) if exit_info.get("pnl_ratio") not in (None, "") else None
    threshold_snapshot = {
        "current_price": exit_info.get("price"),
        "avg_price": exit_info.get("avg_price"),
        "peak_price": exit_info.get("peak_price"),
        "pnl_pct": pnl_ratio,
        "drawdown_pct": exit_info.get("peak_drawdown"),
        "stop_loss_pct": thresholds.get("stop_loss_pct"),
        "effective_stop_loss_pct": thresholds.get("effective_stop_loss_pct"),
        "take_profit_pct": thresholds.get("take_profit_pct"),
        "trailing_stop_pct": thresholds.get("trailing_stop_pct"),
        "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
        "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
        "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
        "hold_limit_sec": exit_info.get("hold_limit_sec"),
        "max_hold_reached": bool(exit_info.get("max_hold_reached")),
        "time_stop_reached": bool(exit_info.get("time_stop_reached")),
        "time_limit_reached": bool(exit_info.get("time_limit_reached")),
        "time_limit_reason": str(exit_info.get("time_limit_reason") or ""),
        "time_limit_reassessment_required": bool(exit_info.get("time_limit_reassessment_required")),
        "time_limit_reassessment_blocked": bool(exit_info.get("time_limit_reassessment_blocked")),
        "time_limit_reassessment_blocked_reason": str(
            exit_info.get("time_limit_reassessment_blocked_reason") or ""
        ),
        "max_runup_pct": exit_info.get("max_runup_pct"),
        "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
        "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
        "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
        "peak_drawdown_blocked": bool(exit_info.get("peak_drawdown_blocked")),
        "peak_drawdown_block_reason": str(exit_info.get("peak_drawdown_block_reason") or ""),
        "peak_drawdown_profit_floor_required_pct": exit_info.get("peak_drawdown_profit_floor_required_pct"),
        "peak_drawdown_profit_floor_met": bool(exit_info.get("peak_drawdown_profit_floor_met")),
        "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
        "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
        "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
        "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
        "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "expected_exit_price": exit_info.get("expected_exit_price"),
        "expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "vwap_distance_pct": exit_info.get("vwap_distance"),
        "volatility_regime": str(exit_info.get("volatility_regime") or ""),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "watch_axes": list(exit_info.get("watch_axes") or []),
        "exit_confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "price_anomaly_flag": bool(exit_info.get("price_anomaly_flag")),
        "price_anomaly_reason": str(exit_info.get("price_anomaly_reason") or ""),
        "pnl_fallback_applied": bool(exit_info.get("pnl_fallback_applied")),
        "fallback_price_source": str(exit_info.get("fallback_price_source") or ""),
        "entry_timeframe_minutes": entry_metrics.get("timeframe_minutes"),
        "entry_minute_source_present": entry_metrics.get("minute_source_present"),
        "entry_minute_source_used": entry_metrics.get("minute_source_used"),
        "entry_latest_candle_ts": entry_metrics.get("latest_candle_ts"),
        "entry_minute_snapshot_age_minutes": entry_metrics.get("minute_snapshot_age_minutes"),
        "entry_minute_snapshot_was_stale": entry_metrics.get("minute_snapshot_was_stale"),
        "entry_minute_refetch_attempted": entry_metrics.get("minute_refetch_attempted"),
        "entry_minute_refetch_succeeded": entry_metrics.get("minute_refetch_succeeded"),
        "entry_minute_refetch_reason": entry_metrics.get("minute_refetch_reason"),
        "entry_minute_refetch_trigger_reason": entry_metrics.get("minute_refetch_trigger_reason"),
        "entry_minute_refetch_failure_reason": entry_metrics.get("minute_refetch_failure_reason"),
        "entry_minute_refetch_produced_fresh_snapshot": entry_metrics.get("minute_refetch_produced_fresh_snapshot"),
        "entry_inferred_spacing_minutes": entry_metrics.get("inferred_spacing_minutes"),
        "entry_series_class": entry_metrics.get("series_class"),
        "entry_recent_high": entry_metrics.get("recent_high"),
        "entry_breakout_level": entry_metrics.get("breakout_level"),
        "entry_vwap": entry_metrics.get("vwap"),
        "entry_volume_ratio": entry_metrics.get("volume_ratio"),
        "entry_extended_from_vwap_pct": entry_metrics.get("extended_from_vwap_pct"),
        "entry_pullback_depth_pct": entry_metrics.get("pullback_depth_pct"),
        "entry_previous_close": entry_metrics.get("previous_close"),
        "entry_session_open": entry_metrics.get("session_open"),
        "entry_open_gap_pct": entry_metrics.get("open_gap_pct"),
        "entry_prev_close_distance_pct": entry_metrics.get("prev_close_distance_pct"),
        "entry_minutes_since_session_open": entry_metrics.get("minutes_since_session_open"),
        "entry_opening_gap_chase_observed": bool(entry_metrics.get("opening_gap_chase_observed")),
        "entry_opening_gap_context_observation_only": bool(entry_metrics.get("opening_gap_context_observation_only")),
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "applied_policy": dict(entry_applied_policy),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "entry_volume_ratio_min": entry_thresholds.get("volume_ratio_min"),
        "entry_max_extended_from_vwap_pct": entry_thresholds.get("max_extended_from_vwap_pct"),
        "entry_min_extended_from_vwap_pct": entry_thresholds.get("min_extended_from_vwap_pct"),
        "entry_pullback_min_pct": entry_thresholds.get("pullback_min_pct"),
        "entry_pullback_max_pct": entry_thresholds.get("pullback_max_pct"),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
        "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "entry_hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "entry_total_score": entry_info.get("total_score"),
        "entry_score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "entry_signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "entry_chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "entry_policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "entry_policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "entry_policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "entry_chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_score_threshold": entry_info.get("entry_threshold"),
        "entry_score_passed": bool(entry_info.get("score_passed")),
        "entry_scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "entry_legacy_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "entry_scoring_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
    }
    state["monitor_posture"] = current_posture
    state["monitor_threshold_snapshot"] = dict(threshold_snapshot)
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["threshold_snapshot"] = dict(threshold_snapshot)
        state["monitor"]["exit_stop_loss_pct"] = threshold_snapshot.get("stop_loss_pct")
        state["monitor"]["exit_effective_stop_loss_pct"] = threshold_snapshot.get("effective_stop_loss_pct")
        state["monitor"]["position_entry_risk_applied"] = bool(exit_info.get("position_entry_risk_applied"))
        state["monitor"]["position_entry_stop_loss_pct"] = exit_info.get("position_entry_stop_loss_pct")
        state["monitor"]["position_entry_stop_loss_source"] = str(exit_info.get("position_entry_stop_loss_source") or "")
        state["monitor"]["position_entry_invalidation_price"] = exit_info.get("position_entry_invalidation_price")
    state["monitor_state_transition"] = {
        "previous_posture": previous_posture,
        "current_posture": current_posture,
        "previous_reason": previous_reason,
        "current_reason": current_reason,
        "state_changed": bool(state_changed),
        "trigger_delta": {
            "previous_active_exit_axis": str(previous_monitor_state.get("active_exit_axis") or ""),
            "current_active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "exit_triggered": bool(exit_info.get("triggered")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
            "became_ready_this_cycle": bool(entry_transition_trace.get("became_ready_this_cycle")),
            "last_blocking_axis": str(entry_transition_trace.get("last_blocking_axis") or ""),
            "transition_readiness_score": entry_transition_trace.get("transition_readiness_score"),
        },
    }
    _emit_monitor_event(
        state,
        name="threshold_snapshot",
        payload=threshold_snapshot,
        symbol=monitor_symbol,
    )
    _emit_monitor_event(
        state,
        name="state_transition",
        payload={
            "previous_posture": previous_posture,
            "current_posture": current_posture,
            "previous_reason": previous_reason,
            "current_reason": current_reason,
            "state_changed": bool(state_changed),
            "trigger_delta": {
                "previous_active_exit_axis": str(previous_monitor_state.get("active_exit_axis") or ""),
                "current_active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
                "exit_triggered": bool(exit_info.get("triggered")),
                "entry_triggered": bool(entry_info.get("triggered")),
                "entry_pattern": str(entry_info.get("pattern") or ""),
                "became_ready_this_cycle": bool(entry_transition_trace.get("became_ready_this_cycle")),
                "last_blocking_axis": str(entry_transition_trace.get("last_blocking_axis") or ""),
                "transition_readiness_score": entry_transition_trace.get("transition_readiness_score"),
            },
        },
        symbol=monitor_symbol,
    )
    buy_submitted = any(str((intent or {}).get("side") or "").strip().upper() == "BUY" for intent in list(intents or []))
    buy_skipped_reason = ""
    if not bool(buy_submitted):
        buy_skipped_reason = str(entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait").strip()
    entry_event_metrics = dict(entry_info.get("metrics") or {}) if isinstance(entry_info.get("metrics"), dict) else {}
    if "price" not in entry_event_metrics:
        entry_event_metrics["price"] = entry_event_metrics.get("current_price")
    if "vwap_distance" not in entry_event_metrics:
        entry_event_metrics["vwap_distance"] = entry_event_metrics.get("extended_from_vwap_pct")
    if "pullback_pct" not in entry_event_metrics:
        entry_event_metrics["pullback_pct"] = entry_event_metrics.get("pullback_depth_pct")
    final_entry_decision = "BUY" if bool(buy_submitted) else "WAIT"
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    monitor_no_trade_surface = build_monitor_no_trade_surface(
        entry_info,
        final_decision=final_entry_decision,
        buy_submitted=bool(buy_submitted),
        guard_blocked=bool(entry_info.get("guard_blocked")),
        guard_reason=entry_info.get("guard_reason"),
        commander_no_trade_reason_code=commander_decision.get("no_trade_reason_code"),
    )
    scanner_monitor_handoff = build_scanner_monitor_handoff_surface(
        selected=scanner_selected_snapshot if isinstance(scanner_selected_snapshot, dict) else {},
        ranked_candidates=[row for row in list(state.get("ranked_candidates") or []) if isinstance(row, dict)],
        scanner_output=state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {},
        final_decision=final_entry_decision,
        no_trade_surface=monitor_no_trade_surface,
        entry_info=entry_info,
    )
    scanner_monitor_handoff["monitor_selected_symbol"] = str((selected or {}).get("symbol") or "")
    scanner_monitor_handoff["entry_candidate_cascade"] = dict(entry_candidate_cascade)
    state["monitor_no_trade_surface"] = dict(monitor_no_trade_surface)
    state["scanner_monitor_handoff"] = dict(scanner_monitor_handoff)
    entry_blocker_surface = build_entry_blocker_surface(
        entry_info,
        final_decision=final_entry_decision,
        no_trade_surface=monitor_no_trade_surface,
        entry_blockers=list(monitor_policy_trace.get("entry_blockers") or []),
        buy_blocked_open_position=bool(buy_blocked_open_position),
        buy_blocked_closeout_window=bool(buy_blocked_closeout_window),
        buy_blocked_post_exit_cooldown=bool(buy_blocked_post_exit_cooldown),
        post_exit_cooldown_remaining_sec=post_exit_cooldown_remaining_sec,
        open_position_count=open_position_count,
        minutes_to_close=entry_info.get("minutes_to_close"),
        eod_flat_cutoff_min=entry_info.get("eod_flat_cutoff_min"),
    )
    state["monitor_entry_blocker_surface"] = dict(entry_blocker_surface)
    scanner_selected_symbol = str(
        scanner_monitor_handoff.get("scanner_selected_symbol")
        or (scanner_selected_snapshot.get("symbol") if isinstance(scanner_selected_snapshot, dict) else "")
        or ""
    ).strip()
    entry_candidate_symbol = str(
        entry_info.get("selected_symbol")
        or entry_info.get("symbol")
        or ((selected or {}).get("symbol") if isinstance(selected, dict) else "")
        or ""
    ).strip()
    entry_final_symbol = str(
        entry_candidate_cascade.get("final_selected_symbol")
        or ((selected or {}).get("symbol") if isinstance(selected, dict) else "")
        or entry_candidate_symbol
        or ""
    ).strip()
    position_focus_symbol = str(exit_info.get("symbol") or "").strip()
    monitor_output_symbol = str(monitor_symbol or position_focus_symbol or entry_final_symbol or "").strip()
    entry_cost_filter_snapshot = (
        dict(entry_info.get("entry_cost_filter") or {})
        if isinstance(entry_info.get("entry_cost_filter"), dict)
        else {}
    )
    if position_focus_symbol and entry_final_symbol and position_focus_symbol != entry_final_symbol:
        monitor_focus_mode = "entry_candidate_and_position_focus"
    elif position_focus_symbol:
        monitor_focus_mode = "position_focus"
    elif entry_final_symbol:
        monitor_focus_mode = "entry_candidate_focus"
    else:
        monitor_focus_mode = "no_symbol_focus"
    monitor_focus_context = {
        "schema_version": "monitor.focus_context.v1",
        "focus_mode": monitor_focus_mode,
        "scanner_selected_symbol": scanner_selected_symbol,
        "entry_candidate_symbol": entry_candidate_symbol,
        "entry_final_symbol": entry_final_symbol,
        "position_focus_symbol": position_focus_symbol,
        "monitor_output_symbol": monitor_output_symbol,
        "open_position_count": int(open_position_count),
        "max_positions": int(max_positions),
        "capacity_remaining": max(0, int(max_positions) - int(open_position_count)),
        "held_symbols": sorted(held_symbols_for_entry),
        "pending_buy_symbols": sorted(pending_buy_symbols_for_entry),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_decision": final_entry_decision,
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_intent_submitted": bool(buy_submitted),
        "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
        "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        "entry_reason": str(entry_info.get("reason") or ""),
        "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "entry_cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "entry_cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "entry_cost_drag_pct": entry_info.get("cost_drag_pct"),
        "entry_cost_filter": dict(entry_cost_filter_snapshot),
        "exit_evaluated": bool(exit_info.get("evaluated")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_reason": str(exit_info.get("reason") or ""),
        "exit_monitor_reason": str(exit_info.get("monitor_reason") or ""),
        "exit_active_axis": str(exit_info.get("active_exit_axis") or ""),
    }
    state["monitor_focus_context"] = dict(monitor_focus_context)
    if isinstance(state.get("monitor"), dict):
        state["monitor"]["monitor_focus_context"] = dict(monitor_focus_context)
        state["monitor"]["entry_candidate_symbol"] = entry_candidate_symbol
        state["monitor"]["entry_final_symbol"] = entry_final_symbol
        state["monitor"]["position_focus_symbol"] = position_focus_symbol
        state["monitor"]["monitor_focus_mode"] = monitor_focus_mode
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["entry_blocker_surface"] = dict(entry_blocker_surface)
        state["monitor_output"]["monitor_focus_context"] = dict(monitor_focus_context)
        state["monitor_output"]["scanner_selected_symbol"] = scanner_selected_symbol
        state["monitor_output"]["entry_candidate_symbol"] = entry_candidate_symbol
        state["monitor_output"]["entry_final_symbol"] = entry_final_symbol
        state["monitor_output"]["position_focus_symbol"] = position_focus_symbol
        state["monitor_output"]["monitor_output_symbol"] = monitor_output_symbol
        state["monitor_output"]["monitor_focus_mode"] = monitor_focus_mode
        state["monitor_output"]["entry_candidate_decision"] = final_entry_decision
        state["monitor_output"]["entry_candidate_reason"] = str(
            entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait"
        )
        state["monitor_output"]["entry_candidate_primary_failure_axis"] = str(
            entry_info.get("primary_failure_axis") or ""
        )
        state["monitor_output"]["entry_candidate_cost_adjusted_edge_ok"] = bool(
            entry_info.get("cost_adjusted_edge_ok")
        )
        state["monitor_output"]["entry_candidate_cost_adjusted_edge_pct"] = entry_info.get("cost_adjusted_edge_pct")
        state["monitor_output"]["entry_candidate_cost_drag_pct"] = entry_info.get("cost_drag_pct")
        state["monitor_output"]["entry_candidate_cost_filter"] = dict(entry_cost_filter_snapshot)
    _emit_monitor_event(
        state,
        name="entry_blocker_surface",
        payload=entry_blocker_surface,
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    entry_decision_detail = {
        "decision": final_entry_decision,
        "reason": str(entry_info.get("guard_reason") or entry_info.get("reason") or "entry_wait"),
        "entry_evaluated": bool(entry_info.get("evaluated")),
        "entry_triggered": bool(entry_info.get("triggered")),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_reason": str(entry_info.get("reason") or ""),
        "signal_chain": list(entry_info.get("signal_chain") or []),
        "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
        "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
        "condition_scores": dict(entry_info.get("condition_scores") or {}),
        "grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
        "guard_blocked": bool(entry_info.get("guard_blocked")),
        "guard_reason": str(entry_info.get("guard_reason") or ""),
        "buy_submitted": bool(buy_submitted),
        "buy_skipped_reason": buy_skipped_reason,
        "previous_close": entry_event_metrics.get("previous_close"),
        "session_open": entry_event_metrics.get("session_open"),
        "open_gap_pct": entry_event_metrics.get("open_gap_pct"),
        "prev_close_distance_pct": entry_event_metrics.get("prev_close_distance_pct"),
        "minutes_since_session_open": entry_event_metrics.get("minutes_since_session_open"),
        "opening_gap_chase_observed": bool(entry_event_metrics.get("opening_gap_chase_observed")),
        "opening_gap_context_observation_only": bool(entry_event_metrics.get("opening_gap_context_observation_only")),
        "metrics": entry_event_metrics,
        "applied_policy": dict(entry_applied_policy),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "thresholds": dict(entry_info.get("thresholds") or {}),
        "passed_checks": list(entry_info.get("passed_checks") or []),
        "failed_checks": list(entry_info.get("failed_checks") or []),
        "primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
        "threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "monitor_memory_bias_observation_only": bool(entry_info.get("monitor_memory_bias_observation_only")),
        "monitor_memory_bias_observed_deltas": list(entry_info.get("monitor_memory_bias_observed_deltas") or []),
        "minute_source_meta": dict(entry_info.get("minute_source_meta") or {}),
        "minute_fetch_meta": dict(entry_info.get("minute_fetch_meta") or {}),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "entry_candidate_cascade": dict(entry_candidate_cascade),
        "entry_blocker_surface": dict(entry_blocker_surface),
        "quant_factor_snapshot": dict(quant_entry_factor_snapshot),
        "entry_quant_decision": dict(quant_entry_decision),
        "quant_entry_enforcement": dict(quant_entry_enforcement),
        "monitor_focus_context": dict(monitor_focus_context),
        "scanner_selected_symbol": scanner_selected_symbol,
        "entry_candidate_symbol": entry_candidate_symbol,
        "entry_final_symbol": entry_final_symbol,
        "position_focus_symbol": position_focus_symbol,
        "monitor_output_symbol": monitor_output_symbol,
        "monitor_focus_mode": monitor_focus_mode,
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "flow_instruction_applied": bool(monitor_policy_trace.get("flow_instruction_applied")),
        "no_trade_reason_applied": bool(monitor_policy_trace.get("no_trade_reason_applied")),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_entry_decision_detail"] = dict(entry_decision_detail)
    _emit_monitor_event(
        state,
        name="entry_decision_detail",
        payload=entry_decision_detail,
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    scoring_event_payload = {
        "run_id": str(state.get("run_id") or ""),
        "symbol": str(monitor_symbol or entry_symbol or ""),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "policy_interpretation": dict(entry_info.get("policy_interpretation") or {}),
        "signal_evidence": dict(entry_info.get("signal_evidence") or {}),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_interpreter_trace": dict(entry_info.get("policy_interpreter_trace") or {}),
        "policy_alignment_summary": dict(entry_info.get("policy_alignment_summary") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "minute_source_meta": dict(entry_info.get("minute_source_meta") or {}),
        "minute_fetch_meta": dict(entry_info.get("minute_fetch_meta") or {}),
        "total_score": entry_info.get("total_score"),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "final_decision": final_entry_decision,
        "primary_reason_code": str(entry_info.get("reason") or ""),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "entry_blocker_surface": dict(entry_blocker_surface),
    }
    if not bool(entry_info.get("hard_filter_passed")):
        _emit_monitor_event(
            state,
            name="hard_filter_failed",
            payload=dict(scoring_event_payload),
            level="info",
            symbol=monitor_symbol or entry_symbol,
        )
    _emit_monitor_event(
        state,
        name="score_computed",
        payload=dict(scoring_event_payload),
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    _emit_monitor_event(
        state,
        name="entry_decision",
        payload=dict(scoring_event_payload),
        level="info",
        symbol=monitor_symbol or entry_symbol,
    )
    sell_submitted = any(str((intent or {}).get("side") or "").strip().upper() == "SELL" for intent in list(intents or []))
    sell_skipped_reason = ""
    if bool(exit_info.get("exit_signal_detected")) and not bool(sell_submitted):
        sell_skipped_reason = str(exit_info.get("sell_guard_reason") or exit_info.get("reason") or "sell_not_submitted").strip()
    exit_decision_detail = {
        "exit_triggered": bool(exit_info.get("triggered")),
        "triggered_rule": str(exit_info.get("reason") or ""),
        "pnl_ratio": exit_info.get("pnl_ratio"),
        "raw_pnl_ratio": exit_info.get("raw_pnl_ratio"),
        "gross_pnl_ratio": exit_info.get("gross_pnl_ratio"),
        "technical_pnl_ratio": exit_info.get("technical_pnl_ratio"),
        "effective_pnl_ratio": exit_info.get("effective_pnl_ratio"),
        "stop_pnl_ratio": exit_info.get("stop_pnl_ratio"),
        "stop_pnl_ratio_source": str(exit_info.get("stop_pnl_ratio_source") or ""),
        "hard_stop_pnl_ratio": exit_info.get("hard_stop_pnl_ratio"),
        "hard_stop_pnl_ratio_source": str(exit_info.get("hard_stop_pnl_ratio_source") or ""),
        "cost_drag_pressure": bool(exit_info.get("cost_drag_pressure")),
        "cost_drag_pressure_pct": exit_info.get("cost_drag_pressure_pct"),
        "cost_drag_pressure_reason": str(exit_info.get("cost_drag_pressure_reason") or ""),
        "stop_loss_cost_drag_blocked": bool(exit_info.get("stop_loss_cost_drag_blocked")),
        "stop_loss_cost_drag_blocked_reason": str(exit_info.get("stop_loss_cost_drag_blocked_reason") or ""),
        "price": exit_info.get("price"),
        "technical_price": exit_info.get("technical_price"),
        "technical_price_source": str(exit_info.get("technical_price_source") or ""),
        "effective_price": exit_info.get("effective_price"),
        "account_mark_price": exit_info.get("account_mark_price"),
        "account_mark_price_source": str(exit_info.get("account_mark_price_source") or ""),
        "account_unrealized_pnl": exit_info.get("account_unrealized_pnl"),
        "account_pnl_ratio_source": str(exit_info.get("account_pnl_ratio_source") or ""),
        "pnl_crosscheck_applied": bool(exit_info.get("pnl_crosscheck_applied")),
        "pnl_crosscheck_reason": str(exit_info.get("pnl_crosscheck_reason") or ""),
        "pnl_crosscheck_gap": exit_info.get("pnl_crosscheck_gap"),
        "price_anomaly_flag": bool(exit_info.get("price_anomaly_flag")),
        "price_anomaly_reason": str(exit_info.get("price_anomaly_reason") or ""),
        "pnl_fallback_applied": bool(exit_info.get("pnl_fallback_applied")),
        "fallback_price_source": str(exit_info.get("fallback_price_source") or ""),
        "confirm_count": int(exit_info.get("exit_confirm_count") or 0),
        "confirm_required": int(exit_info.get("exit_confirm_ticks") or 0),
        "guard_blocked": bool(exit_info.get("sell_guard_blocked")),
        "guard_reason": str(exit_info.get("sell_guard_reason") or ""),
        "hold_block_reason": str(exit_info.get("hold_block_reason") or ""),
        "final_exit_thresholds": dict(exit_info.get("final_exit_thresholds") or {}),
        "exit_threshold_source": str(exit_info.get("exit_threshold_source") or ""),
        "max_runup_pct": exit_info.get("max_runup_pct"),
        "peak_drawdown_from_peak": exit_info.get("peak_drawdown_from_peak"),
        "peak_drawdown_armed": bool(exit_info.get("peak_drawdown_armed")),
        "peak_drawdown_mode": str(exit_info.get("peak_drawdown_mode") or ""),
        "peak_drawdown_blocked": bool(exit_info.get("peak_drawdown_blocked")),
        "peak_drawdown_block_reason": str(exit_info.get("peak_drawdown_block_reason") or ""),
        "peak_drawdown_profit_floor_required_pct": exit_info.get("peak_drawdown_profit_floor_required_pct"),
        "peak_drawdown_profit_floor_met": bool(exit_info.get("peak_drawdown_profit_floor_met")),
        "final_peak_drawdown_ratio": exit_info.get("final_peak_drawdown_ratio"),
        "peak_drawdown_source": str(exit_info.get("peak_drawdown_source") or ""),
        "exit_trigger_metric_name": str(exit_info.get("exit_trigger_metric_name") or ""),
        "exit_trigger_metric_value": exit_info.get("exit_trigger_metric_value"),
        "exit_trigger_metric_source": str(exit_info.get("exit_trigger_metric_source") or ""),
        "cost_aware_profit_floor_enabled": bool(exit_info.get("cost_aware_profit_floor_enabled")),
        "round_trip_cost_floor_pct": exit_info.get("round_trip_cost_floor_pct"),
        "min_net_profit_buffer_pct": exit_info.get("min_net_profit_buffer_pct"),
        "cost_aware_profit_floor_pct": exit_info.get("cost_aware_profit_floor_pct"),
        "cost_aware_profit_floor_met": bool(exit_info.get("cost_aware_profit_floor_met")),
        "cost_aware_profit_floor_gap_pct": exit_info.get("cost_aware_profit_floor_gap_pct"),
        "cost_aware_profit_floor_blocked": bool(exit_info.get("cost_aware_profit_floor_blocked")),
        "expected_exit_price": exit_info.get("expected_exit_price"),
        "expected_exit_price_source": str(exit_info.get("expected_exit_price_source") or ""),
        "expected_exit_price_fallback_used": bool(exit_info.get("expected_exit_price_fallback_used")),
        "expected_exit_slippage_buffer_pct": exit_info.get("expected_exit_slippage_buffer_pct"),
        "expected_exit_pnl_ratio": exit_info.get("expected_exit_pnl_ratio"),
        "expected_exit_net_pnl_ratio": exit_info.get("expected_exit_net_pnl_ratio"),
        "expected_exit_profit_floor_met": bool(exit_info.get("expected_exit_profit_floor_met")),
        "expected_exit_profit_floor_gap_pct": exit_info.get("expected_exit_profit_floor_gap_pct"),
        "expected_exit_profit_floor_blocked": bool(exit_info.get("expected_exit_profit_floor_blocked")),
        "expected_exit_profit_floor_blocked_reason": str(
            exit_info.get("expected_exit_profit_floor_blocked_reason") or ""
        ),
        "protective_exit_floor_blocked": bool(exit_info.get("protective_exit_floor_blocked")),
        "protective_exit_floor_blocked_reason": str(exit_info.get("protective_exit_floor_blocked_reason") or ""),
        "protective_exit_hard_invalidation": bool(exit_info.get("protective_exit_hard_invalidation")),
        "protective_exit_hard_invalidation_reason": str(
            exit_info.get("protective_exit_hard_invalidation_reason") or ""
        ),
        "risk_reward_take_profit_target_pct": exit_info.get("risk_reward_take_profit_target_pct"),
        "risk_reward_take_profit_rung": exit_info.get("risk_reward_take_profit_rung"),
        "resistance_price": exit_info.get("resistance_price"),
        "resistance_price_source": str(exit_info.get("resistance_price_source") or ""),
        "resistance_distance_pct": exit_info.get("resistance_distance_pct"),
        "profit_time_stop_peak_giveback_pct": exit_info.get("profit_time_stop_peak_giveback_pct"),
        "partial_exit": bool(exit_info.get("partial_exit")),
        "exit_qty": exit_info.get("exit_qty"),
        "exit_qty_fraction": exit_info.get("exit_qty_fraction"),
        "profit_ladder_level_pct": exit_info.get("profit_ladder_level_pct"),
        "profit_ladder_level_index": exit_info.get("profit_ladder_level_index"),
        "volume_ratio": exit_info.get("volume_ratio"),
        "execution_strength": exit_info.get("execution_strength"),
        "trade_strength": exit_info.get("trade_strength"),
        "opening_gap_chase_observed": bool(exit_info.get("opening_gap_chase_observed")),
        "open_gap_pct": exit_info.get("open_gap_pct"),
        "prev_close_distance_pct": exit_info.get("prev_close_distance_pct"),
        "position_entry_risk_applied": bool(exit_info.get("position_entry_risk_applied")),
        "position_entry_stop_loss_pct": exit_info.get("position_entry_stop_loss_pct"),
        "position_entry_stop_loss_source": str(exit_info.get("position_entry_stop_loss_source") or ""),
        "position_entry_invalidation_price": exit_info.get("position_entry_invalidation_price"),
        "sell_submitted": bool(sell_submitted),
        "sell_skipped_reason": sell_skipped_reason,
        "final_reason": current_reason,
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "exit_quant_decision": dict(quant_exit_decision),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "exit_trigger_basis": dict(monitor_policy_trace.get("exit_trigger_basis") or {}),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_exit_decision_detail"] = dict(exit_decision_detail)
    _emit_monitor_event(
        state,
        name="exit_decision_detail",
        payload=exit_decision_detail,
        level="warning" if bool(exit_info.get("triggered")) else "info",
        symbol=monitor_symbol,
    )
    triggered_rules = []
    if bool(exit_info.get("triggered")) and str(exit_info.get("reason") or "").strip():
        triggered_rules.append(str(exit_info.get("reason") or "").strip())
    if bool(entry_info.get("triggered")) and str(entry_info.get("pattern") or "").strip():
        triggered_rules.append(f"entry:{str(entry_info.get('pattern') or '').strip()}")
    blocked_rules = []
    if bool(entry_info.get("guard_blocked")) and str(entry_info.get("guard_reason") or "").strip():
        blocked_rules.append(str(entry_info.get("guard_reason") or "").strip())
    if bool(exit_info.get("sell_guard_blocked")) and str(exit_info.get("sell_guard_reason") or "").strip():
        blocked_rules.append(str(exit_info.get("sell_guard_reason") or "").strip())
    blocked_rules.extend([str(x or "").strip() for x in list(entry_info.get("failed_checks") or []) if str(x or "").strip()])
    reason_chain = [
        str(exit_info.get("monitor_reason") or "").strip(),
        str(exit_info.get("reason") or "").strip(),
        str(entry_info.get("reason") or "").strip(),
        str((state.get("monitor_output") or {}).get("entry_exit_reason") or "").strip(),
    ]
    reason_chain = [x for x in reason_chain if x]
    if isinstance(state.get("monitor_output"), dict):
        state["monitor_output"]["policy_ref"] = dict(monitor_policy_trace.get("policy_ref") or {})
        state["monitor_output"]["entry_check_summary"] = str(monitor_policy_trace.get("entry_check_summary") or "")
        state["monitor_output"]["entry_blockers"] = list(monitor_policy_trace.get("entry_blockers") or [])
        state["monitor_output"]["timing_assessment"] = dict(monitor_policy_trace.get("timing_assessment") or {})
        state["monitor_output"]["exit_trigger_basis"] = dict(monitor_policy_trace.get("exit_trigger_basis") or {})
        state["monitor_output"]["exit_vs_strategy_intent"] = dict(exit_info.get("exit_vs_strategy_intent") or {})
        state["monitor_output"]["final_exit_thresholds"] = dict(exit_info.get("final_exit_thresholds") or {})
        state["monitor_output"]["exit_threshold_source"] = str(exit_info.get("exit_threshold_source") or "")
        state["monitor_output"]["hold_block_reason"] = str(exit_info.get("hold_block_reason") or "")
        state["monitor_output"]["max_runup_pct"] = exit_info.get("max_runup_pct")
        state["monitor_output"]["peak_drawdown_from_peak"] = exit_info.get("peak_drawdown_from_peak")
        state["monitor_output"]["peak_drawdown_armed"] = bool(exit_info.get("peak_drawdown_armed"))
        state["monitor_output"]["peak_drawdown_mode"] = str(exit_info.get("peak_drawdown_mode") or "")
        state["monitor_output"]["peak_drawdown_blocked"] = bool(exit_info.get("peak_drawdown_blocked"))
        state["monitor_output"]["peak_drawdown_block_reason"] = str(exit_info.get("peak_drawdown_block_reason") or "")
        state["monitor_output"]["peak_drawdown_profit_floor_required_pct"] = exit_info.get(
            "peak_drawdown_profit_floor_required_pct"
        )
        state["monitor_output"]["peak_drawdown_profit_floor_met"] = bool(exit_info.get("peak_drawdown_profit_floor_met"))
        state["monitor_output"]["final_peak_drawdown_ratio"] = exit_info.get("final_peak_drawdown_ratio")
        state["monitor_output"]["peak_drawdown_source"] = str(exit_info.get("peak_drawdown_source") or "")
        state["monitor_output"]["exit_trigger_metric_name"] = str(exit_info.get("exit_trigger_metric_name") or "")
        state["monitor_output"]["exit_trigger_metric_value"] = exit_info.get("exit_trigger_metric_value")
        state["monitor_output"]["exit_trigger_metric_source"] = str(exit_info.get("exit_trigger_metric_source") or "")
        state["monitor_output"]["exit_gross_pnl_ratio"] = exit_info.get("gross_pnl_ratio")
        state["monitor_output"]["exit_technical_pnl_ratio"] = exit_info.get("technical_pnl_ratio")
        state["monitor_output"]["exit_stop_pnl_ratio"] = exit_info.get("stop_pnl_ratio")
        state["monitor_output"]["exit_stop_pnl_ratio_source"] = str(exit_info.get("stop_pnl_ratio_source") or "")
        state["monitor_output"]["exit_hard_stop_pnl_ratio"] = exit_info.get("hard_stop_pnl_ratio")
        state["monitor_output"]["exit_hard_stop_pnl_ratio_source"] = str(
            exit_info.get("hard_stop_pnl_ratio_source") or ""
        )
        state["monitor_output"]["exit_cost_drag_pressure"] = bool(exit_info.get("cost_drag_pressure"))
        state["monitor_output"]["exit_cost_drag_pressure_pct"] = exit_info.get("cost_drag_pressure_pct")
        state["monitor_output"]["exit_cost_drag_pressure_reason"] = str(exit_info.get("cost_drag_pressure_reason") or "")
        state["monitor_output"]["exit_stop_loss_cost_drag_blocked"] = bool(
            exit_info.get("stop_loss_cost_drag_blocked")
        )
        state["monitor_output"]["exit_stop_loss_cost_drag_blocked_reason"] = str(
            exit_info.get("stop_loss_cost_drag_blocked_reason") or ""
        )
        state["monitor_output"]["risk_reward_take_profit_target_pct"] = exit_info.get("risk_reward_take_profit_target_pct")
        state["monitor_output"]["risk_reward_take_profit_rung"] = exit_info.get("risk_reward_take_profit_rung")
        state["monitor_output"]["resistance_price"] = exit_info.get("resistance_price")
        state["monitor_output"]["resistance_price_source"] = str(exit_info.get("resistance_price_source") or "")
        state["monitor_output"]["resistance_distance_pct"] = exit_info.get("resistance_distance_pct")
        state["monitor_output"]["profit_time_stop_peak_giveback_pct"] = exit_info.get("profit_time_stop_peak_giveback_pct")
        state["monitor_output"]["partial_exit"] = bool(exit_info.get("partial_exit"))
        state["monitor_output"]["exit_qty"] = exit_info.get("exit_qty")
        state["monitor_output"]["exit_qty_fraction"] = exit_info.get("exit_qty_fraction")
        state["monitor_output"]["profit_ladder_level_pct"] = exit_info.get("profit_ladder_level_pct")
        state["monitor_output"]["profit_ladder_level_index"] = exit_info.get("profit_ladder_level_index")
        state["monitor_output"]["volume_ratio"] = exit_info.get("volume_ratio")
        state["monitor_output"]["execution_strength"] = exit_info.get("execution_strength")
        state["monitor_output"]["trade_strength"] = exit_info.get("trade_strength")
        state["monitor_output"]["opening_gap_chase_observed"] = bool(exit_info.get("opening_gap_chase_observed"))
        state["monitor_output"]["open_gap_pct"] = exit_info.get("open_gap_pct")
        state["monitor_output"]["prev_close_distance_pct"] = exit_info.get("prev_close_distance_pct")
        state["monitor_output"]["position_entry_risk_applied"] = bool(exit_info.get("position_entry_risk_applied"))
        state["monitor_output"]["position_entry_stop_loss_pct"] = exit_info.get("position_entry_stop_loss_pct")
        state["monitor_output"]["position_entry_stop_loss_source"] = str(exit_info.get("position_entry_stop_loss_source") or "")
        state["monitor_output"]["position_entry_invalidation_price"] = exit_info.get("position_entry_invalidation_price")
        state["monitor_output"]["received_policy"] = dict(entry_info.get("received_policy") or entry_received_policy or {})
        state["monitor_output"]["received_policy_source"] = str(entry_info.get("received_policy_source") or entry_policy_origin or "")
        state["monitor_output"]["policy_contract"] = dict(entry_info.get("policy_contract") or entry_policy_contract or {})
        state["monitor_output"]["effective_policy"] = dict(entry_info.get("effective_policy") or entry_applied_policy)
        state["monitor_output"]["effective_policy_source"] = str(entry_info.get("effective_policy_source") or "")
        state["monitor_output"]["effective_policy_source_chain"] = list(entry_info.get("effective_policy_source_chain") or [])
        state["monitor_output"]["policy_adjustments"] = dict(entry_info.get("policy_adjustments") or {})
        state["monitor_output"]["policy_adjustment_summary"] = str(entry_info.get("policy_adjustment_summary") or "")
        state["monitor_output"]["policy_adjustment_reasoning"] = str(entry_info.get("policy_adjustment_reasoning") or "")
        state["monitor_output"]["effective_policy_deltas"] = list(entry_info.get("effective_policy_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_applied"] = bool(entry_info.get("monitor_memory_bias_applied"))
        state["monitor_output"]["monitor_memory_bias_observation_only"] = bool(entry_info.get("monitor_memory_bias_observation_only"))
        state["monitor_output"]["monitor_memory_bias"] = dict(entry_info.get("monitor_memory_bias") or {})
        state["monitor_output"]["monitor_memory_bias_summary"] = dict(entry_info.get("monitor_memory_bias_summary") or {})
        state["monitor_output"]["monitor_memory_bias_deltas"] = list(entry_info.get("monitor_memory_bias_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_observed_deltas"] = list(entry_info.get("monitor_memory_bias_observed_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_hold_applied"] = bool(exit_info.get("monitor_memory_bias_hold_applied"))
        state["monitor_output"]["monitor_memory_bias_hold_deltas"] = list(exit_info.get("monitor_memory_bias_hold_deltas") or [])
        state["monitor_output"]["monitor_memory_bias_exit_applied"] = bool(exit_info.get("monitor_memory_bias_exit_applied"))
        state["monitor_output"]["monitor_memory_bias_exit_deltas"] = list(exit_info.get("monitor_memory_bias_exit_deltas") or [])
        state["monitor_output"]["commander_memory_application_trace"] = dict(commander_memory_application_trace)
        state["monitor_output"]["monitor_memory_application_trace"] = dict(commander_memory_application_trace)
        state["monitor_output"]["applied_policy"] = dict(entry_applied_policy)
        state["monitor_output"]["policy_source"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or "")
        state["monitor_output"]["policy_validation_status"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or "")
        state["monitor_output"]["policy_fallback_used"] = bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used"))
        state["monitor_output"]["policy_fallback_reason"] = str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or "")
        state["monitor_output"]["policy_partial_normalized"] = bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized"))
        state["monitor_output"]["policy_default_filled_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or [])
        state["monitor_output"]["policy_validation_missing_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or [])
        state["monitor_output"]["policy_validation_invalid_fields"] = list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or [])
        state["monitor_output"]["override_reason"] = str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or "")
        state["monitor_output"]["applied_policy_source_chain"] = list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or [])
        state["monitor_output"]["commander_context_consumed"] = bool(monitor_policy_trace.get("commander_context_consumed"))
        state["monitor_output"]["consumed_fields"] = list(monitor_policy_trace.get("consumed_fields") or [])
        state["monitor_output"]["shadow_used"] = bool(monitor_policy_trace.get("shadow_used"))
        state["monitor_output"]["strategist_fallback_used"] = bool(monitor_policy_trace.get("strategist_fallback_used"))
        state["monitor_output"]["hard_filter_passed"] = bool(entry_info.get("hard_filter_passed"))
        state["monitor_output"]["hard_filter_fail_reasons"] = list(entry_info.get("hard_filter_fail_reasons") or [])
        state["monitor_output"]["total_score"] = entry_info.get("total_score")
        state["monitor_output"]["score_breakdown"] = dict(entry_info.get("score_breakdown") or {})
        state["monitor_output"]["policy_interpretation"] = dict(entry_info.get("policy_interpretation") or {})
        state["monitor_output"]["signal_evidence"] = dict(entry_info.get("signal_evidence") or {})
        state["monitor_output"]["chart_structure_features"] = dict(entry_info.get("chart_structure_features") or {})
        state["monitor_output"]["policy_interpreter_trace"] = dict(entry_info.get("policy_interpreter_trace") or {})
        state["monitor_output"]["policy_alignment_summary"] = dict(entry_info.get("policy_alignment_summary") or {})
        state["monitor_output"]["policy_aware_gating"] = dict(entry_info.get("policy_aware_gating") or {})
        state["monitor_output"]["chart_structure_decision_hint"] = dict(entry_info.get("chart_structure_decision_hint") or {})
        state["monitor_output"]["no_trade_surface"] = dict(monitor_no_trade_surface)
        state["monitor_output"]["scanner_monitor_handoff"] = dict(scanner_monitor_handoff)
        state["monitor_output"]["entry_threshold"] = entry_info.get("entry_threshold")
        state["monitor_output"]["score_passed"] = bool(entry_info.get("score_passed"))
        state["monitor_output"]["scoring_mode"] = str(entry_info.get("scoring_mode") or "disabled")
        state["monitor_output"]["legacy_entry_decision"] = str(entry_info.get("legacy_entry_decision") or "WAIT")
        state["monitor_output"]["scoring_entry_decision"] = str(entry_info.get("scoring_entry_decision") or "WAIT")
    state["monitor_evaluation"] = {
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
        "posture": current_posture,
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "entry_pattern": str(entry_info.get("pattern") or ""),
        "entry_passed_checks": list(entry_info.get("passed_checks") or []),
        "entry_failed_checks": list(entry_info.get("failed_checks") or []),
        "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "chart_structure_features": dict(entry_info.get("chart_structure_features") or {}),
        "policy_aware_gating": dict(entry_info.get("policy_aware_gating") or {}),
        "chart_structure_decision_hint": dict(entry_info.get("chart_structure_decision_hint") or {}),
        "entry_lane": str(entry_info.get("entry_lane") or "strict"),
        "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
        "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
        "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
        "cost_drag_pct": entry_info.get("cost_drag_pct"),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "timing_assessment": dict(monitor_policy_trace.get("timing_assessment") or {}),
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "flow_instruction_applied": bool(monitor_policy_trace.get("flow_instruction_applied")),
        "no_trade_reason_applied": bool(monitor_policy_trace.get("no_trade_reason_applied")),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    state["monitor_action_decision"] = {
        "decision": str((state.get("monitor_output") or {}).get("intent_side") or "NOOP"),
        "action_reason_human": str((state.get("monitor_output") or {}).get("entry_exit_reason") or current_reason),
        "decision_reason_chain": list(reason_chain),
        "confidence": float(_to_float(entry_info.get("confidence"))),
        "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
        "triggered_rules": list(triggered_rules),
        "blocked_rules": list(dict.fromkeys(blocked_rules))[:8],
        "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
        "policy_contract": dict(entry_info.get("policy_contract") or entry_policy_contract or {}),
        "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
        "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
        "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
        "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
        "applied_policy": dict(entry_applied_policy),
        "policy_source": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or ""),
        "policy_validation_status": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or ""),
        "policy_fallback_used": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used")),
        "policy_fallback_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or ""),
        "policy_partial_normalized": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized")),
        "policy_default_filled_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or []),
        "policy_validation_missing_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or []),
        "policy_validation_invalid_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or []),
        "override_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or ""),
        "applied_policy_source_chain": list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or []),
        "policy_ref": dict(monitor_policy_trace.get("policy_ref") or {}),
        "entry_check_summary": str(monitor_policy_trace.get("entry_check_summary") or ""),
        "entry_blockers": list(monitor_policy_trace.get("entry_blockers") or []),
        "exit_trigger_basis": dict(monitor_policy_trace.get("exit_trigger_basis") or {}),
        "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
        "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
        "hard_filter_passed": bool(entry_info.get("hard_filter_passed")),
        "hard_filter_fail_reasons": list(entry_info.get("hard_filter_fail_reasons") or []),
        "total_score": entry_info.get("total_score"),
        "score_breakdown": dict(entry_info.get("score_breakdown") or {}),
        "entry_threshold": entry_info.get("entry_threshold"),
        "score_passed": bool(entry_info.get("score_passed")),
        "scoring_mode": str(entry_info.get("scoring_mode") or "disabled"),
        "legacy_entry_decision": str(entry_info.get("legacy_entry_decision") or "WAIT"),
        "scoring_entry_decision": str(entry_info.get("scoring_entry_decision") or "WAIT"),
        "no_trade_surface": dict(monitor_no_trade_surface),
        "scanner_monitor_handoff": dict(scanner_monitor_handoff),
        "commander_context_consumed": bool(monitor_policy_trace.get("commander_context_consumed")),
        "consumed_fields": list(monitor_policy_trace.get("consumed_fields") or []),
        "shadow_used": bool(monitor_policy_trace.get("shadow_used")),
        "strategist_fallback_used": bool(monitor_policy_trace.get("strategist_fallback_used")),
    }
    _emit_monitor_event(
        state,
        name="cycle_summary",
        payload={
            "selected_symbol": str((selected.get("symbol") if isinstance(selected, dict) else "") or ""),
            "monitor_symbol": monitor_symbol,
            "posture": current_posture,
            "monitor_reason": current_reason,
            "open_position_count": int(open_position_count),
            "has_intent": bool(intents),
            "intent_side": str((state.get("monitor_output") or {}).get("intent_side") or "NOOP"),
            "active_exit_axis": str(exit_info.get("active_exit_axis") or ""),
            "price_source": str(exit_info.get("price_source") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
            "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
            "minutes_to_close": entry_info.get("minutes_to_close"),
            "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
            "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
            "closeout_window_active": bool(entry_info.get("closeout_window_active")),
            "entry_blocker_surface": dict(entry_blocker_surface),
        },
        symbol=monitor_symbol,
    )
    _log_monitor_summary(
        state,
        {
            "has_intent": bool(intents),
            "intent_count": len(intents),
            "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
            "order_status_fallback": bool(fallback_reasons),
            "exit_policy_enabled": bool(exit_info.get("enabled")),
            "exit_evaluated": bool(exit_info.get("evaluated")),
            "exit_triggered": bool(exit_info.get("triggered")),
            "exit_reason": str(exit_info.get("reason") or ""),
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "peak_price": exit_info.get("peak_price"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "price_source": str(exit_info.get("price_source") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
            "sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
            "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
            "exit_confirm_count": int(exit_info.get("exit_confirm_count") or 0),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            "sell_guard_reason": str(exit_info.get("sell_guard_reason") or ""),
            "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "exit_vs_strategy_intent": dict(exit_info.get("exit_vs_strategy_intent") or {}),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "position_sizing_enabled": bool(sizing_info.get("enabled")),
            "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
            "position_sizing_qty": int(sizing_info.get("qty") or 0),
            "position_sizing_reason": str(sizing_info.get("reason") or ""),
            "position_sizing_stop_loss_pct": (sizing_info.get("inputs") or {}).get("stop_loss_pct")
            if isinstance(sizing_info.get("inputs"), dict)
            else None,
            "position_sizing_stop_loss_source": str(
                ((sizing_info.get("inputs") or {}).get("stop_loss_source") if isinstance(sizing_info.get("inputs"), dict) else "")
                or ""
            ),
            "position_sizing_invalidation_price": (sizing_info.get("inputs") or {}).get("invalidation_price")
            if isinstance(sizing_info.get("inputs"), dict)
            else None,
            "open_position_count": int(open_position_count),
            "block_buy_when_open_position": bool(block_buy_open_position),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
            "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
            "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
            "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
            "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
            "minutes_to_close": entry_info.get("minutes_to_close"),
            "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
            "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
            "closeout_window_active": bool(entry_info.get("closeout_window_active")),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_reason": str(entry_info.get("reason") or ""),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "entry_lane": str(entry_info.get("entry_lane") or "strict"),
            "entry_cost_filter": dict(entry_info.get("entry_cost_filter") or {}),
            "cost_adjusted_edge_ok": bool(entry_info.get("cost_adjusted_edge_ok")),
            "cost_adjusted_edge_pct": entry_info.get("cost_adjusted_edge_pct"),
            "cost_drag_pct": entry_info.get("cost_drag_pct"),
            "decision_outcome": str(monitor_no_trade_surface.get("decision_outcome") or final_entry_decision),
            "pre_intent_decision": str(monitor_no_trade_surface.get("pre_intent_decision") or ""),
            "no_trade_stage": str(monitor_no_trade_surface.get("no_trade_stage") or ""),
            "no_trade_reason_code": str(monitor_no_trade_surface.get("no_trade_reason_code") or ""),
            "no_trade_reason_summary": str(monitor_no_trade_surface.get("no_trade_reason_summary") or ""),
            "dominant_blocker": str(monitor_no_trade_surface.get("dominant_blocker") or ""),
            "blocker_family": str(monitor_no_trade_surface.get("blocker_family") or ""),
            "blocker_metrics": dict(monitor_no_trade_surface.get("blocker_metrics") or {}),
            "distance_to_ready": dict(monitor_no_trade_surface.get("distance_to_ready") or {}),
            "near_ready_flag": bool(monitor_no_trade_surface.get("near_ready_flag")),
            "required_checks_failed": list(monitor_no_trade_surface.get("required_checks_failed") or []),
            "preferred_checks_failed": list(monitor_no_trade_surface.get("preferred_checks_failed") or []),
            "relaxable_checks_failed": list(monitor_no_trade_surface.get("relaxable_checks_failed") or []),
            "evidence_snapshot": dict(monitor_no_trade_surface.get("evidence_snapshot") or {}),
            "scanner_monitor_handoff": dict(scanner_monitor_handoff),
            "entry_blocker_surface": dict(entry_blocker_surface),
        },
    )
    append_decision_trace(
        state,
        agent="monitor",
        event="entry_exit_decision",
        payload={
            "selected_symbol": str((selected.get("symbol") if isinstance(selected, dict) else "") or ""),
            "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
            "exit_reason": str(exit_info.get("reason") or ""),
            "thresholds": dict(exit_info.get("thresholds") or {}),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "peak_drawdown": exit_info.get("peak_drawdown"),
            "peak_price": exit_info.get("peak_price"),
            "vwap_distance": exit_info.get("vwap_distance"),
            "price_source": str(exit_info.get("price_source") or ""),
            "price_source_policy": str(exit_info.get("price_source_policy") or ""),
            "feature_source": str(exit_info.get("feature_source") or ""),
            "min_hold_sec": int(exit_info.get("min_hold_sec") or 0),
            "sell_cooldown_sec": int(exit_info.get("sell_cooldown_sec") or 0),
            "exit_confirm_ticks": int(exit_info.get("exit_confirm_ticks") or 0),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "strategy_horizon": str(exit_info.get("strategy_horizon") or ""),
            "source_strategy_horizon": str(exit_info.get("source_strategy_horizon") or ""),
            "horizon_behavior_translation": dict(exit_info.get("horizon_behavior_translation") or {}),
            "position_strategy_context_applied": bool(exit_info.get("position_strategy_context_applied")),
            "position_strategy_context_symbol": str(exit_info.get("position_strategy_context_symbol") or ""),
            "position_strategy_context_source": str(exit_info.get("position_strategy_context_source") or ""),
            "strategy_frame_adjustments": list(exit_info.get("strategy_frame_adjustments") or []),
            "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
            "entry_evaluated": bool(entry_info.get("evaluated")),
            "entry_triggered": bool(entry_info.get("triggered")),
            "entry_pattern": str(entry_info.get("pattern") or ""),
            "entry_signal_chain": list(entry_info.get("signal_chain") or []),
            "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
            "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
            "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
            "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
            "entry_metrics": dict(entry_info.get("metrics") or {}),
            "entry_thresholds": dict(entry_info.get("thresholds") or {}),
            "received_policy": dict(entry_info.get("received_policy") or entry_received_policy or {}),
            "received_policy_source": str(entry_info.get("received_policy_source") or entry_policy_origin or ""),
            "effective_policy": dict(entry_info.get("effective_policy") or entry_applied_policy),
            "effective_policy_source": str(entry_info.get("effective_policy_source") or ""),
            "effective_policy_source_chain": list(entry_info.get("effective_policy_source_chain") or []),
            "policy_adjustments": dict(entry_info.get("policy_adjustments") or {}),
            "policy_adjustment_summary": str(entry_info.get("policy_adjustment_summary") or ""),
            "policy_adjustment_reasoning": str(entry_info.get("policy_adjustment_reasoning") or ""),
            "effective_policy_deltas": list(entry_info.get("effective_policy_deltas") or []),
            "applied_policy": dict(entry_applied_policy),
            "policy_source": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_source") or ""),
            "policy_validation_status": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_status") or ""),
            "policy_fallback_used": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_used")),
            "policy_fallback_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("policy_fallback_reason") or ""),
            "policy_partial_normalized": bool((monitor_policy_trace.get("policy_ref") or {}).get("policy_partial_normalized")),
            "policy_default_filled_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_default_filled_fields") or []),
            "policy_validation_missing_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_missing_fields") or []),
            "policy_validation_invalid_fields": list((monitor_policy_trace.get("policy_ref") or {}).get("policy_validation_invalid_fields") or []),
            "override_reason": str((monitor_policy_trace.get("policy_ref") or {}).get("override_reason") or ""),
            "applied_policy_source_chain": list((monitor_policy_trace.get("policy_ref") or {}).get("applied_policy_source_chain") or []),
            "entry_passed_checks": list(entry_info.get("passed_checks") or []),
            "entry_failed_checks": list(entry_info.get("failed_checks") or []),
            "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
            "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
            "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
            "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
            "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
        },
    )
    try:
        record_decision_bridge(
            run_id=run_id,
            agent="monitor",
            stage="decision_bridge",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "monitor_policy": dict(monitor_policy),
                "intents_preview": [
                    {
                        "symbol": str(x.get("symbol") or ""),
                        "side": str(x.get("side") or ""),
                        "qty": _to_int(x.get("qty")),
                    }
                    for x in list(intents)[:3]
                    if isinstance(x, dict)
                ],
            },
            parsed_output={
                "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                "exit_reason": str(exit_info.get("reason") or ""),
                "monitor_reason": str(exit_info.get("monitor_reason") or ""),
                "position_age_seconds": exit_info.get("position_age_seconds"),
                "peak_drawdown": exit_info.get("peak_drawdown"),
                "peak_price": exit_info.get("peak_price"),
                "vwap_distance": exit_info.get("vwap_distance"),
                "price_source": str(exit_info.get("price_source") or ""),
                "feature_source": str(exit_info.get("feature_source") or ""),
                "exit_signal_detected": bool(exit_info.get("exit_signal_detected")),
                "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
                "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
                "sell_guard_reason": str(exit_info.get("sell_guard_reason") or ""),
                "exit_policy_guard_adjustments": list(exit_info.get("exit_policy_guard_adjustments") or []),
                "post_exit_cooldown_sec": int(post_exit_cooldown_sec),
                "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
                "buy_blocked_post_exit_cooldown": bool(buy_blocked_post_exit_cooldown),
                "post_exit_cooldown_remaining_sec": int(post_exit_cooldown_remaining_sec),
                "minutes_to_close": entry_info.get("minutes_to_close"),
                "eod_flat_cutoff_min": int(entry_info.get("eod_flat_cutoff_min") or 0),
                "buy_closeout_cutoff_min": int(entry_info.get("buy_closeout_cutoff_min") or 0),
                "closeout_window_active": bool(entry_info.get("closeout_window_active")),
                "entry_evaluated": bool(entry_info.get("evaluated")),
                "entry_triggered": bool(entry_info.get("triggered")),
                "entry_pattern": str(entry_info.get("pattern") or ""),
                "entry_reason": str(entry_info.get("reason") or ""),
                "entry_signal_chain": list(entry_info.get("signal_chain") or []),
                "entry_condition_path": str(entry_info.get("entry_condition_path") or ""),
                "entry_condition_paths_passed": list(entry_info.get("entry_condition_paths_passed") or []),
                "entry_condition_scores": dict(entry_info.get("condition_scores") or {}),
                "entry_grouped_logic_trace": dict(entry_info.get("grouped_logic_trace") or {}),
                "entry_metrics": dict(entry_info.get("metrics") or {}),
                "entry_thresholds": dict(entry_info.get("thresholds") or {}),
                "entry_passed_checks": list(entry_info.get("passed_checks") or []),
                "entry_failed_checks": list(entry_info.get("failed_checks") or []),
                "entry_primary_failure_axis": str(entry_info.get("primary_failure_axis") or ""),
                "entry_threshold_margins": dict(entry_info.get("threshold_margins") or {}),
                "entry_transition_trace": dict(entry_info.get("entry_transition_trace") or {}),
                "entry_guard_blocked": bool(entry_info.get("guard_blocked")),
                "entry_guard_reason": str(entry_info.get("guard_reason") or ""),
            },
            decision_link={
                "decision_chain": {
                    "theme": str((state.get("themes") or [""])[0] if isinstance(state.get("themes"), list) and state.get("themes") else ""),
                    "scanner_selected": state.get("top_stock") or (
                        str(selected.get("symbol") or "") if isinstance(selected, dict) else ""
                    ),
                    "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                    "exit_reason": str(exit_info.get("reason") or ""),
                }
            },
        )
    except Exception:
        pass
    try:
        write_monitor_artifact(state)
    except Exception:
        pass
    return state
