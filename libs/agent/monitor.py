from __future__ import annotations

from typing import Any, Dict, List


class Monitor:
    """Legacy monitor interface placeholder.

    Canonical monitor behavior is implemented in `graphs/nodes/monitor_node.py`.
    This class remains for compatibility with legacy commander tests/wiring.
    """

    def update(
        self,
        *,
        intents: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        executions: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> None:
        # Placeholder: integrate with repo/state_store later.
        return
