from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict

from libs.ai.intent_schema import normalize_intent
from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.circuit_breaker import (
    gate_runtime_circuit,
    mark_runtime_circuit_failure,
    mark_runtime_circuit_success,
)

def _rule_intent(symbol: Any, price: Any, cash: Any, open_positions: Any) -> Dict[str, Any]:
    if cash and cash > 1_000_000 and price is not None and int(open_positions or 0) == 0 and symbol:
        return {
            "action": "BUY",
            "symbol": symbol,
            "qty": 1,
            "price": price,
            "order_type": "limit",
            "order_api_id": "ORDER_SUBMIT",
            "rationale": "rule:cash_and_price_ok",
        }
    return {"action": "NOOP", "reason": "conditions_not_met", "rationale": "rule:no_trade"}


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _extract_position_for_symbol(portfolio: Dict[str, Any], symbol: Any) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}
    rows = portfolio.get("positions")
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").strip().upper() == sym:
            return dict(row)
    return {}


def _resolve_exit_policy_enabled(state: Dict[str, Any]) -> bool:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    if _is_trueish(state.get("use_exit_policy")):
        return True
    if _is_trueish(policy.get("use_exit_policy")):
        return True
    return _is_trueish(os.getenv("USE_EXIT_POLICY", "false"))


def _resolve_exit_policy_config(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})

    sl_raw = str(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "") or "").strip()
    tp_raw = str(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "") or "").strip()

    if sl_raw:
        out["stop_loss_pct"] = _to_float(sl_raw, _to_float(out.get("stop_loss_pct"), 0.03))
    if tp_raw:
        out["take_profit_pct"] = _to_float(tp_raw, _to_float(out.get("take_profit_pct"), 0.05))
    return out


def _import_event_logger():
    for mod in ("libs.event_logger", "libs.logging.event_logger", "libs.core.event_logger"):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _ensure_run_id(state: dict) -> str:
    _EventLogger, new_run_id = _import_event_logger()
    rid = str(state.get("run_id") or new_run_id())
    state["run_id"] = rid
    return rid


def _make_logger():
    EventLogger, _new_run_id = _import_event_logger()
    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_decision(state: dict, packet: dict, trace: dict) -> None:
    try:
        logger = _make_logger()
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="decision", event="trace", payload={"decision_packet": packet, "trace": trace})
    except Exception:
        return


def _log_llm_call(state: dict, payload: Dict[str, Any]) -> None:
    try:
        logger = _make_logger()
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="strategist_llm", event="result", payload=payload)
    except Exception:
        return


def _sync_legacy_circuit_fields(state: dict, llm_meta: Dict[str, Any]) -> None:
    """Keep legacy top-level circuit fields in sync for compatibility."""
    if llm_meta.get("circuit_state") is not None:
        state["circuit_state"] = str(llm_meta.get("circuit_state") or "")
    if llm_meta.get("circuit_fail_count") is not None:
        try:
            state["circuit_fail_count"] = int(float(llm_meta.get("circuit_fail_count") or 0))
        except Exception:
            pass
    if llm_meta.get("circuit_open_until_epoch") is not None:
        try:
            state["circuit_open_until_epoch"] = int(float(llm_meta.get("circuit_open_until_epoch") or 0))
        except Exception:
            pass


