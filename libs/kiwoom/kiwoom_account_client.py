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

    @staticmethod
    def _is_invalid_token_payload(payload: Dict[str, object]) -> bool:
        text = str(payload.get("return_msg") or payload.get("message") or "").lower()
        code = str(payload.get("return_code") or payload.get("code") or "").strip()
        return code in {"3", "8005", "805004"} and ("token" in text or "인증" in text or "8005" in text)

    def get_account_balance(self, *, dry_run: bool = False) -> ApiResponse:
        # Kiwoom REST (mock/real) account-balance endpoint.
        # Legacy /uapi path is not used by Kiwoom OpenAPI and causes unstable responses.
        path = "/api/dostk/acnt"
        # kt00018: 계좌평가잔고내역요청 (current holdings)
        api_id = "kt00018"

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
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["api-id"] = api_id
        if self.s.kiwoom_app_key:
            headers.setdefault("appkey", self.s.kiwoom_app_key)
        if self.s.kiwoom_app_secret:
            headers.setdefault("appsecret", self.s.kiwoom_app_secret)

        body = {
            "qry_tp": "1",
            "dmst_stex_tp": "KRX",
        }

        url, resp = self.http.request("POST", path, headers=headers, json_body=body)
        assert resp is not None
        parsed = ApiResponse.from_http(resp.status_code, resp.text)
        payload = parsed.payload if isinstance(parsed.payload, dict) else {}
        if self._is_invalid_token_payload(payload):
            ensure = self.tokens.ensure_token(dry_run=False, force_refresh=True)
            headers.update(self.tokens.auth_headers(ensure.token))
            url, resp = self.http.request("POST", path, headers=headers, json_body=body)
            assert resp is not None
            parsed = ApiResponse.from_http(resp.status_code, resp.text)
            payload = parsed.payload if isinstance(parsed.payload, dict) else {}
        rc = str(payload.get("return_code") or "").strip()
        if rc and rc not in ("0",):
            msg = str(payload.get("return_msg") or payload.get("message") or "").strip()
            return ApiResponse(
                status_code=parsed.status_code,
                ok=False,
                payload=payload,
                error_code=rc,
                error_message=msg or f"kiwoom_account_error(return_code={rc})",
                raw_text=parsed.raw_text,
            )
        return parsed
