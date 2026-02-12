from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: int
    avg_price: float
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    positions: List[PositionSnapshot]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cash": float(self.cash),
            "positions": [p.to_dict() for p in self.positions],
        }


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    ts: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": float(self.price),
            "ts": int(self.ts),
        }
