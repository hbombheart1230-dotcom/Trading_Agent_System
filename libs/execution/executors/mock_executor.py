from __future__ import annotations

from typing import Any, Dict, Optional

from libs.core.api_response import ApiResponse
from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionResult


class MockExecutor:
    """Mock executor: never calls network, never trades.
    Returns ApiResponse(ok=True) with the would-be request payload.
    """

    def __init__(self, base_url: str = ""):
        self.base_url = base_url.rstrip("/")

    def execute(self, req: PreparedRequest, *, auth_token: Optional[str] = None) -> ExecutionResult:
        url = f"{self.base_url}{req.path}" if self.base_url else req.path
        payload: Dict[str, Any] = {
            "mode": "mock",
            "url": url,
            "method": req.method,
            "headers": dict(req.headers or {}),
            "query": dict(req.query or {}),
            "body": dict(req.body or {}),
        }
        if auth_token:
            payload["headers"]["Authorization"] = f"Bearer {auth_token}"
        else:
            payload["headers"]["Authorization"] = "Bearer <token>"

        resp = ApiResponse(
            status_code=0,
            ok=True,
            payload=payload,
            error_code=None,
            error_message=None,
            raw_text="",
        )
        return ExecutionResult(response=resp, meta={"executor": "mock"})
