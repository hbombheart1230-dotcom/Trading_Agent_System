from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings
from libs.risk.supervisor import Supervisor, AllowResult
from libs.catalog.api_request_builder import PreparedRequest


@dataclass(frozen=True)
class OrderDryRun:
    allowed: bool
    reason: str
    url: str
    method: str
    headers: Dict[str, Any]
    query: Dict[str, Any]
    body: Dict[str, Any]


class OrderClient:
    """Order client (M7-2) – DRY-RUN ONLY.

    Responsibilities:
    - Enforce Supervisor guardrails before preparing an order request
    - Attach auth headers (token) but never send the request
    - Return a dry-run payload for inspection/logging

    Guarantees:
    - No network calls (always dry-run)
    """

    def __init__(self, settings: Optional[Settings] = None, http: Optional[HttpClient] = None):
        self.s = settings or Settings.from_env()
        self.http = http or HttpClient(
            self.s.base_url,
            timeout_sec=self.s.kiwoom_http_timeout_sec,
            retry_max=self.s.kiwoom_retry_max,
        )
        self.tokens = KiwoomTokenClient(self.s, self.http)
        self.supervisor = Supervisor(self.s)

    def dry_run_order(
        self,
        prepared: PreparedRequest,
        *,
        intent: str,
        risk_context: Dict[str, Any],
        dry_run_token: bool = True,
    ) -> OrderDryRun:
        # 1) Supervisor gate
        allow: AllowResult = self.supervisor.allow(intent, risk_context)
        url = self.http.build_url(prepared.path)

        if not allow.allow:
            return OrderDryRun(
                allowed=False,
                reason=allow.reason,
                url=url,
                method=prepared.method,
                headers={},
                query=prepared.query,
                body=prepared.body,
            )

        # 2) Ensure token (dry-run by default so no auth call during tests)
        ensure = self.tokens.ensure_token(dry_run=dry_run_token)

        headers = dict(prepared.headers or {})
        if ensure.action != "dry_run" and ensure.token:
            headers.update(self.tokens.auth_headers(ensure.token))
        else:
            # show intended auth header shape without real token
            headers["Authorization"] = "Bearer <token>"

        return OrderDryRun(
            allowed=True,
            reason="Allowed (dry-run)",
            url=url,
            method=prepared.method,
            headers=headers,
            query=prepared.query,
            body=prepared.body,
        )
