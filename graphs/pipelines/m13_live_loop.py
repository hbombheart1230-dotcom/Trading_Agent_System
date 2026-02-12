from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional

# Type aliases for dependency injection (keeps this pipeline unit-testable).
NodeFn = Callable[[Dict[str, Any]], Dict[str, Any]]

def run_m13_once(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    load_state_fn: Optional[NodeFn] = None,
    save_state_fn: Optional[NodeFn] = None,
    tick_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    eod_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """M13-3: one-iteration live loop (test-first).

    Default wiring (when fns are not injected):
      - graphs.nodes.load_state.load_state
      - graphs.pipelines.m13_tick.run_m13_tick
      - graphs.pipelines.m13_eod_report.run_m13_eod_report
      - graphs.nodes.save_state.save_state

    The goal is to make a minimal, deterministic 'one loop' unit you can call from CLI.
    """
    if load_state_fn is None:
        from graphs.nodes.load_state import load_state as load_state_fn  # lazy import
    if save_state_fn is None:
        from graphs.nodes.save_state import save_state as save_state_fn  # lazy import
    if tick_fn is None:
        from graphs.pipelines.m13_tick import run_m13_tick as tick_fn  # lazy import
    if eod_fn is None:
        from graphs.pipelines.m13_eod_report import run_m13_eod_report as eod_fn  # lazy import

    # Load persisted state first (state_store_path is read from env by node)
    state = load_state_fn(state)
    # One tick (runs M10 only if market open)
    state = tick_fn(state, dt=dt)  # type: ignore[arg-type]
    # End-of-day report trigger (runs only after close, once per day)
    state = eod_fn(state, dt=dt)  # type: ignore[arg-type]
    # Persist state at end
    state = save_state_fn(state)
    return state
