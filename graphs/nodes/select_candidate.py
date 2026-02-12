from __future__ import annotations

from typing import Dict, List, Optional

def select_candidate(state: dict) -> dict:
    """M11-2 node: pick one symbol from candidates.

    Heuristic (safe/minimal):
      - If state['candidate_prices'] dict exists, choose the lowest priced symbol
        (cheap-first placeholder; replace later with real ranking).
      - Else choose first candidate.
      - If state['symbol'] already exists, keep it (backward compatible).

    Produces:
      - state['selected_symbol']
      - state['symbol'] (for downstream M9/M10 pipelines)
    """
    if isinstance(state.get("symbol"), str) and state["symbol"]:
        state["selected_symbol"] = state["symbol"]
        return state

    candidates: List[str] = state.get("candidates") or []
    if not candidates:
        return state

    prices: Optional[Dict[str, float]] = state.get("candidate_prices")
    chosen = candidates[0]
    if isinstance(prices, dict) and prices:
        # best-effort: pick min(price)
        best = None
        for sym in candidates:
            p = prices.get(sym)
            if p is None:
                continue
            try:
                pv = float(p)
            except Exception:
                continue
            if best is None or pv < best[1]:
                best = (sym, pv)
        if best is not None:
            chosen = best[0]

    state["selected_symbol"] = chosen
    state["symbol"] = chosen
    return state
