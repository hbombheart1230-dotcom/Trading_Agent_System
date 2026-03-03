from __future__ import annotations

import os

from libs.read.price_reader import PriceReader
from libs.read.price_reader import MockPriceReader
from libs.read.kiwoom_price_reader import KiwoomPriceReader


def build_market_snapshot(state: dict) -> dict:
    """M9 node: build market_snapshot (current price).
    Default: KiwoomPriceReader (real HTTP; host depends on KIWOOM_MODE).
    """
    symbol = str(state.get("symbol", "")).strip()
    if not symbol:
        raise ValueError("state['symbol'] is required")

    if state.get("price_reader") is not None:
        reader: PriceReader = state["price_reader"]
    else:
        # real reader (mock host when KIWOOM_MODE=mock)
        reader = KiwoomPriceReader.from_env()

    mock_mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"
    fallback_price = float(os.getenv("MOCK_PRICE_FALLBACK", "70000") or 70000)

    try:
        snap = reader.get_market_snapshot(symbol)
    except Exception:
        if not mock_mode:
            raise
        # In mock mode, keep runtime moving with deterministic fallback snapshot.
        snap = MockPriceReader(prices={symbol: fallback_price}, default_price=fallback_price).get_market_snapshot(symbol)

    if mock_mode and float(getattr(snap, "price", 0.0) or 0.0) <= 0.0:
        snap = MockPriceReader(prices={symbol: fallback_price}, default_price=fallback_price).get_market_snapshot(symbol)

    state["market_snapshot"] = snap.to_dict()
    return state
