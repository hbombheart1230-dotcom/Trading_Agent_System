from __future__ import annotations

from typing import Any, Dict, Optional, Set
import os

from libs.core.api_response import ApiResponse
from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionResult, ExecutionDisabledError
from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings


class RealExecutor:
    """Real executor: performs actual HTTP call.

    Safety:
    - If KIWOOM_MODE=real:
        - Requires EXECUTION_ENABLED=true
        - Requires ALLOW_REAL_EXECUTION=true
      (Must be enforced BEFORE token issuance / any HTTP call)
    - Optional: SYMBOL_ALLOWLIST (if set) blocks disallowed symbols.
    """

    def __init__(self, settings: Optional[Settings] = None, http: Optional[HttpClient] = None):
        self.s = settings or Settings.from_env()
        self.http = http or HttpClient(
            self.s.base_url,
            timeout_sec=self.s.kiwoom_http_timeout_sec,
            retry_max=self.s.kiwoom_retry_max,
        )
        self.tokens = KiwoomTokenClient(self.s, self.http)

    @staticmethod
    def _parse_symbol_allowlist(raw: Optional[str]) -> Set[str]:
        """Parse SYMBOL_ALLOWLIST.

        - If env var is missing/empty/whitespace => returns empty set (guard disabled).
        - Supports comma-separated values, e.g. "005930,000660".
        """
        if raw is None:
            return set()
        raw = raw.strip()
        if not raw:
            return set()
        return {s.strip() for s in raw.split(",") if s.strip()}

    @staticmethod
    def _extract_symbol(req: PreparedRequest) -> Optional[str]:
        """Best-effort extract symbol from request body."""
        body = req.body or {}
        sym = body.get("stk_cd") or body.get("symbol")
        if sym is None:
            return None
        sym = str(sym).strip()
        return sym or None

    def _enforce_symbol_allowlist(self, req: PreparedRequest) -> None:
        allow = self._parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST"))
        if not allow:
            return  # guard disabled

        sym = self._extract_symbol(req)
        if sym is None:
            return  # nothing to validate

        if sym not in allow:
            raise ExecutionDisabledError(
                f"Symbol '{sym}' is not allowed by SYMBOL_ALLOWLIST. Allowed={sorted(allow)}"
            )

    @staticmethod
    def _env_flag_true(name: str, default: str = "false") -> bool:
        return (os.getenv(name, default) or default).strip().lower() == "true"

    @staticmethod
    def _deny(code: str, message: str) -> Dict[str, Any]:
        return {"ok": False, "code": str(code or "").strip() or "UNKNOWN", "message": str(message or "")}

    @staticmethod
    def _allow() -> Dict[str, Any]:
        return {"ok": True, "code": "OK", "message": "allowed"}

    def preflight_check(self, req: Optional[PreparedRequest] = None) -> Dict[str, Any]:
        """M24-5: explicit preflight check with stable denial reason codes.

        This is a pure guard evaluation step. It performs no token issuance and no HTTP calls.
        """
        mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower()
        enabled = self._env_flag_true("EXECUTION_ENABLED", "false")

        if mode == "real":
            if not enabled:
                return self._deny(
                    "EXECUTION_DISABLED",
                    "Execution is disabled. Set EXECUTION_ENABLED=true to allow real calls.",
                )

            allow_real = self._env_flag_true("ALLOW_REAL_EXECUTION", "false")
            if not allow_real:
                return self._deny(
                    "REAL_EXECUTION_NOT_ALLOWED",
                    "Real execution is not allowed. Set ALLOW_REAL_EXECUTION=true to allow real calls.",
                )

            if not str(self.s.kiwoom_app_key or "").strip():
                return self._deny(
                    "MISSING_APP_KEY",
                    "KIWOOM_APP_KEY is required in real mode.",
                )
            if not str(self.s.kiwoom_app_secret or "").strip():
                return self._deny(
                    "MISSING_APP_SECRET",
                    "KIWOOM_APP_SECRET is required in real mode.",
                )
            if not str(self.s.kiwoom_account_no or "").strip():
                return self._deny(
                    "MISSING_ACCOUNT_NO",
                    "KIWOOM_ACCOUNT_NO is required in real mode.",
                )
            if not str(self.s.base_url or "").strip().lower().startswith("https://"):
                return self._deny(
                    "INVALID_BASE_URL",
                    "Real mode requires https base URL.",
                )
        else:
            # Keep compatibility:
            # - mock mode can run with EXECUTION_ENABLED=false
            # - unknown/non-mock mode behaves like real for execution_enabled guard
            if mode != "mock" and not enabled:
                return self._deny(
                    "EXECUTION_DISABLED",
                    "Execution is disabled. Set EXECUTION_ENABLED=true to allow real calls.",
                )

        if req is not None:
            allow = self._parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST"))
            if allow:
                sym = self._extract_symbol(req)
                if sym is not None and sym not in allow:
                    return self._deny(
                        "ALLOWLIST_BLOCKED",
                        f"Symbol '{sym}' is not allowed by SYMBOL_ALLOWLIST. Allowed={sorted(allow)}",
                    )

        return self._allow()

    def execute(self, req: PreparedRequest, *, auth_token: Optional[str] = None) -> ExecutionResult:
        """
        IMPORTANT ORDER:
          1) Mode/Execution/Allow-Real guards
          2) Allowlist guard
          3) Token issuance
          4) HTTP request
        """
        pf = self.preflight_check(req)
        if not bool(pf.get("ok")):
            code = str(pf.get("code") or "UNKNOWN")
            msg = str(pf.get("message") or "Execution preflight check failed.")
            raise ExecutionDisabledError(f"[{code}] {msg}")

        # --- Token issuance (only after all guards pass) ---
        token = auth_token
        if not token:
            ensure = self.tokens.ensure_token(dry_run=False)
            token = ensure.token

        headers = dict(req.headers or {})
        headers.update({"Authorization": f"Bearer {token}"})

        # Kiwoom REST commonly requires app credentials on each request.
        # (Token endpoint itself is handled by KiwoomTokenClient.)
        if self.s.kiwoom_app_key:
            headers.setdefault("appkey", self.s.kiwoom_app_key)
        if self.s.kiwoom_app_secret:
            headers.setdefault("appsecret", self.s.kiwoom_app_secret)

        url, resp = self.http.request(
            req.method,
            req.path,
            headers=headers,
            params=req.query,
            json_body=req.body if req.body else None,
            dry_run=False,
        )
        assert resp is not None
        api_resp = ApiResponse.from_http(resp.status_code, resp.text)
        return ExecutionResult(response=api_resp, meta={"executor": "real", "url": url})
