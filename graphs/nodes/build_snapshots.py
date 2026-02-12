from __future__ import annotations

from graphs.nodes.build_market_snapshot import build_market_snapshot
from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot


def build_snapshots(state: dict) -> dict:
    """M9-4 node: build both market_snapshot and portfolio_snapshot.

    Expects (typical):
      - state['symbol']
      - optional: state['price_reader'] / state['portfolio_reader']

    Produces:
      - state['market_snapshot']
      - state['portfolio_snapshot']
      - state['snapshots'] = {'market': ..., 'portfolio': ...}
    """
    state = build_market_snapshot(state)
    state = build_portfolio_snapshot(state)

    state["snapshots"] = {
        "market": state.get("market_snapshot"),
        "portfolio": state.get("portfolio_snapshot"),
    }
    return state
