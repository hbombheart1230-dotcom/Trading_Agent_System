from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Any, Optional

from libs.runtime.market_hours import MarketHours, now_kst

def run_m13_tick(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    market_hours: Optional[MarketHours] = None,
    run_m10: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """M13-1: single tick wrapper around M10 pipeline.

    - If market is closed: sets state['tick_skipped']=True and returns.
    - If open: runs M10 pipeline once and sets state['tick_skipped']=False.

    Injection points:
      - dt: fixed time for tests
      - run_m10: pipeline function (defaults to graphs.pipelines.m10_live_pipeline.run_m10_live_pipeline)
    """
    mh = market_hours or MarketHours()
    ts = dt or now_kst()
    state["tick_ts"] = int(ts.timestamp())

    if not mh.is_open(ts):
        state["tick_skipped"] = True
        return state

    if run_m10 is None:
        from graphs.pipelines.m10_live_pipeline import run_m10_live_pipeline as run_m10  # lazy import

    state["tick_skipped"] = False
    return run_m10(state)
