from __future__ import annotations

from libs.core.event_logger_compat import get_event_logger
from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket


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

    state["decision_packet"] = {
        "intent": ti.to_dict(),
        "risk": risk.to_dict(),
        "exec_context": exec_ctx.to_dict(),
    }
    try:
        logger.end({"intent": ti.intent})
    except Exception:
        pass
    return state
