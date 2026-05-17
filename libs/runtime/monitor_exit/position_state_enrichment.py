from __future__ import annotations

from typing import Any, Dict


def enrich_exit_policy_with_position_state(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    peak_price: float,
    features: Dict[str, Any],
    exit_policy_map: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(exit_policy_map or {})
    if position.get("peak_price") is not None:
        out.setdefault("peak_price", position.get("peak_price"))
    elif position.get("high_water_mark") is not None:
        out.setdefault("peak_price", position.get("high_water_mark"))
    elif peak_price > 0.0:
        out.setdefault("peak_price", peak_price)
    else:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
        if peak_map.get(symbol) is not None:
            out.setdefault("peak_price", peak_map.get(symbol))

    if features.get("engine_volatility20") is not None:
        out.setdefault("current_volatility", features.get("engine_volatility20"))
    if state.get("policy") and isinstance(state.get("policy"), dict):
        policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
        if policy.get("exit_policy_baseline_volatility") is not None:
            out.setdefault("baseline_volatility", policy.get("exit_policy_baseline_volatility"))

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    partial_taken_map = (
        persisted.get("partial_take_profit_taken_by_symbol")
        if isinstance(persisted.get("partial_take_profit_taken_by_symbol"), dict)
        else {}
    )
    if partial_taken_map.get(symbol) not in (None, ""):
        out.setdefault("partial_take_profit_taken", True)
    ladder_taken_map = (
        persisted.get("profit_ladder_taken_levels_by_symbol")
        if isinstance(persisted.get("profit_ladder_taken_levels_by_symbol"), dict)
        else {}
    )
    if isinstance(ladder_taken_map.get(symbol), list):
        out.setdefault("profit_ladder_taken_levels", list(ladder_taken_map.get(symbol) or []))
    rr_taken_map = (
        persisted.get("risk_reward_take_profit_taken_rungs_by_symbol")
        if isinstance(persisted.get("risk_reward_take_profit_taken_rungs_by_symbol"), dict)
        else {}
    )
    if isinstance(rr_taken_map.get(symbol), list):
        out.setdefault("risk_reward_take_profit_taken_rungs", list(rr_taken_map.get(symbol) or []))
    if state.get("emergency_halt") is not None:
        out.setdefault("emergency_halt", state.get("emergency_halt"))
    mctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    if mctx.get("minutes_to_close") is not None:
        out.setdefault("minutes_to_close", mctx.get("minutes_to_close"))
    return out

