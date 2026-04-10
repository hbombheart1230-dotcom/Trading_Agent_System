from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, Any, Optional

from libs.runtime.market_hours import MarketHours, now_kst


def _resolve_tick_pipeline(state: Dict[str, Any]) -> str:
    """Resolve M13 tick pipeline mode.

    Priority:
      1) state["m13_tick_pipeline"]
      2) state["runtime_path"]
      3) integrated_chain (default)
    """
    raw = (
        state.get("m13_tick_pipeline")
        or state.get("runtime_path")
    )
    v = str(raw or "").strip().lower()
    if v in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    if v in ("legacy_m10", "legacy", "m10"):
        return "legacy_m10"
    return "integrated_chain"


def run_m13_tick(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    market_hours: Optional[MarketHours] = None,
    run_m10: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    run_integrated: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """M13-1: single tick wrapper around M10 pipeline.

    - If market is closed: sets state['tick_skipped']=True and returns.
    - If open: runs selected tick pipeline and sets state['tick_skipped']=False.

    Injection points:
      - dt: fixed time for tests
      - run_m10: legacy pipeline function
      - run_integrated: integrated chain runtime function
    """
    mh = market_hours or MarketHours()
    ts = dt or now_kst()
    state["tick_ts"] = int(ts.timestamp())
    state["tick_pipeline"] = _resolve_tick_pipeline(state)

    if not mh.is_open(ts):
        state["tick_skipped"] = True
        return state

    state["tick_skipped"] = False
    if state["tick_pipeline"] == "integrated_chain":
        if run_integrated is None:
            from graphs.commander_runtime import run_commander_runtime

            run_integrated = lambda s: run_commander_runtime(s, mode="integrated_chain")
        return run_integrated(state)

    if run_m10 is None:
        from graphs.pipelines.m10_live_pipeline import run_m10_live_pipeline as run_m10  # lazy import
    return run_m10(state)
