from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from libs.agent.executor.executor_agent import ExecutorAgent


class AgentExecutor:
    """Agent-layer executor (M15).

    Wraps the existing ExecutorAgent (two-phase + execution skill runner).
    """

    def __init__(self, *, executor_agent: ExecutorAgent):
        self._agent = executor_agent

    def submit(
        self,
        *,
        intent: Dict[str, Any],
        approval_mode: str = "manual",
        execution_enabled: bool = False,
    ) -> Dict[str, Any]:
        # Support standard order intent shape:
        # {side, symbol, qty, order_type, price, rationale}
        if "side" in intent and "symbol" in intent and "qty" in intent:
            return self._agent.submit_order_intent(
                side=str(intent.get("side")),
                symbol=str(intent.get("symbol")),
                qty=int(intent.get("qty")),
                order_type=str(intent.get("order_type") or "market"),
                price=int(intent["price"]) if intent.get("price") is not None else None,
                rationale=str(intent.get("rationale") or ""),
                approval_mode=approval_mode,
                execution_enabled=execution_enabled,
            )

        # Or accept already-normalized {action, symbol, qty, ...}
        action = str(intent.get("action") or "").upper()
        if action in ("BUY", "SELL") and "symbol" in intent and "qty" in intent:
            # Map to submit_order_intent API
            side = "buy" if action == "BUY" else "sell"
            return self._agent.submit_order_intent(
                side=side,
                symbol=str(intent.get("symbol")),
                qty=int(intent.get("qty")),
                order_type=str(intent.get("order_type") or "market"),
                price=int(intent["price"]) if intent.get("price") is not None else None,
                rationale=str(intent.get("rationale") or ""),
                approval_mode=approval_mode,
                execution_enabled=execution_enabled,
            )

        # Fallback: store/submit via supervisor directly if needed in future.
        return {"decision": {"status": "rejected", "reason": "Unsupported intent shape", "intent": intent}}
