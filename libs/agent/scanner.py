from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from libs.agent.strategist import Plan


class Scanner:
    """Turns a Plan into concrete order intents.

    NOTE: This is a placeholder scaffold. Real scanning logic (signals, ranking, etc.)
    can be added incrementally.
    """

    def scan(self, *, plan: Plan, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # If user provides explicit intents, pass-through
        provided = context.get("intents")
        if isinstance(provided, list) and all(isinstance(x, dict) for x in provided):
            return provided

        # Minimal default: no trading unless explicitly requested
        return []
