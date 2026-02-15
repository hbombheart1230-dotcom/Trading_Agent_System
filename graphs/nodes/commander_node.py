from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime


def commander_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience node that runs canonical commander runtime.

    Mode resolution is delegated to commander runtime policy:
      explicit > state["runtime_mode"] > env COMMANDER_RUNTIME_MODE > graph_spine(default)
    """
    return run_commander_runtime(state)
