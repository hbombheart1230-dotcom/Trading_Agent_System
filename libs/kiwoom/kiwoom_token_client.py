from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
import json
import time

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.token_cache import TokenCache, TokenRecord


class KiwoomAuthError(Exception):
    pass


@dataclass(frozen=True)
class EnsureTokenResult:
    action: str  # 'cache_hit' | 'refreshed' | 'dry_run'
    token: str
    expires_at_epoch: int
    reason: str


class KiwoomTokenClient:
    """Kiwoom token client (M6-2).

    Important behavior:
    - If dry_run=True, NEVER requires credentials and NEVER makes HTTP calls.
      It returns a placeholder result so upstream dry-run pipelines can run without .env secrets.
    """

    def __init__(self, settings: Settings, http: HttpClient):
        self.s = settings
        self.http = http
        self.cache = TokenCache(self.s.kiwoom_token_cache_path)

    def ensure_token(self, *, dry_run: bool = False) -> EnsureTokenResult:
        # ✅ Dry-run must be side-effect free and must not require secrets.
        if dry_run:
            return EnsureTokenResult(
                action="dry_run",
                token="",
                expires_at_epoch=0,
                reason="Dry-run: token request skipped",
            )

        margin = int(self.s.kiwoom_token_refresh_margin_sec)
        cached = self.cache.load()
        if cached and (not cached.will_expire_within(margin)):
            return EnsureTokenResult(
                action="cache_hit",
                token=cached.access_token,
                expires_at_epoch=cached.expires_at_epoch,
                reason="Valid cached token",
            )

        endpoint = self._token_endpoint()
        body = self._token_request_body()
        url, resp = self.http.request(
            "POST",
            endpoint,
            headers={"Content-Type": "application/json"},
            json_body=body,
            dry_run=False,
        )

        assert resp is not None
        try:
            payload = json.loads(resp.text or "{}")
        except Exception as e:
            raise KiwoomAuthError(f"Token response not JSON: {resp.text}") from e

        if resp.status_code >= 400:
            raise KiwoomAuthError(f"Token request failed ({resp.status_code}): {payload}")

        access_token = str(payload.get("access_token") or payload.get("token") or "")
        token_type = str(payload.get("token_type") or "Bearer")
        expires_in = int(payload.get("expires_in") or payload.get("expiresIn") or 0)

        if not access_token:
            raise KiwoomAuthError(f"Token missing in response: {payload}")

        if expires_in <= 0:
            expires_in = 3600
        expires_at = int(time.time()) + expires_in

        rec = TokenRecord(
            access_token=access_token,
            token_type=token_type,
            expires_at_epoch=expires_at,
            raw=payload,
        )
        self.cache.save(rec)

        return EnsureTokenResult(
            action="refreshed",
            token=access_token,
            expires_at_epoch=expires_at,
            reason="Token refreshed and cached",
        )

    def auth_headers(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _token_endpoint(self) -> str:
        return "/oauth2/token"

    def _token_request_body(self) -> Dict[str, Any]:
        if not self.s.kiwoom_app_key or not self.s.kiwoom_app_secret:
            raise KiwoomAuthError("Missing KIWOOM_APP_KEY / KIWOOM_APP_SECRET in .env")
        return {
            "grant_type": "client_credentials",
            "appkey": self.s.kiwoom_app_key,
            "secretkey": self.s.kiwoom_app_secret,
        }
