from __future__ import annotations

from libs.read.price_reader import PriceReader
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

    snap = reader.get_market_snapshot(symbol)
    state["market_snapshot"] = snap.to_dict()
    return state
