from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol


@dataclass(frozen=True)
class Candidate:
    symbol: str
    why: str = ""


class CandidateGenerator(Protocol):
    """Generates 3~5 candidate symbols automatically."""

    def generate(self, state: Dict[str, Any]) -> List[Candidate]: ...
