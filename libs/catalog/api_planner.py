from dataclasses import dataclass
from typing import List

from libs.catalog.api_discovery import ApiMatch


@dataclass(frozen=True)
class PlanResult:
    action: str  # 'select' or 'ask'
    selected: ApiMatch | None
    candidates: List[ApiMatch]
    reason: str


class ApiPlanner:
    def __init__(self, select_threshold: float = 0.85, margin_threshold: float = 0.15):
        self.select_threshold = select_threshold
        self.margin_threshold = margin_threshold

    def plan(self, matches: List[ApiMatch]) -> PlanResult:
        if not matches:
            return PlanResult(
                action="ask",
                selected=None,
                candidates=[],
                reason="No candidates found"
            )

        top = matches[0]
        if len(matches) == 1:
            return PlanResult(
                action="select",
                selected=top,
                candidates=matches,
                reason="Only one candidate"
            )

        second = matches[1]
        if (
            top.score >= self.select_threshold and
            (top.score - second.score) >= self.margin_threshold
        ):
            return PlanResult(
                action="select",
                selected=top,
                candidates=matches,
                reason="High confidence selection"
            )

        return PlanResult(
            action="ask",
            selected=None,
            candidates=matches[:3],
            reason="Ambiguous intent"
        )