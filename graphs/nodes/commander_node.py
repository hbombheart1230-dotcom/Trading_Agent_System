from __future__ import annotations

from typing import Any, Dict

from graphs.trading_graph import run_trading_graph


def commander_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Optional convenience node that runs the whole M17 baseline graph.

    This keeps a 'Commander-like' interface for callers that want a single entry.
    """
    return run_trading_graph(state)
