from __future__ import annotations

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings
from libs.core.api_response import ApiResponse

class KiwoomAccountClient:
    """Read-only account APIs (M6-3).
    Safe endpoints only (no trading).
    """

    def __init__(self, settings: Settings, http: HttpClient, token_client: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.tokens = token_client

    def get_account_balance(self, *, dry_run: bool = False) -> ApiResponse:
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"

        ensure = self.tokens.ensure_token(dry_run=dry_run)
        if dry_run:
            return ApiResponse(
                status_code=0,
                ok=True,
                payload={"action": ensure.action, "reason": ensure.reason},
                error_code=None,
                error_message=None,
                raw_text="",
            )

        headers = {}
        headers.update(self.tokens.auth_headers(ensure.token))

        url, resp = self.http.request(
            "GET",
            path,
            headers=headers,
            params={
                "CANO": self.s.kiwoom_account_no,
                "ACNT_PRDT_CD": "01",
            },
        )
        assert resp is not None
        return ApiResponse.from_http(resp.status_code, resp.text)
