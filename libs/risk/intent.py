from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal


IntentType = Literal["buy", "sell", "open", "close", "hold"]


@dataclass(frozen=True)
class TradeIntent:
    """What we want to do (decision output).
    This is produced by Strategist/AI (or a rule-based stub for now).
    """
    intent: IntentType
    order_api_id: str  # explicit API id to use for execution
    symbol: Optional[str] = None  # e.g., stock code
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "order_api_id": self.order_api_id,
            "symbol": self.symbol,
            "rationale": self.rationale,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TradeIntent":
        return TradeIntent(
            intent=str(d.get("intent", "hold")).lower(),  # type: ignore
            order_api_id=str(d.get("order_api_id", "")),
            symbol=(str(d["symbol"]) if d.get("symbol") is not None else None),
            rationale=str(d.get("rationale", "")),
        )


@dataclass(frozen=True)
class RiskContext:
    """What Supervisor needs to evaluate risk.
    Produced by Scanner/Portfolio state.
    """
    daily_pnl_ratio: float = 0.0
    per_trade_risk_ratio: float = 0.0
    open_positions: int = 0
    last_order_epoch: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "daily_pnl_ratio": float(self.daily_pnl_ratio),
            "per_trade_risk_ratio": float(self.per_trade_risk_ratio),
            "open_positions": int(self.open_positions),
            "last_order_epoch": int(self.last_order_epoch),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RiskContext":
        return RiskContext(
            daily_pnl_ratio=float(d.get("daily_pnl_ratio", 0.0)),
            per_trade_risk_ratio=float(d.get("per_trade_risk_ratio", 0.0)),
            open_positions=int(d.get("open_positions", 0)),
            last_order_epoch=int(d.get("last_order_epoch", 0)),
        )


@dataclass(frozen=True)
class ExecutionContext:
    """Inputs for ApiRequestBuilder.prepare(spec, context).
    This is the parameter context used to fill request params.
    """
    values: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.values or {})


@dataclass(frozen=True)
class TradeDecisionPacket:
    """Single packet that can be executed deterministically.
    - intent decides action
    - risk_context for Supervisor
    - exec_context for request builder
    """
    intent: TradeIntent
    risk: RiskContext
    exec_context: ExecutionContext

    def to_state(self, catalog_path: str) -> Dict[str, Any]:
        """Convert into state dict expected by execute_order node."""
        return {
            "catalog_path": catalog_path,
            "order_api_id": self.intent.order_api_id,
            "intent": self.intent.intent,
            "context": self.exec_context.to_dict(),
            "risk_context": self.risk.to_dict(),
        }
