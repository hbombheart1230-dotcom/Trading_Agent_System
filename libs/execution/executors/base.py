from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol, Optional

from libs.core.api_response import ApiResponse
from libs.catalog.api_request_builder import PreparedRequest


class ExecutionDisabledError(Exception):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    response: ApiResponse
    meta: Dict[str, Any]


class OrderExecutor(Protocol):
    """Executor interface.
    - Must NOT decide whether to trade. It only executes when called.
    - Supervisor gating must happen BEFORE calling executor.
    """

    def execute(self, req: PreparedRequest, *, auth_token: Optional[str] = None) -> ExecutionResult:
        ...
