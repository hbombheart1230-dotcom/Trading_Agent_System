from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


StateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class IntegratedChainNodes:
    build_portfolio_snapshot: StateFn
    build_risk_context: StateFn
    strategist_node: StateFn
    scanner_node: StateFn
    monitor_node: StateFn
    decision_node: StateFn
    reporter_node: StateFn
    update_state_after_execution: StateFn


def load_integrated_chain_nodes() -> IntegratedChainNodes:
    from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
    from graphs.nodes.build_risk_context import build_risk_context
    from graphs.nodes.decision_node import decision_node
    from graphs.nodes.monitor_node import monitor_node
    from graphs.nodes.reporter_node import reporter_node
    from graphs.nodes.scanner_node import scanner_node
    from graphs.nodes.strategist_node import strategist_node
    from graphs.nodes.update_state_after_execution import update_state_after_execution

    return IntegratedChainNodes(
        build_portfolio_snapshot=build_portfolio_snapshot,
        build_risk_context=build_risk_context,
        strategist_node=strategist_node,
        scanner_node=scanner_node,
        monitor_node=monitor_node,
        decision_node=decision_node,
        reporter_node=reporter_node,
        update_state_after_execution=update_state_after_execution,
    )
