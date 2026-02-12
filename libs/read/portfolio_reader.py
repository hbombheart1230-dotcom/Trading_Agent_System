from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from libs.read.snapshot_models import PortfolioSnapshot, PositionSnapshot


class PortfolioReader(Protocol):
    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        ...


class MockPortfolioReader:
    """Mock portfolio reader."""

    def __init__(self, cash: float = 0.0, positions: Optional[List[Dict]] = None):
        self.cash = float(cash)
        self._positions = positions or []

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        pos = []
        for p in self._positions:
            pos.append(
                PositionSnapshot(
                    symbol=str(p.get("symbol", "")),
                    qty=int(p.get("qty", 0)),
                    avg_price=float(p.get("avg_price", 0.0)),
                    unrealized_pnl=float(p.get("unrealized_pnl", 0.0)),
                )
            )
        return PortfolioSnapshot(cash=self.cash, positions=pos)
