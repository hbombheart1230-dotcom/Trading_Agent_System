from __future__ import annotations

import os

from libs.read.portfolio_reader import PortfolioReader
from libs.read.portfolio_reader import MockPortfolioReader
from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader


def build_portfolio_snapshot(state: dict) -> dict:
    """M9 node: build portfolio_snapshot.
    Default: KiwoomPortfolioReader (real HTTP; host depends on KIWOOM_MODE).
    """
    if state.get("portfolio_reader") is not None:
        reader: PortfolioReader = state["portfolio_reader"]
    else:
        reader = KiwoomPortfolioReader.from_env()

    mock_mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"
    fallback_cash = float(os.getenv("MOCK_CASH_FALLBACK", "2000000") or 2000000)

    try:
        snap = reader.get_portfolio_snapshot()
    except Exception:
        if not mock_mode:
            raise
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    if mock_mode and float(getattr(snap, "cash", 0.0) or 0.0) <= 0.0:
        snap = MockPortfolioReader(cash=fallback_cash, positions=[]).get_portfolio_snapshot()

    state["portfolio_snapshot"] = snap.to_dict()
    return state
