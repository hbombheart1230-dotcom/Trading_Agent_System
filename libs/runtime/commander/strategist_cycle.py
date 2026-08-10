from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from libs.runtime.commander.shadow_runtime import (
    mark_pre_buy_refresh_shadow,
    mark_post_scanner_refresh_shadow,
    mark_strategist_executed,
    mark_strategist_skipped,
    reset_post_scanner_refresh_shadow,
    reset_pre_buy_refresh_shadow,
)


StateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def resolve_strategist_cache_use(
    state: Dict[str, Any],
    *,
    should_use_cached_from_commander_skip_fn: Callable[[Dict[str, Any]], Tuple[bool, Dict[str, Any]]],
    should_use_cached_when_flat_fn: Callable[[Dict[str, Any]], Tuple[bool, Dict[str, Any]]],
) -> Tuple[bool, Dict[str, Any]]:
    reused_strategist_cache, cache_payload = should_use_cached_from_commander_skip_fn(state)
    if not reused_strategist_cache and str(cache_payload.get("reason") or "").strip() != "commander_requested_refresh":
        reused_strategist_cache, cache_payload = should_use_cached_when_flat_fn(state)
    return reused_strategist_cache, cache_payload


def run_pre_scanner_strategist_cycle(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    reused_strategist_cache: bool,
    cache_payload: Dict[str, Any],
    prior_cached_output: Dict[str, Any],
    hydrate_strategist_output_cache_fn: StateFn,
    log_commander_event_fn: Callable[[Dict[str, Any], str, Dict[str, Any]], None],
    attach_reporter_feedback_policy_fn: Callable[..., Dict[str, Any]],
    attach_applied_policy_fn: StateFn,
    strategist_node_fn: StateFn,
    shadow_market_changed_fn: Callable[[Dict[str, Any], Dict[str, Any]], bool],
    strategist_frame_blocked_fn: Callable[[Dict[str, Any]], bool],
    apply_strategist_block_fn: Callable[..., Dict[str, Any]],
    persist_strategist_output_cache_fn: StateFn,
) -> Tuple[Dict[str, Any], bool, bool]:
    if reused_strategist_cache:
        mark_strategist_skipped(shadow_runtime, used_cached=True)
        reset_pre_buy_refresh_shadow(shadow_runtime)
        reset_post_scanner_refresh_shadow(shadow_runtime)
        shadow_runtime["market_changed"] = False
        shadow_runtime["repeated_same_context"] = True
        state = hydrate_strategist_output_cache_fn(state)
        state["runtime_fast_path"] = dict(cache_payload)
        log_commander_event_fn(state, "fast_path", {"path": "integrated_chain_cached_frame", **cache_payload})
        return state, reused_strategist_cache, False

    if str(cache_payload.get("reason") or "").strip() == "commander_requested_refresh":
        mark_pre_buy_refresh_shadow(shadow_runtime, cache_payload)
        log_commander_event_fn(state, "pre_buy_refresh", {"path": "integrated_chain", **cache_payload})
    else:
        reset_pre_buy_refresh_shadow(shadow_runtime)
    reset_post_scanner_refresh_shadow(shadow_runtime)
    state = attach_reporter_feedback_policy_fn(state, selected_route="full_cycle", phase="session")
    state = attach_applied_policy_fn(state)
    state = strategist_node_fn(state)
    mark_strategist_executed(shadow_runtime, state, used_cached=False)
    market_changed = shadow_market_changed_fn(
        prior_cached_output if isinstance(prior_cached_output, dict) else {},
        state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {},
    )
    shadow_runtime["market_changed"] = market_changed
    shadow_runtime["repeated_same_context"] = market_changed is False
    if strategist_frame_blocked_fn(state):
        state = apply_strategist_block_fn(state, phase="integrated_chain")
        return state, reused_strategist_cache, True
    state = persist_strategist_output_cache_fn(state)
    return state, reused_strategist_cache, False


