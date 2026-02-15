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

from typing import Any, Callable, Dict, Literal, Optional

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet


RuntimeMode = Literal["graph_spine", "decision_packet"]


def run_commander_runtime(
    state: Dict[str, Any],
    *,
    mode: Optional[RuntimeMode] = None,
    graph_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    execute: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one canonical commander runtime step.

    Priority for mode selection:
      1) explicit `mode` argument
      2) state["runtime_mode"] when valid
      3) default "graph_spine"
    """
    selected = str(mode or state.get("runtime_mode") or "graph_spine").strip().lower()
    if selected not in ("graph_spine", "decision_packet"):
        selected = "graph_spine"

    graph_runner = graph_runner or run_trading_graph
    decide = decide or decide_trade
    execute = execute or execute_from_packet

    if selected == "decision_packet":
        state = decide(state)
        state = execute(state)
        return state

    return graph_runner(state)

