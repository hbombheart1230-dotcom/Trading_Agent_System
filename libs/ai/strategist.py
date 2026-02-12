from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class StrategyInput:
    symbol: str
    market_snapshot: Dict[str, Any]
    portfolio_snapshot: Dict[str, Any]
    risk_context: Dict[str, Any]


@dataclass
class StrategyDecision:
    """Pure decision (no execution)."""
    intent: Dict[str, Any]
    rationale: str = ""


@runtime_checkable
class Strategist(Protocol):
    def decide(self, x: StrategyInput) -> StrategyDecision:  # pragma: no cover
        ...


class RuleStrategist:
    """M12 placeholder: deterministic rules (no LLM)."""

    def decide(self, x: StrategyInput) -> StrategyDecision:
        price = x.market_snapshot.get("price")
        cash = x.portfolio_snapshot.get("cash", 0)

        if cash > 1_000_000 and price is not None:
            intent = {
                "action": "BUY",
                "symbol": x.symbol,
                "qty": 1,
                "price": price,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            }
            return StrategyDecision(intent=intent, rationale="rule:cash_and_price_ok")

        return StrategyDecision(intent={"action": "NOOP", "reason": "conditions_not_met"}, rationale="rule:no_trade")
