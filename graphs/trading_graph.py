from __future__ import annotations

"""M17: Graph spine (B: conditional branching baseline).

This module intentionally avoids taking a hard dependency on LangGraph yet.
It provides a stable *graph-shaped* execution surface that we can later
swap to LangGraph with minimal refactor.

Contract:
  - Input/Output is a mutable dict-like `state`.
  - Nodes are pure-ish functions: node(state) -> state (may mutate).
  - Branching happens at `decision_node`.
"""

from typing import Any, Dict, Callable, Optional, Literal

from graphs.nodes.strategist_node import strategist_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.decision_node import decision_node
from graphs.nodes.executor_node import executor_node
from graphs.nodes.hydrate_skill_results_node import hydrate_skill_results_node


Decision = Literal["approve", "reject", "noop", "retry_scan"]


def run_trading_graph(
    state: Dict[str, Any],
    *,
    strategist: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    hydrate: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    scanner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    monitor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the M17 baseline graph.

    Flow (B, M17-3 + M22-6):
      Strategist -> (optional HydrateSkillResults) -> Scanner -> Monitor -> Decision
        - approve    -> Executor (stub: marks execution_pending)
        - retry_scan -> (optional HydrateSkillResults) -> Scanner -> Monitor -> Decision
          (loop up to policy.max_scan_retries)
        - reject/noop-> END

    Injection points exist for tests/experiments.
    """

    strategist = strategist or strategist_node
    hydrate = hydrate or hydrate_skill_results_node
    scanner = scanner or scanner_node
    monitor = monitor or monitor_node
    decide = decide or decision_node
    executor = executor or executor_node

    def _should_hydrate(s: Dict[str, Any]) -> bool:
        if bool(s.get("use_skill_hydration")):
            return True
        return bool(s.get("skill_runner"))

    state = strategist(state)

    # Initial pass
    if _should_hydrate(state):
        state = hydrate(state)
    state = scanner(state)
    state = monitor(state)
    state = decide(state)

    # Retry loop (scanner-only)
    while str(state.get("decision") or "").lower() == "retry_scan":
        if _should_hydrate(state):
            state = hydrate(state)
        state = scanner(state)
        state = monitor(state)
        state = decide(state)

    decision: str = str(state.get("decision") or "noop").lower()
    if decision == "approve":
        state = executor(state)

    return state
