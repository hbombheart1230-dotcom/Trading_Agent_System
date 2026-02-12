from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Plan:
    """Strategist output: describes what to look for, not how to execute."""
    thesis: str
    constraints: Dict[str, Any]


class Strategist:
    """Produces a high-level plan for a run.

    In M15 we keep this deterministic/minimal by default.
    You can later plug in LLM reasoning, news context, etc.
    """

    def plan(self, *, context: Dict[str, Any]) -> Plan:
        thesis = str(context.get("thesis") or "default_thesis")
        constraints = dict(context.get("constraints") or {})
        return Plan(thesis=thesis, constraints=constraints)
