from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import uuid
import time

from libs.ai.intent_schema import normalize_intent
from libs.risk.supervisor import Supervisor
from libs.core.settings import Settings


@dataclass(frozen=True)
class OrderIntent:
    intent_id: str
    action: str           # BUY/SELL/NOOP (normalized)
    symbol: Optional[str]
    qty: int
    price: Optional[float]
    order_type: str       # limit/market
    rationale: str
    created_epoch: int


@dataclass(frozen=True)
class Decision:
    status: str  # "approved" | "rejected" | "needs_approval"
    reason: str
    details: Dict[str, Any]
    intent: OrderIntent


class TwoPhaseSupervisor:
    """2-Phase gate for orders.

    Phase 1: create intent (LLM can call) -> returns approved/rejected/needs_approval
    Phase 2: execute only if approved (human or policy)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or Settings.from_env()
        self.risk = Supervisor(self.s)

    def create_intent(self, raw_intent: Dict[str, Any]) -> Decision:
        norm, rationale = normalize_intent(raw_intent)
        now = int(time.time())
        intent = OrderIntent(
            intent_id=uuid.uuid4().hex,
            action=str(norm.get("action") or "NOOP"),
            symbol=norm.get("symbol"),
            qty=int(norm.get("qty") or 0),
            price=norm.get("price"),
            order_type=str(norm.get("order_type") or "limit"),
            rationale=rationale,
            created_epoch=now,
        )

        # risk gate (deterministic)
        allow = self.risk.allow(intent.action.lower(), {"now_epoch": now})
        if not allow.allow:
            return Decision(status="rejected", reason=allow.reason, details=allow.details, intent=intent)

        import os

        auto = (str(getattr(self.s, "auto_approve_orders", os.getenv("AUTO_APPROVE_ORDERS", "false"))).lower() == "true")
        if auto:
            return Decision(status="approved", reason="AUTO_APPROVE_ORDERS=true", details={}, intent=intent)
        return Decision(status="needs_approval", reason="Supervisor approval required", details={}, intent=intent)
