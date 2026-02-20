from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.portfolio_budget_guard import apply_portfolio_budget_guard


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_market_price_map(state: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    src = state.get("market_prices")
    if not isinstance(src, dict):
        return out
    for k, v in src.items():
        key = str(k or "").strip().upper()
        if not key:
            continue
        out[key] = max(0.0, _as_float(v, 0.0))
    return out


def _should_apply(state: Dict[str, Any]) -> bool:
    if str(state.get("use_portfolio_budget_guard") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    if isinstance(state.get("strategy_budget_map"), dict):
        return True
    if isinstance(state.get("portfolio_allocation_result"), dict):
        return True
    if isinstance(state.get("allocation_result"), dict):
        return True
    return False


def portfolio_guard_node(state: Dict[str, Any]) -> Dict[str, Any]:
    intents = state.get("intents")
    intent_list = intents if isinstance(intents, list) else []
    if not intent_list:
        state["portfolio_guard"] = {
            "applied": False,
            "reason": "no_intents",
            "intent_total": 0,
            "approved_total": 0,
            "blocked_total": 0,
            "blocked_reason_counts": {},
        }
        return state

    if not _should_apply(state):
        state["portfolio_guard"] = {
            "applied": False,
            "reason": "disabled",
            "intent_total": len(intent_list),
            "approved_total": len(intent_list),
            "blocked_total": 0,
            "blocked_reason_counts": {},
        }
        return state

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    allocation_result = (
        state.get("portfolio_allocation_result")
        if isinstance(state.get("portfolio_allocation_result"), dict)
        else state.get("allocation_result")
    )
    strategy_budget_map = state.get("strategy_budget_map") if isinstance(state.get("strategy_budget_map"), dict) else {}
    symbol_caps = state.get("symbol_max_notional_map") if isinstance(state.get("symbol_max_notional_map"), dict) else {}
    if not symbol_caps and isinstance(policy.get("symbol_max_notional_map"), dict):
        symbol_caps = policy.get("symbol_max_notional_map")
    default_symbol_max_notional = _as_float(
        state.get("default_symbol_max_notional"),
        _as_float(policy.get("default_symbol_max_notional"), 0.0),
    )

    out = apply_portfolio_budget_guard(
        intent_list,
        allocation_result=allocation_result if isinstance(allocation_result, dict) else None,
        strategy_budget_map=strategy_budget_map if isinstance(strategy_budget_map, dict) else None,
        default_symbol_max_notional=default_symbol_max_notional,
        symbol_max_notional_map=symbol_caps if isinstance(symbol_caps, dict) else None,
        market_prices=_to_market_price_map(state),
    )

    approved_rows = out.get("approved") if isinstance(out.get("approved"), list) else []
    approved_intents: List[Dict[str, Any]] = []
    for row in approved_rows:
        if not isinstance(row, dict):
            continue
        intent = row.get("intent")
        if isinstance(intent, dict):
            approved_intents.append(intent)

    state["intents"] = approved_intents
    state["portfolio_guard"] = {
        "applied": True,
        "ok": bool(out.get("ok")),
        "intent_total": int(out.get("intent_total") or 0),
        "budget_screened_total": int(out.get("budget_screened_total") or 0),
        "approved_total": int(out.get("approved_total") or 0),
        "blocked_total": int(out.get("blocked_total") or 0),
        "blocked_reason_counts": out.get("blocked_reason_counts") if isinstance(out.get("blocked_reason_counts"), dict) else {},
        "strategy_budget": out.get("strategy_budget") if isinstance(out.get("strategy_budget"), dict) else {},
        "failures": out.get("failures") if isinstance(out.get("failures"), list) else [],
    }
    state["blocked_intents"] = out.get("blocked") if isinstance(out.get("blocked"), list) else []

    if len(intent_list) > 0 and len(approved_intents) == 0:
        state["selected"] = None
        state["portfolio_guard"]["selected_cleared"] = True
    else:
        state["portfolio_guard"]["selected_cleared"] = False
    return state
