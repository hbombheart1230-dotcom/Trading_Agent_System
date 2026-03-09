from __future__ import annotations

import os

from libs.read.price_reader import PriceReader
from libs.read.price_reader import MockPriceReader
from libs.read.kiwoom_price_reader import KiwoomPriceReader


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _resolve_last_valid_price(state: dict) -> float:
    # Prefer most recent in-memory market snapshot price.
    mkt = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    px = _safe_float(mkt.get("price"), 0.0)
    if px > 0.0:
        return float(px)

    # Optional persisted hint from previous runtime.
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    px2 = _safe_float(persisted.get("last_market_price"), 0.0)
    if px2 > 0.0:
        return float(px2)
    return 0.0


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
    health = {
        "reader_ok": True,
        "reader_error": "",
        "fallback_applied": False,
        "fallback_source": "",
        "source": "reader",
    }

    try:
        snap = reader.get_market_snapshot(symbol)
    except Exception as e:
        health["reader_ok"] = False
        health["reader_error"] = str(e)
        if not mock_mode:
            raise
        last_valid = _resolve_last_valid_price(state)
        if last_valid > 0.0:
            health["fallback_applied"] = True
            health["fallback_source"] = "last_valid_market_price"
            health["source"] = "mock_fallback_after_reader_error"
            snap = MockPriceReader(prices={symbol: last_valid}, default_price=last_valid).get_market_snapshot(symbol)
        else:
            # In mock mode, keep runtime moving with deterministic fallback snapshot.
            health["fallback_applied"] = True
            health["fallback_source"] = "mock_price_fallback_env"
            health["source"] = "mock_fallback_after_reader_error"
            snap = MockPriceReader(prices={symbol: fallback_price}, default_price=fallback_price).get_market_snapshot(symbol)

    if mock_mode and float(getattr(snap, "price", 0.0) or 0.0) <= 0.0:
        last_valid = _resolve_last_valid_price(state)
        if last_valid > 0.0:
            health["fallback_applied"] = True
            health["fallback_source"] = "last_valid_market_price"
            health["source"] = "mock_fallback_after_non_positive_price"
            snap = MockPriceReader(prices={symbol: last_valid}, default_price=last_valid).get_market_snapshot(symbol)
        else:
            health["fallback_applied"] = True
            health["fallback_source"] = "mock_price_fallback_env"
            health["source"] = "mock_fallback_after_non_positive_price"
            snap = MockPriceReader(prices={symbol: fallback_price}, default_price=fallback_price).get_market_snapshot(symbol)

    market_snapshot = snap.to_dict()
    market_snapshot["_health"] = dict(health)
    state["market_snapshot"] = market_snapshot
    state["market_snapshot_health"] = dict(health)

    # Persist positive market price hint for next-run fallback reuse.
    if float(market_snapshot.get("price") or 0.0) > 0.0:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        persisted["last_market_price"] = float(market_snapshot.get("price") or 0.0)
        state["persisted_state"] = persisted
    return state
