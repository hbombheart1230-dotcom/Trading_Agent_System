from __future__ import annotations

import time


def build_risk_context(state: dict) -> dict:
    """M10-2 node: build risk_context automatically.

    Inputs:
      - state['snapshots']['portfolio']
      - state['persisted_state']

    Produces:
      - state['risk_context']
    """
    portfolio = state.get("snapshots", {}).get("portfolio", {})
    persisted = state.get("persisted_state", {})

    positions = portfolio.get("positions", [])
    open_positions = len([p for p in positions if p.get("qty", 0) > 0])

    # daily_pnl_ratio: best-effort (unrealized / cash)
    cash = float(portfolio.get("cash", 0.0)) or 1.0
    unrealized_sum = sum(float(p.get("unrealized_pnl", 0.0)) for p in positions)
    daily_pnl_ratio = unrealized_sum / cash

    risk = {
        "open_positions": open_positions,
        "daily_pnl_ratio": daily_pnl_ratio,
        "last_order_epoch": int(persisted.get("last_order_epoch", 0)),
        "now_epoch": int(time.time()),
    }

    state["risk_context"] = risk
    return state
