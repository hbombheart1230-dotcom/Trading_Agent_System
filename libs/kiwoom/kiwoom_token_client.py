from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import json
import time

from libs.core.http_client import HttpClient
from libs.core.path_isolation import resolve_runtime_write_path
from libs.core.settings import Settings
from libs.kiwoom.token_cache import TokenCache, TokenRecord
from libs.kiwoom.token_refresh_guard import TokenRefreshGuard


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
        # Call-time isolation (Phase 1 P0 Fix 2): Settings.kiwoom_token_cache_path
        # defaults to a production-relative "./data/token_cache.json" with no
        # isolation of its own -- TokenCache's saved token, and
        # TokenRefreshGuard's lock/failure-cooldown sidecar files derived
        # from the same path, must never land in the real repository during
        # pytest. Confirmed leak: a test exercising a token-acquisition
        # failure path writes a real, disk-persistent
        # data/token_cache.json.refresh_failure.json cooldown record that
        # then blocks unrelated tests hitting the same real path within the
        # cooldown window, in a later pytest invocation as well as later in
        # the same run.
        self._token_cache_path = resolve_runtime_write_path(self.s.kiwoom_token_cache_path)
        self.cache = TokenCache(self._token_cache_path)

    def ensure_token(self, *, dry_run: bool = False, force_refresh: bool = False) -> EnsureTokenResult:
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
        if cached and (not force_refresh) and (not cached.will_expire_within(margin)):
            return EnsureTokenResult(
                action="cache_hit",
                token=cached.access_token,
                expires_at_epoch=cached.expires_at_epoch,
                reason="Valid cached token",
            )

        guard = TokenRefreshGuard(self._token_cache_path)
        try:
            with guard:
                # Another process may have refreshed while this process waited.
                cached = self.cache.load()
                if cached and (not force_refresh) and (not cached.will_expire_within(margin)):
                    return EnsureTokenResult(
                        action="cache_hit",
                        token=cached.access_token,
                        expires_at_epoch=cached.expires_at_epoch,
                        reason="Valid cached token after refresh wait",
                    )
                failure = guard.active_failure() if not force_refresh else None
                if failure:
                    raise KiwoomAuthError(
                        "Token refresh cooldown active: "
                        + str(failure.get("reason") or "previous refresh failed")
                    )
                try:
                    result = self._refresh_token()
                except Exception as exc:
                    guard.record_failure(str(exc))
                    raise
                guard.clear_failure()
                return result
        except TimeoutError as exc:
            raise KiwoomAuthError(str(exc)) from exc

    def _refresh_token(self) -> EnsureTokenResult:
        endpoint = self._token_endpoint()
        body = self._token_request_body()
        _url, resp = self.http.request(
            "POST",
            endpoint,
            headers={"Content-Type": "application/json"},
            json_body=body,
            dry_run=False,
        )
        assert resp is not None
        try:
            payload = json.loads(resp.text or "{}")
        except Exception as exc:
            raise KiwoomAuthError(f"Token response not JSON: {resp.text}") from exc
        if resp.status_code >= 400:
            raise KiwoomAuthError(f"Token request failed ({resp.status_code}): {payload}")
        access_token = str(payload.get("access_token") or payload.get("token") or "")
        token_type = str(payload.get("token_type") or "Bearer")
        expires_in = int(payload.get("expires_in") or payload.get("expiresIn") or 0)
        if not access_token:
            raise KiwoomAuthError(f"Token missing in response: {payload}")
        expires_at = 0
        expires_dt = str(payload.get("expires_dt") or "").strip()
        if len(expires_dt) == 14 and expires_dt.isdigit():
            try:
                expires_at = int(
                    datetime.strptime(expires_dt, "%Y%m%d%H%M%S")
                    .replace(tzinfo=timezone(timedelta(hours=9)))
                    .timestamp()
                )
            except ValueError:
                expires_at = 0
        if expires_at <= 0:
            expires_at = int(time.time()) + (expires_in if expires_in > 0 else 3600)
        self.cache.save(
            TokenRecord(
                access_token=access_token,
                token_type=token_type,
                expires_at_epoch=expires_at,
                raw=payload,
            )
        )
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
