from __future__ import annotations

from typing import Any, Dict

from libs.runtime.commander.policy_readers import coerce_int
from libs.runtime.commander.strategist_cache_decision import runtime_now_epoch
from libs.runtime.commander.strategist_fingerprint import (
    build_strategist_input_fingerprint,
    portfolio_open_position_symbols,
)


def normalize_strategist_output_contract(output: Dict[str, Any]) -> Dict[str, Any]:
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


def persist_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    if not strategist_output:
        return state
    if bool(state.get("strategist_blocked")) or bool(strategist_output.get("llm_frame_blocked")):
        return state
    strategist_output = normalize_strategist_output_contract(strategist_output)
    state["strategist_output"] = dict(strategist_output)
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    input_fingerprint = build_strategist_input_fingerprint(state)
    persisted_state["strategist_output_cache"] = {
        "output": dict(strategist_output),
        "generated_epoch": int(runtime_now_epoch(state)),
        "source": "strategist_node",
        "input_fingerprint": dict(input_fingerprint),
    }
    state["persisted_state"] = persisted_state
    return state


def hydrate_strategist_output_cache(state: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(state.get("strategist_output"), dict) and state.get("strategist_output"):
        return state
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = (
        persisted_state.get("strategist_output_cache")
        if isinstance(persisted_state.get("strategist_output_cache"), dict)
        else {}
    )
    cached = raw_cached.get("output") if isinstance(raw_cached.get("output"), dict) else raw_cached
    if isinstance(cached, dict) and cached:
        state["strategist_output"] = normalize_strategist_output_contract(cached)
        if isinstance(raw_cached, dict) and raw_cached:
            state["strategist_output_cache_meta"] = dict(raw_cached)
        return state

    position_context = (
        persisted_state.get("position_strategy_context")
        if isinstance(persisted_state.get("position_strategy_context"), dict)
        else {}
    )
    for symbol in portfolio_open_position_symbols(state):
        row = position_context.get(symbol) if isinstance(position_context.get(symbol), dict) else {}
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        if output:
            state["strategist_output"] = normalize_strategist_output_contract(output)
            state["strategist_output_cache_meta"] = {
                "output": dict(state["strategist_output"]),
                "generated_epoch": coerce_int(row.get("generated_epoch"), 0),
                "source": str(row.get("source") or "position_strategy_context"),
                "symbol": symbol,
            }
    return state
