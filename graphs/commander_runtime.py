from __future__ import annotations

"""M21-1: Canonical commander runtime entry.

This module provides one stable entry for orchestration while preserving
existing runtime behavior.

Modes:
  - graph_spine: run M17 graph spine (`run_trading_graph`)
  - decision_packet: run strategist decision + execution packet path
    (`decide_trade` -> `execute_from_packet`)

Default mode is graph_spine for backward compatibility.
"""

import os
from typing import Any, Callable, Dict, Literal, Optional

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet


RuntimeMode = Literal["graph_spine", "decision_packet"]


def _normalize_mode(value: Any) -> RuntimeMode:
    v = str(value or "").strip().lower()
    if v == "decision_packet":
        return "decision_packet"
    return "graph_spine"


def resolve_runtime_mode(state: Dict[str, Any], *, mode: Optional[RuntimeMode] = None) -> RuntimeMode:
    """Resolve runtime mode with explicit precedence.

    Priority:
      1) explicit argument `mode`
      2) `state["runtime_mode"]`
      3) env `COMMANDER_RUNTIME_MODE`
      4) default `graph_spine`
    """
    if mode is not None:
        return _normalize_mode(mode)
    if "runtime_mode" in state:
        return _normalize_mode(state.get("runtime_mode"))
    env_mode = os.getenv("COMMANDER_RUNTIME_MODE", "")
    return _normalize_mode(env_mode or "graph_spine")


def run_commander_runtime(
    state: Dict[str, Any],
    *,
    mode: Optional[RuntimeMode] = None,
    graph_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    execute: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one canonical commander runtime step.

    Mode selection uses `resolve_runtime_mode(...)`.
    """
    selected = resolve_runtime_mode(state, mode=mode)

    graph_runner = graph_runner or run_trading_graph
    decide = decide or decide_trade
    execute = execute or execute_from_packet

    if selected == "decision_packet":
        state = decide(state)
        state = execute(state)
        return state

    return graph_runner(state)