def decide_trade(state: dict) -> dict:
    market: Dict[str, Any] = state.get("market_snapshot", {}) or {}
    portfolio: Dict[str, Any] = state.get("portfolio_snapshot", {}) or {}

    symbol = state.get("symbol") or state.get("selected_symbol") or market.get("symbol")

    risk = state.get("risk_context") or {
        "daily_pnl_ratio": portfolio.get("daily_pnl_ratio", 0.0),
        "open_positions": portfolio.get("open_positions", 0),
        "last_order_epoch": portfolio.get("last_order_epoch", 0),
        "per_trade_risk_ratio": 0.0,
    }

    exec_context = state.get("exec_context") or {"mode": "mock"}

    strategist = state.get("strategist")
    if strategist is None:
        from libs.ai.strategist_factory import get_strategist_from_env
        strategist = get_strategist_from_env()
        state["strategist"] = strategist

    price = market.get("price")
    cash = portfolio.get("cash", 0)
    open_positions = risk.get("open_positions", portfolio.get("open_positions", 0))

    features = {
        "symbol": symbol,
        "price": price,
        "cash": cash,
        "open_positions": open_positions,
        "daily_pnl_ratio": risk.get("daily_pnl_ratio", 0.0),
    }
    signals = {
        "cash_gt_1m": bool(cash and cash > 1_000_000),
        "has_price": price is not None,
        "no_open_positions": bool(int(open_positions or 0) == 0),
    }

    strategy_name = strategist.__class__.__name__ if strategist is not None else "builtin_rule"
    raw_intent: Dict[str, Any]
    error: str | None = None
    llm_meta: Dict[str, Any] = {}
    static_intent: Dict[str, Any] | None = None

    # Optional M29+ exit policy path for live loop:
    # when a position is already open and exit policy is enabled,
    # prefer deterministic hold/exit over repeated BUY intents.
    use_exit_policy = _resolve_exit_policy_enabled(state)
    position = _extract_position_for_symbol(portfolio, symbol)
    if int(open_positions or 0) > 0 and use_exit_policy and isinstance(position, dict):
        qty_pos = int(position.get("qty") or 0)
        avg_price = _to_float(position.get("avg_price"), 0.0)
        px = _to_float(price, 0.0) if price is not None else 0.0
        if qty_pos > 0 and avg_price > 0.0 and px > 0.0:
            exit_decision = evaluate_exit_policy(
                price=px,
                avg_price=avg_price,
                qty=qty_pos,
                policy=_resolve_exit_policy_config(state),
            )
            reason = str(exit_decision.get("reason") or "hold")
            if bool(exit_decision.get("triggered")):
                static_intent = {
                    "action": "SELL",
                    "symbol": symbol,
                    "qty": qty_pos,
                    "price": price,
                    "order_type": "market",
                    "order_api_id": "ORDER_SUBMIT",
                    "rationale": f"exit_policy:{reason}",
                }
            else:
                static_intent = {
                    "action": "NOOP",
                    "reason": "position_hold",
                    "rationale": f"exit_policy:{reason}",
                }
            strategy_name = "ExitPolicyStrategist"

    if static_intent is not None:
        raw_intent = dict(static_intent)
    elif strategist is not None and hasattr(strategist, "decide"):
        llm_t0 = 0.0
        do_llm_log = strategy_name == "OpenAIStrategist"
        runtime_gate: Dict[str, Any] = {}
        runtime_gate_blocked = False
        runtime_circuit_update: Dict[str, Any] = {}
        if do_llm_log:
            llm_t0 = time.perf_counter()
            try:
                runtime_gate = gate_runtime_circuit(state, scope="strategist")
            except Exception:
                runtime_gate = {}

            if runtime_gate and not bool(runtime_gate.get("allowed", True)):
                runtime_gate_blocked = True
                raw_intent = {"action": "NOOP", "reason": "circuit_open", "rationale": "runtime_circuit_open"}
                llm_meta = {
                    "error": "circuit_open",
                    "error_type": "CircuitOpen",
                    "attempts": 0,
                    "circuit_state": str(runtime_gate.get("circuit_state") or "open"),
                    "circuit_fail_count": int(runtime_gate.get("fail_count") or 0),
                    "circuit_open_until_epoch": int(runtime_gate.get("open_until_epoch") or 0),
                }
        if not runtime_gate_blocked:
            try:
                # Accept both provider StrategyInput and libs.ai.strategist StrategyInput
                try:
                    from libs.ai.strategist import StrategyInput  # type: ignore
                    x = StrategyInput(symbol=str(symbol), market_snapshot=market, portfolio_snapshot=portfolio, risk_context=risk)
                except Exception:
                    from libs.ai.providers.openai_provider import StrategyInput  # type: ignore
                    x = StrategyInput(symbol=str(symbol), market_snapshot=market, portfolio_snapshot=portfolio, risk_context=risk)

                decision = strategist.decide(x)  # type: ignore[call-arg]
                raw_intent = dict(getattr(decision, "intent", {}) or {})
                m = getattr(decision, "meta", None)
                if isinstance(m, dict):
                    llm_meta = dict(m)
                if getattr(decision, "rationale", None) and "rationale" not in raw_intent:
                    raw_intent["rationale"] = getattr(decision, "rationale")
            except Exception as e:
                error = str(e)
                # If this is OpenAIStrategist, keep it and return NOOP (do not swap strategy)
                if strategy_name == "OpenAIStrategist":
                    raw_intent = {"action": "NOOP", "reason": "strategist_error", "rationale": error}
                else:
                    from libs.ai.strategist import RuleStrategist
                    strategist = RuleStrategist()
                    state["strategist"] = strategist
                    strategy_name = "RuleStrategist"
                    raw_intent = _rule_intent(symbol, price, cash, open_positions)

        if do_llm_log:
            # M23-3: runtime circuit integration for strategist path.
            if not runtime_gate_blocked:
                intent_reason_for_cb = str(raw_intent.get("reason") or "").strip().lower()
                meta_error_for_cb = str(llm_meta.get("error") or "").strip()
                llm_failed_for_cb = (
                    bool(error)
                    or bool(meta_error_for_cb)
                    or intent_reason_for_cb in ("strategist_error", "circuit_open", "missing_config")
                )
                try:
                    if llm_failed_for_cb:
                        runtime_circuit_update = mark_runtime_circuit_failure(
                            state,
                            scope="strategist",
                            error_type=str(llm_meta.get("error_type") or "StrategistError"),
                        )
                    else:
                        runtime_circuit_update = mark_runtime_circuit_success(state, scope="strategist")
                except Exception:
                    runtime_circuit_update = {}

                if runtime_circuit_update:
                    llm_meta["circuit_state"] = str(runtime_circuit_update.get("circuit_state") or "")
                    llm_meta["circuit_fail_count"] = int(runtime_circuit_update.get("fail_count") or 0)
                    llm_meta["circuit_open_until_epoch"] = int(runtime_circuit_update.get("open_until_epoch") or 0)

            _sync_legacy_circuit_fields(state, llm_meta)

            latency_ms = int((time.perf_counter() - llm_t0) * 1000)
            intent_reason = str(raw_intent.get("reason") or "")
            meta_error = str(llm_meta.get("error") or "")
            llm_ok = not bool(error) and not bool(meta_error) and intent_reason != "strategist_error"
            payload: Dict[str, Any] = {
                "strategy": strategy_name,
                "provider": str(os.getenv("AI_STRATEGIST_PROVIDER", "rule") or "rule"),
                "model": str(getattr(strategist, "model", "") or ""),
                "latency_ms": latency_ms,
                "ok": bool(llm_ok),
                "intent_action": str(raw_intent.get("action") or ""),
                "intent_reason": intent_reason,
            }
            if getattr(strategist, "endpoint", None):
                payload["endpoint"] = str(getattr(strategist, "endpoint"))
            if llm_meta.get("attempts") is not None:
                payload["attempts"] = int(llm_meta.get("attempts") or 0)
            if llm_meta.get("endpoint_type"):
                payload["endpoint_type"] = str(llm_meta.get("endpoint_type"))
            for tok_key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if llm_meta.get(tok_key) is not None:
                    try:
                        payload[tok_key] = int(float(llm_meta.get(tok_key) or 0))
                    except Exception:
                        pass
            if llm_meta.get("estimated_cost_usd") is not None:
                try:
                    payload["estimated_cost_usd"] = float(llm_meta.get("estimated_cost_usd"))
                except Exception:
                    pass
            if llm_meta.get("circuit_state") is not None:
                payload["circuit_state"] = str(llm_meta.get("circuit_state") or "")
            if llm_meta.get("circuit_fail_count") is not None:
                try:
                    payload["circuit_fail_count"] = int(float(llm_meta.get("circuit_fail_count") or 0))
                except Exception:
                    pass
            if llm_meta.get("circuit_open_until_epoch") is not None:
                try:
                    payload["circuit_open_until_epoch"] = int(float(llm_meta.get("circuit_open_until_epoch") or 0))
                except Exception:
                    pass
            prompt_version = str(
                llm_meta.get("prompt_version") or getattr(strategist, "prompt_version", "") or ""
            )
            if prompt_version:
                payload["prompt_version"] = prompt_version
            schema_version = str(
                llm_meta.get("schema_version") or getattr(strategist, "schema_version", "") or ""
            )
            if schema_version:
                payload["schema_version"] = schema_version
            if llm_meta.get("error_type"):
                payload["error_type"] = str(llm_meta.get("error_type"))
            elif error:
                payload["error_type"] = "Exception"
            _log_llm_call(state, payload)
    else:
        raw_intent = _rule_intent(symbol, price, cash, open_positions)

    intent, rationale = normalize_intent(raw_intent, default_symbol=str(symbol) if symbol else None, default_price=price)

    # Safety: if a position is already open, block additional BUY intents.
    try:
        action = str(intent.get("action") or "").strip().upper()
        if action == "BUY" and int(open_positions or 0) > 0:
            intent["action"] = "NOOP"
            intent["qty"] = 0
            intent["reason"] = "position_already_open"
            rationale = "position_already_open"
    except Exception:
        pass

    packet = {"intent": intent, "risk": risk, "exec_context": exec_context}
    trace = {
        "features": features,
        "signals": signals,
        "rationale": rationale,
        "strategy": strategy_name,
        "raw_intent": raw_intent,
    }
    if error:
        trace["error"] = error

    state["decision_packet"] = packet
    state["decision_trace"] = trace
    _log_decision(state, packet, trace)
    return state
