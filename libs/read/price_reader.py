from __future__ import annotations

import time
from typing import Dict, Optional, Protocol

from libs.read.snapshot_models import MarketSnapshot


class PriceReader(Protocol):
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        ...


class MockPriceReader:
    """Mock current-price reader."""

    def __init__(self, prices: Optional[Dict[str, float]] = None, default_price: float = 100.0):
        self.prices = prices or {}
        self.default_price = float(default_price)

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        price = float(self.prices.get(symbol, self.default_price))
        return MarketSnapshot(symbol=symbol, price=price, ts=int(time.time()))