def run_post_scanner_refresh_cycle(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    reused_strategist_cache: bool,
    post_scanner_selected_symbol: str,
    scanner_node_fn: StateFn,
    strategist_node_fn: StateFn,
    build_commander_decision_fn: Callable[..., Dict[str, Any]],
    force_selected_symbol_tactical_refresh_decision_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    commander_post_scanner_refresh_enabled_fn: Callable[[Dict[str, Any]], bool],
    log_commander_event_fn: Callable[[Dict[str, Any], str, Dict[str, Any]], None],
    attach_reporter_feedback_policy_fn: Callable[..., Dict[str, Any]],
    attach_applied_policy_fn: StateFn,
    strategist_frame_blocked_fn: Callable[[Dict[str, Any]], bool],
    apply_strategist_block_fn: Callable[..., Dict[str, Any]],
    persist_strategist_output_cache_fn: StateFn,
    portfolio_open_position_count_fn: Callable[[Dict[str, Any]], int],
    resolve_risk_max_positions_fn: Callable[[Dict[str, Any]], int],
) -> Tuple[Dict[str, Any], bool, bool]:
    if not (
        portfolio_open_position_count_fn(state) < resolve_risk_max_positions_fn(state)
        and (
            reused_strategist_cache
            or (bool(post_scanner_selected_symbol) and bool(str(state.get("run_id") or "").strip()))
        )
    ):
        return state, reused_strategist_cache, False

    post_scanner_path = (
        "integrated_chain_cached_frame_post_scanner"
        if reused_strategist_cache
        else "integrated_chain_post_scanner"
    )
    post_scanner_decision = build_commander_decision_fn(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value=post_scanner_path,
        reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
    )
    post_scanner_decision = force_selected_symbol_tactical_refresh_decision_fn(state, post_scanner_decision)
    post_scanner_refresh_requested = bool(post_scanner_decision.get("strategist_refresh_requested"))
    if post_scanner_refresh_requested:
        if not commander_post_scanner_refresh_enabled_fn(state):
            refresh_context = (
                dict(post_scanner_decision.get("strategist_refresh_context") or {})
                if isinstance(post_scanner_decision.get("strategist_refresh_context"), dict)
                else {}
            )
            mark_post_scanner_refresh_shadow(
                shadow_runtime,
                decision=post_scanner_decision,
                refresh_context=refresh_context,
                skipped=True,
                skip_reason="post_scanner_refresh_disabled",
            )
            state["commander_shadow_runtime"] = dict(shadow_runtime)
            log_commander_event_fn(
                state,
                "post_scanner_refresh_skipped",
                {
                    "path": post_scanner_path,
                    **dict(refresh_context),
                    "strategist_refresh_reason": str(post_scanner_decision.get("strategist_refresh_reason") or ""),
                    "skip_reason": "post_scanner_refresh_disabled",
                },
            )
            return state, reused_strategist_cache, False

        state["commander_decision"] = dict(post_scanner_decision)
        refresh_context = (
            dict(post_scanner_decision.get("strategist_refresh_context") or {})
            if isinstance(post_scanner_decision.get("strategist_refresh_context"), dict)
            else {}
        )
        mark_post_scanner_refresh_shadow(
            shadow_runtime,
            decision=post_scanner_decision,
            refresh_context=refresh_context,
        )
        state["commander_shadow_runtime"] = dict(shadow_runtime)
        log_commander_event_fn(
            state,
            "post_scanner_refresh",
            {
                "path": post_scanner_path,
                **dict(refresh_context),
                "strategist_refresh_reason": str(post_scanner_decision.get("strategist_refresh_reason") or ""),
            },
        )
        from libs.runtime.q9_decision_snapshots import capture_pre_refresh_scanner_snapshot

        capture_pre_refresh_scanner_snapshot(state)
        state = attach_reporter_feedback_policy_fn(state, selected_route="full_cycle", phase="session")
        state = attach_applied_policy_fn(state)
        state = strategist_node_fn(state)
        mark_strategist_executed(shadow_runtime, state, used_cached=False)
        if strategist_frame_blocked_fn(state):
            state = apply_strategist_block_fn(state, phase="integrated_chain")
            return state, reused_strategist_cache, True
        state = persist_strategist_output_cache_fn(state)
        state["runtime_fast_path"] = {
            "reason": "post_scanner_selected_symbol_refresh",
            "strategist_refresh_reason": str(post_scanner_decision.get("strategist_refresh_reason") or ""),
            "selected_symbol": str(refresh_context.get("selected_symbol") or ""),
        }
        reused_strategist_cache = False
        state = scanner_node_fn(state)
        return state, reused_strategist_cache, False

    refresh_context = (
        dict(post_scanner_decision.get("strategist_refresh_context") or {})
        if isinstance(post_scanner_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    if bool(refresh_context.get("post_scanner_refresh_suppressed")):
        reset_post_scanner_refresh_shadow(shadow_runtime)
        shadow_runtime["post_scanner_refresh_context"] = dict(refresh_context)
        state["commander_decision"] = dict(post_scanner_decision)
        state["commander_shadow_runtime"] = dict(shadow_runtime)
        log_commander_event_fn(
            state,
            "post_scanner_refresh_suppressed",
            {
                "path": post_scanner_path,
                **dict(refresh_context),
                "skip_reason": str(refresh_context.get("post_scanner_refresh_suppressed_reason") or ""),
            },
        )
    return state, reused_strategist_cache, False
