from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict

from libs.ai.intent_schema import normalize_intent

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

    if strategist is not None and hasattr(strategist, "decide"):
        llm_t0 = 0.0
        do_llm_log = strategy_name == "OpenAIStrategist"
        if do_llm_log:
            llm_t0 = time.perf_counter()
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
        finally:
            if do_llm_log:
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
                if llm_meta.get("error_type"):
                    payload["error_type"] = str(llm_meta.get("error_type"))
                elif error:
                    payload["error_type"] = "Exception"
                _log_llm_call(state, payload)
    else:
        raw_intent = _rule_intent(symbol, price, cash, open_positions)

    intent, rationale = normalize_intent(raw_intent, default_symbol=str(symbol) if symbol else None, default_price=price)

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
