from __future__ import annotations

import os
from typing import List

def _default_universe() -> List[str]:
    raw = os.getenv("UNIVERSE_SYMBOLS", "").strip()
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    # Minimal starter universe (KRX 대표주)
    return ["005930", "000660"]

def scan_candidates(state: dict) -> dict:
    """M11-2 node: produce candidate symbols.

    Priority:
      1) state['universe'] (list[str])
      2) env UNIVERSE_SYMBOLS="005930,000660,..."
      3) fallback ["005930","000660"]

    Produces:
      - state['candidates']: list[str]
    """
    universe = state.get("universe")
    if isinstance(universe, list) and all(isinstance(x, str) for x in universe) and universe:
        state["candidates"] = universe
        return state

    state["candidates"] = _default_universe()
    return state
