from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from libs.runtime.commander.execution import run_monitor_decision_path
from libs.runtime.commander.shadow_runtime import mark_strategist_executed, mark_strategist_skipped


StateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def run_monitor_only_fast_path(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    fast_path_payload: Dict[str, Any],
    monitor_node_fn: StateFn,
    decision_node_fn: StateFn,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    hydrate_strategist_output_cache_fn: StateFn,
    attach_reporter_feedback_policy_fn: Callable[..., Dict[str, Any]],
    attach_applied_policy_fn: StateFn,
    build_commander_decision_fn: Callable[..., Dict[str, Any]],
    portfolio_open_position_symbols_fn: Callable[[Dict[str, Any]], list[str]],
    select_open_position_focus_symbol_fn: Callable[..., str],
    log_commander_event_fn: Callable[[Dict[str, Any], str, Dict[str, Any]], None],
    hydrate_monitor_symbol_features_fn: StateFn,
    intent_from_monitor_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_packet_from_state_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    mark_strategist_skipped(shadow_runtime, used_cached=False)
    state = hydrate_strategist_output_cache_fn(state)
    state = attach_reporter_feedback_policy_fn(state, selected_route="monitor_only", phase="session")
    state = attach_applied_policy_fn(state)
    state["commander_decision"] = build_commander_decision_fn(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value="integrated_chain_monitor_only",
        reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
    )
    held_symbols = portfolio_open_position_symbols_fn(state)
    focus_symbol = select_open_position_focus_symbol_fn(state, fallback_symbols=held_symbols)
    if focus_symbol:
        state["selected"] = {
            "symbol": focus_symbol,
            "_monitor_synthetic_selected": True,
        }
    else:
        state.pop("selected", None)
    state.pop("scanner_output", None)
    state["runtime_fast_path"] = dict(fast_path_payload)
    log_commander_event_fn(state, "fast_path", {"path": "integrated_chain_monitor_only", **fast_path_payload})
    state = run_monitor_decision_path(
        state,
        shadow_runtime=shadow_runtime,
        hydrate_monitor_symbol_features_fn=hydrate_monitor_symbol_features_fn,
        monitor_node_fn=monitor_node_fn,
        decision_node_fn=decision_node_fn,
        execute_fn=execute_fn,
        emit_trade_report_fn=emit_trade_report_fn,
        update_state_after_execution_fn=update_state_after_execution_fn,
        intent_from_monitor_state_fn=intent_from_monitor_state_fn,
        build_packet_from_state_fn=build_packet_from_state_fn,
    )
    state["path"] = "integrated_chain_monitor_only"
    return state


def run_closeout_guard_fast_path(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    closeout_payload: Dict[str, Any],
    strategist_node_fn: StateFn,
    monitor_node_fn: StateFn,
    decision_node_fn: StateFn,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    hydrate_strategist_output_cache_fn: StateFn,
    attach_reporter_feedback_policy_fn: Callable[..., Dict[str, Any]],
    attach_applied_policy_fn: StateFn,
    build_commander_decision_fn: Callable[..., Dict[str, Any]],
    hydrate_closeout_account_orders_fn: StateFn,
    pending_buy_cancel_intents_from_account_orders_fn: Callable[[Dict[str, Any]], list[Dict[str, Any]]],
    build_packet_from_state_fn: Callable[..., Dict[str, Any]],
    log_commander_event_fn: Callable[[Dict[str, Any], str, Dict[str, Any]], None],
    record_absent_later_stage_llm_reviews_fn: StateFn,
    portfolio_open_position_symbols_fn: Callable[[Dict[str, Any]], list[str]],
    select_open_position_focus_symbol_fn: Callable[..., str],
    run_stage4_carry_review_fn: Callable[..., Tuple[Dict[str, Any], bool]],
    strategist_frame_blocked_fn: Callable[[Dict[str, Any]], bool],
    apply_strategist_block_fn: Callable[..., Dict[str, Any]],
    hydrate_monitor_symbol_features_fn: StateFn,
    intent_from_monitor_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    mark_strategist_skipped(shadow_runtime, used_cached=False)
    state = hydrate_strategist_output_cache_fn(state)
    state = attach_reporter_feedback_policy_fn(state, selected_route="closeout", phase="session")
    state = attach_applied_policy_fn(state)
    state["runtime_fast_path"] = dict(closeout_payload)
    state["session_closeout_guard"] = dict(closeout_payload)
    state["commander_decision"] = build_commander_decision_fn(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value="integrated_chain_closeout_guard",
        reason_text=str(closeout_payload.get("reason") or ""),
    )
    state = hydrate_closeout_account_orders_fn(state)
    pending_buy_cancel_intents = pending_buy_cancel_intents_from_account_orders_fn(state)
    if pending_buy_cancel_intents:
        cancel_intent = dict(pending_buy_cancel_intents[0])
        state["selected"] = {
            "symbol": cancel_intent.get("symbol"),
            "_monitor_synthetic_selected": True,
            "_closeout_guard_selected": True,
            "_pending_buy_cancel_selected": True,
        }
        state["commander_pending_buy_cancel"] = {
            "detected": True,
            "intent": dict(cancel_intent),
            "candidate_count": len(pending_buy_cancel_intents),
            "reason": "session_closeout_pending_buy_cancel",
        }
        state["decision"] = "approve"
        state["decision_reason"] = "session_closeout_pending_buy_cancel"
        state["decision_packet"] = build_packet_from_state_fn(state, intent=cancel_intent)
        log_commander_event_fn(
            state,
            "pending_buy_cancel",
            {
                "path": "integrated_chain_closeout_guard",
                "symbol": cancel_intent.get("symbol"),
                "orig_ord_no": cancel_intent.get("orig_ord_no"),
                "candidate_count": len(pending_buy_cancel_intents),
            },
        )
        state = execute_fn(state)
        shadow_runtime["monitor_decision"] = "CANCEL"
        shadow_runtime["executor_action"] = str(
            (((state.get("execution") or {}).get("order") or {}).get("action") or "CANCEL")
        )
        shadow_runtime["executor_status"] = str(
            ((state.get("execution") or {}).get("reason")
            or ((state.get("execution") or {}).get("ok_source") or ""))
        )
        state["path"] = "integrated_chain_closeout_guard"
        record_absent_later_stage_llm_reviews_fn(state)
        return state

    held_symbols = portfolio_open_position_symbols_fn(state)
    focus_symbol = select_open_position_focus_symbol_fn(state, fallback_symbols=held_symbols)
    if focus_symbol:
        state["selected"] = {
            "symbol": focus_symbol,
            "_monitor_synthetic_selected": True,
            "_closeout_guard_selected": True,
        }
    else:
        state.pop("selected", None)
    state.pop("scanner_output", None)
    if held_symbols:
        state, stage4_ran = run_stage4_carry_review_fn(
            state,
            strategist_node_fn,
            review_reason="session_closeout_carry_review",
            phase="closeout",
        )
        if stage4_ran:
            mark_strategist_executed(shadow_runtime, state, used_cached=False)
            shadow_runtime["stage4_carry_review_requested"] = True
            shadow_runtime["stage4_carry_review_reason"] = "session_closeout_carry_review"
            state["commander_shadow_runtime"] = dict(shadow_runtime)
            if strategist_frame_blocked_fn(state):
                return apply_strategist_block_fn(state, phase="closeout")

    log_commander_event_fn(state, "fast_path", {"path": "integrated_chain_closeout_guard", **closeout_payload})
    state = run_monitor_decision_path(
        state,
        shadow_runtime=shadow_runtime,
        hydrate_monitor_symbol_features_fn=hydrate_monitor_symbol_features_fn,
        monitor_node_fn=monitor_node_fn,
        decision_node_fn=decision_node_fn,
        execute_fn=execute_fn,
        emit_trade_report_fn=emit_trade_report_fn,
        update_state_after_execution_fn=update_state_after_execution_fn,
        intent_from_monitor_state_fn=intent_from_monitor_state_fn,
        build_packet_from_state_fn=build_packet_from_state_fn,
    )
    state["path"] = "integrated_chain_closeout_guard"
    record_absent_later_stage_llm_reviews_fn(state)
    return state


def run_pre_entry_exit_sweep_if_needed(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    monitor_node_fn: StateFn,
    decision_node_fn: StateFn,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    portfolio_open_position_count_fn: Callable[[Dict[str, Any]], int],
    attach_reporter_feedback_policy_fn: Callable[..., Dict[str, Any]],
    attach_applied_policy_fn: StateFn,
    run_pre_entry_exit_sweep_fn: Callable[..., Tuple[Dict[str, Any], bool]],
    record_absent_later_stage_llm_reviews_fn: StateFn,
) -> Tuple[Dict[str, Any], bool]:
    if portfolio_open_position_count_fn(state) <= 0:
        return state, False

    state = attach_reporter_feedback_policy_fn(state, selected_route="monitor_only", phase="session")
    state = attach_applied_policy_fn(state)
    state, pre_entry_exit_executed = run_pre_entry_exit_sweep_fn(
        state,
        monitor_node_fn=monitor_node_fn,
        decision_node_fn=decision_node_fn,
        execute_fn=execute_fn,
        emit_trade_report_fn=emit_trade_report_fn,
        update_state_after_execution_fn=update_state_after_execution_fn,
        shadow_runtime=shadow_runtime,
    )
    state["commander_shadow_runtime"] = dict(shadow_runtime)
    if pre_entry_exit_executed:
        record_absent_later_stage_llm_reviews_fn(state)
        return state, True
    return state, False
