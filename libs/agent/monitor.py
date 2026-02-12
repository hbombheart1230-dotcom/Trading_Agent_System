from __future__ import annotations

from typing import Any, Dict, List


class Monitor:
    """Tracks state across cycles (positions, open intents, etc.)."""

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
