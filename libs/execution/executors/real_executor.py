from __future__ import annotations

import os
from typing import Optional, Any
from types import SimpleNamespace

from libs.core.api_response import ApiResponse
from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionResult, ExecutionDisabledError
from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings


class RealExecutor:
    """Real executor: performs HTTP call via HttpClient.

    Safety:
      - KIWOOM_MODE=real (default): requires EXECUTION_ENABLED=true to run.
      - KIWOOM_MODE=mock: allows execution even if EXECUTION_ENABLED is unset/false.

    Notes:
      - Accepts `catalog=...` for compatibility.
      - Kiwoom REST requires an API ID header; we set it from req.api_id automatically.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http: Optional[Any] = None,
        *,
        catalog: Any = None,
        **_: Any,
    ):
        self.s = settings or Settings.from_env()
        self.http = http or HttpClient(
            self.s.base_url,
            timeout_sec=self.s.kiwoom_http_timeout_sec,
            retry_max=self.s.kiwoom_retry_max,
        )
        self.catalog = catalog
        self.tokens = KiwoomTokenClient(self.s, self.http)

    def _coerce_request(self, req: Any) -> Any:
        """Accept either PreparedRequest or a dict from simple demos."""
        if isinstance(req, PreparedRequest):
            return req
        if isinstance(req, dict):
            return SimpleNamespace(
                api_id=req.get("api_id") or req.get("apiId") or req.get("id") or req.get("api") or "UNKNOWN",
                method=(req.get("method") or req.get("http_method") or "GET"),
                path=req.get("path") or req.get("url_path") or "/",
                headers=req.get("headers") or {},
                query=req.get("query") or {},
                body=req.get("body"),
            )
        return req

    def execute(self, req: Any, *, auth_token: Optional[str] = None) -> ExecutionResult:
        req = self._coerce_request(req)

        mode = (os.getenv("KIWOOM_MODE", "real") or "real").strip().lower()
        enabled = (os.getenv("EXECUTION_ENABLED", "false") or "false").lower() == "true"
        if mode != "mock" and not enabled:
            raise ExecutionDisabledError("Execution is disabled. Set EXECUTION_ENABLED=true to allow real calls.")

        token = auth_token
        if not token:
            ensure = self.tokens.ensure_token(dry_run=False)
            token = ensure.token

        headers = dict(getattr(req, "headers", None) or {})

        # --- REQUIRED: API ID header (Kiwoom returns 1501 if missing) ---
        api_id = getattr(req, "api_id", None) or headers.get("api-id") or headers.get("api_id")
        if api_id:
            headers.setdefault("api-id", str(api_id))
            headers.setdefault("api_id", str(api_id))  # harmless; some gateways accept either

        # Auth header
        headers["Authorization"] = f"Bearer {token}"

        # App credentials (some endpoints require these headers)
        if getattr(self.s, "kiwoom_app_key", None):
            headers.setdefault("appkey", self.s.kiwoom_app_key)
        if getattr(self.s, "kiwoom_app_secret", None):
            headers.setdefault("appsecret", self.s.kiwoom_app_secret)

        method = (getattr(req, "method", "GET") or "GET").upper()
        path = getattr(req, "path", "/") or "/"
        params = getattr(req, "query", None) or {}
        json_body = getattr(req, "body", None) if getattr(req, "body", None) else None

        url, resp = self.http.request(
            method,
            path,
            headers=headers,
            params=params,
            json_body=json_body,
            dry_run=False,
        )

        assert resp is not None
        api_resp = ApiResponse.from_http(resp.status_code, resp.text)
        return ExecutionResult(response=api_resp, meta={"executor": "real", "url": url})
