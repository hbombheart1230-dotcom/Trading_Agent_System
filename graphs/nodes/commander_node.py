from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime


def commander_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience node that runs canonical commander runtime.

    For backward compatibility, this node defaults to M17 graph_spine mode.
    """
    return run_commander_runtime(state, mode="graph_spine")
