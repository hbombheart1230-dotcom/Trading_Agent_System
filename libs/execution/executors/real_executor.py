from __future__ import annotations

from typing import Any, Dict, Optional, Set
import os

from libs.core.api_response import ApiResponse
from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionResult, ExecutionDisabledError
from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings
from libs.execution.guards.symbol_allowlist import (
    parse_symbol_allowlist as _canonical_parse_symbol_allowlist,
)
from libs.execution.guards.broker_mutation import (
    classify_mutation_response,
    is_mutation_request,
)


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

        Delegates to the canonical parser (libs/execution/guards/symbol_allowlist.py)
        so this executor and the execute_from_packet guard chain share one
        parsing/normalization implementation. Kept as a static method with the
        same name/signature for backward compatibility with existing callers.
        """
        return _canonical_parse_symbol_allowlist(raw)

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

    @staticmethod
    def _is_invalid_token_response(response: ApiResponse) -> bool:
        payload = response.payload if isinstance(response.payload, dict) else {}
        text = str(payload.get("return_msg") or payload.get("message") or response.error_message or "").lower()
        code = str(payload.get("return_code") or payload.get("code") or response.error_code or "").strip()
        return code in {"3", "8005", "805004"} and ("token" in text or "인증" in text or "8005" in text)

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

        Broker mutation safety (Phase 1 Step 5B): when req targets a broker
        mutation api_id (BUY/SELL/CANCEL/MODIFY), this method guarantees at
        most one physical HTTP submission attempt, never automatically
        replays that submission after a token-invalid-looking response, and
        never lets a post-submission exception escape uncaught -- it is
        converted into a BrokerOutcome-classified ExecutionResult instead
        (see libs/execution/guards/broker_mutation.py). Non-mutation
        (read/query/token) calls are entirely unaffected.
        """
        # Phase 1 Step 5B Safety Fix 2: cross-checks api_id against
        # action/side/operation on the request too, so a custom
        # order_builder or an alternate live mutation path (execute_order.py,
        # the tool-facade skill runner) can't silently escape mutation-safe
        # transport treatment just because api_id ended up missing/wrong.
        is_mutation = is_mutation_request(req)

        pf = self.preflight_check(req)
        if not bool(pf.get("ok")):
            code = str(pf.get("code") or "UNKNOWN")
            msg = str(pf.get("message") or "Execution preflight check failed.")
            raise ExecutionDisabledError(f"[{code}] {msg}")

        # --- Token issuance (only after all guards pass) ---
        token = auth_token
        token_from_cache = not bool(token)
        if not token:
            try:
                ensure = self.tokens.ensure_token(dry_run=False)
                token = ensure.token
            except Exception as exc:
                if is_mutation:
                    # Token acquisition failed strictly before the mutation
                    # HTTP call was ever attempted -> definitely NOT_SENT.
                    raise ExecutionDisabledError(f"[TOKEN_ACQUISITION_FAILED] {exc}") from exc
                raise

        headers = dict(req.headers or {})
        headers.update({"Authorization": f"Bearer {token}"})

        # Kiwoom order/read endpoints commonly require API id header.
        # Ensure runtime-prepared requests always carry it.
        if getattr(req, "api_id", None):
            headers.setdefault("api-id", str(getattr(req, "api_id")))

        # Kiwoom REST commonly requires app credentials on each request.
        # (Token endpoint itself is handled by KiwoomTokenClient.)
        if self.s.kiwoom_app_key:
            headers.setdefault("appkey", self.s.kiwoom_app_key)
        if self.s.kiwoom_app_secret:
            headers.setdefault("appsecret", self.s.kiwoom_app_secret)

        json_body = req.body if req.body or str(req.method or "").upper() == "POST" else None

        if is_mutation:
            return self._execute_mutation(req, headers=headers, json_body=json_body)

        url, resp = self.http.request(
            req.method,
            req.path,
            headers=headers,
            params=req.query,
            json_body=json_body,
            dry_run=False,
        )
        assert resp is not None
        api_resp = ApiResponse.from_http(resp.status_code, resp.text)
        if token_from_cache and self._is_invalid_token_response(api_resp):
            ensure = self.tokens.ensure_token(dry_run=False, force_refresh=True)
            headers.update({"Authorization": f"Bearer {ensure.token}"})
            url, resp = self.http.request(
                req.method,
                req.path,
                headers=headers,
                params=req.query,
                json_body=json_body,
                dry_run=False,
            )
            assert resp is not None
            api_resp = ApiResponse.from_http(resp.status_code, resp.text)
        return ExecutionResult(response=api_resp, meta={"executor": "real", "url": url})

    def _execute_mutation(
        self,
        req: PreparedRequest,
        *,
        headers: Dict[str, Any],
        json_body: Optional[Dict[str, Any]],
    ) -> ExecutionResult:
        """One broker mutation transport attempt, classified into BrokerOutcome.

        Invariant: one logical mutation -> at most one transport submission
        attempt (retry_override=0). Never raises for anything that happens
        during or after that single attempt -- always returns an
        ExecutionResult with meta['broker_outcome'] in
        {ACCEPTED, REJECTED, UNKNOWN} so the caller can quarantine on
        UNKNOWN instead of losing provenance to an uncaught exception.
        """
        try:
            url, resp = self.http.request(
                req.method,
                req.path,
                headers=headers,
                params=req.query,
                json_body=json_body,
                dry_run=False,
                retry_override=0,
            )
        except Exception as exc:
            return ExecutionResult(
                response=ApiResponse(
                    status_code=0,
                    ok=False,
                    payload={},
                    error_code=None,
                    error_message=str(exc),
                    raw_text="",
                ),
                meta={
                    "executor": "real",
                    "broker_outcome": "UNKNOWN",
                    "submission_phase": "mutation_http_call",
                    "submission_attempts": 1,
                    "exception_type": type(exc).__name__,
                    "reconciliation_required": True,
                },
            )

        assert resp is not None
        api_resp = ApiResponse.from_http(resp.status_code, resp.text)

        if self._is_invalid_token_response(api_resp):
            # The mutation has already been submitted once. Do not refresh
            # the token and replay the same mutation on a guess -- treat the
            # outcome as unknown and let reconciliation resolve it.
            return ExecutionResult(
                response=api_resp,
                meta={
                    "executor": "real",
                    "broker_outcome": "UNKNOWN",
                    "submission_phase": "mutation_http_call",
                    "submission_attempts": 1,
                    "exception_type": "",
                    "reconciliation_required": True,
                    "note": "token_invalid_after_submission_no_replay",
                },
            )

        payload = api_resp.payload if isinstance(api_resp.payload, dict) else {}
        outcome, reference_missing = classify_mutation_response(payload, status_code=api_resp.status_code)
        return ExecutionResult(
            response=api_resp,
            meta={
                "executor": "real",
                "broker_outcome": outcome,
                "submission_phase": "mutation_http_call",
                "submission_attempts": 1,
                "exception_type": "",
                "reconciliation_required": outcome == "UNKNOWN",
                "broker_reference_missing": reference_missing,
            },
        )
