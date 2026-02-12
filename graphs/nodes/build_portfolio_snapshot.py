from __future__ import annotations

from libs.read.portfolio_reader import PortfolioReader
from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader


def build_portfolio_snapshot(state: dict) -> dict:
    """M9 node: build portfolio_snapshot.
    Default: KiwoomPortfolioReader (real HTTP; host depends on KIWOOM_MODE).
    """
    if state.get("portfolio_reader") is not None:
        reader: PortfolioReader = state["portfolio_reader"]
    else:
        reader = KiwoomPortfolioReader.from_env()

    snap = reader.get_portfolio_snapshot()
    state["portfolio_snapshot"] = snap.to_dict()
    return state
