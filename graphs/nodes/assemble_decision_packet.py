from __future__ import annotations

from libs.core.event_logger_compat import get_event_logger
from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket


def _build_default_why(state: dict) -> dict:
    trace = state.get("decision_trace") if isinstance(state.get("decision_trace"), dict) else {}
    llm_ctx = trace.get("llm_context") if isinstance(trace.get("llm_context"), dict) else {}
    technical = llm_ctx.get("technical") if isinstance(llm_ctx.get("technical"), dict) else {}
    news = llm_ctx.get("news") if isinstance(llm_ctx.get("news"), dict) else {}
    policy = llm_ctx.get("decision_policy") if isinstance(llm_ctx.get("decision_policy"), dict) else {}

    return {
        "regime": str(technical.get("regime") or "unknown"),
        "technical": dict(technical),
        "news": dict(news),
        "policy": dict(policy),
    }


def _build_default_invalidation(state: dict) -> dict:
    raw = state.get("invalidation")
    if isinstance(raw, dict):
        return {
            "triggered": bool(raw.get("triggered", False)),
            "reason": str(raw.get("reason") or ""),
            "conditions": list(raw.get("conditions") or []),
        }
    return {
        "triggered": False,
        "reason": "",
        "conditions": [],
    }


def assemble_decision_packet(state: dict) -> dict:
    """M8-2 node: assemble a deterministic decision packet."""
    logger = get_event_logger("assemble_decision_packet")
    try:
        logger.start({"order_api_id": state.get("order_api_id")})
    except Exception:
        pass

    intent_val = state.get("intent", "hold")
    if isinstance(intent_val, dict):
        intent_val = intent_val.get("intent", "hold")

    ti = TradeIntent(
        intent=str(intent_val).lower(),
        order_api_id=str(state.get("order_api_id", "")),
        symbol=state.get("symbol"),
        rationale=str(state.get("rationale", "")),
    )
    risk = RiskContext.from_dict(state.get("risk_context", {}) or {})
    exec_ctx = ExecutionContext(values=state.get("exec_context", {}) or {})

    _ = TradeDecisionPacket(intent=ti, risk=risk, exec_context=exec_ctx)

    why = _build_default_why(state)
    if isinstance(state.get("why"), dict):
        why.update({k: v for k, v in dict(state.get("why") or {}).items() if k in ("regime", "technical", "news", "policy")})

    state["decision_packet"] = {
        "intent": ti.to_dict(),
        "risk": risk.to_dict(),
        "exec_context": exec_ctx.to_dict(),
        "why": why,
        "invalidation": _build_default_invalidation(state),
    }
    try:
        logger.end({"intent": ti.intent, "regime": str(why.get("regime") or "unknown")})
    except Exception:
        pass
    return state
