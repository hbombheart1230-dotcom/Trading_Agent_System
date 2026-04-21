from __future__ import annotations

import time

from graphs.nodes.risk_cash_truth import resolve_risk_cash_truth


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
    portfolio_cash = float(portfolio.get("cash", 0.0) or 0.0)
    cash_truth = resolve_risk_cash_truth(state, portfolio_cash=portfolio_cash)

    # daily_pnl_ratio: prefer broker deposit truth before falling back to portfolio cash.
    cash = float(cash_truth.get("broker_deposit") or portfolio_cash) or 1.0
    unrealized_sum = sum(float(p.get("unrealized_pnl", 0.0)) for p in positions)
    daily_pnl_ratio = unrealized_sum / cash

    risk = {
        "open_positions": open_positions,
        "daily_pnl_ratio": daily_pnl_ratio,
        "daily_pnl_ratio_denominator": float(cash),
        "daily_pnl_ratio_denominator_source": (
            "broker_deposit" if float(cash_truth.get("broker_deposit") or 0.0) > 0.0 else "portfolio.cash"
        ),
        "last_order_epoch": int(persisted.get("last_order_epoch", 0)),
        "now_epoch": int(time.time()),
    }
    risk.update(cash_truth)

    state["risk_context"] = risk
    return state
