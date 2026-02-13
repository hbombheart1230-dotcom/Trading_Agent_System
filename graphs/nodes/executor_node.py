from __future__ import annotations

from typing import Any, Dict


def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Executor (stub).

    M17 baseline **does not execute orders**.
    It only marks that an execution step is pending.

    Writes:
      - state['execution_pending'] = True
    """
    state["execution_pending"] = True
    return state
