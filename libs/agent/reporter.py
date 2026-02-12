from __future__ import annotations

from typing import Any, Dict, List, Optional


class Reporter:
    """Builds a structured summary for UI/logging."""

    def build(
        self,
        *,
        run_id: str,
        context: Dict[str, Any],
        plan: Any,
        intents: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        executions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "plan": getattr(plan, "__dict__", str(plan)),
            "intents_count": len(intents),
            "decisions_count": len(decisions),
            "executions_count": len(executions),
        }
