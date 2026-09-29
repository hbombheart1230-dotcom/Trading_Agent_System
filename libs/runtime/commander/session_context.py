from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


StateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def seed_shadow_prior_context(
    state: Dict[str, Any],
    *,
    ensure_shadow_runtime_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    strategist_cache_payload_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    seed_prior_context_fn: Callable[..., None],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    shadow_runtime = ensure_shadow_runtime_fn(state)
    prior_cache_payload = strategist_cache_payload_fn(state)
    prior_cached_output = prior_cache_payload.get("output") if isinstance(prior_cache_payload.get("output"), dict) else {}
    seed_prior_context_fn(
        state,
        prior_cached_output=prior_cached_output if isinstance(prior_cached_output, dict) else {},
    )
    shadow_runtime = ensure_shadow_runtime_fn(state)
    return shadow_runtime, prior_cache_payload, prior_cached_output if isinstance(prior_cached_output, dict) else {}


def build_integrated_chain_session_context(
    state: Dict[str, Any],
    *,
    build_portfolio_snapshot_fn: StateFn,
    build_open_order_snapshot_fn: StateFn,
    build_execution_readiness_fn: StateFn,
    build_risk_context_fn: StateFn,
    apply_portfolio_preflight_guard_fn: Callable[..., Tuple[bool, Dict[str, Any]]],
    build_commander_decision_fn: Callable[..., Dict[str, Any]],
) -> Tuple[Dict[str, Any], bool]:
    state = build_portfolio_snapshot_fn(state)
    # P0-A (real-readiness hardening): unconditional, every-tick, same
    # point as position reconciliation -- deliberately BEFORE the
    # portfolio preflight guard's own possible early-return, so the
    # open-order evidence is always this tick's own, never a stale
    # carry-over from a tick that short-circuited earlier.
    state = build_open_order_snapshot_fn(state)
    # P1 (execution readiness authority): consumes this SAME tick's
    # portfolio/open-order evidence plus runtime ownership state -- must
    # run after both, still unconditionally and still before the
    # preflight guard's own possible early-return, so
    # state["execution_readiness"] always reflects this tick, never a
    # stale carry-over from an earlier short-circuited tick.
    state = build_execution_readiness_fn(state)
    snaps = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {
        **dict(snaps or {}),
        "portfolio": state.get("portfolio_snapshot"),
        "open_orders": state.get("open_order_snapshot"),
    }
    should_continue, state = apply_portfolio_preflight_guard_fn(state, phase="session")
    if not should_continue:
        return state, False
    state = build_risk_context_fn(state)
    state["commander_decision"] = build_commander_decision_fn(
        state,
        mode_value="integrated_chain",
        phase_value=str(state.get("runtime_phase") or "session"),
        status_value=str(state.get("runtime_status") or "planning"),
        path_value=str(state.get("path") or "integrated_chain_pending"),
        reason_text=str((state.get("runtime_fast_path") or {}).get("reason") or ""),
    )
    return state, True
