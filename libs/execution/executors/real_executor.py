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
    - Mutations (BUY/SELL/MODIFY/CANCEL -- see
      libs/execution/guards/broker_mutation.py::is_mutation_request) always
      require EXECUTION_ENABLED=true, regardless of KIWOOM_MODE.
    - Reads (auth, account query, open-order query, and any other
      non-mutation call) do NOT require EXECUTION_ENABLED -- see
      preflight_check()'s own docstring for the P1.3 read/write gate
      separation this implements.
    - If KIWOOM_MODE=real: additionally requires ALLOW_REAL_EXECUTION=true
      (and valid credentials/base URL) unconditionally, for both reads and
      writes -- this live-account-only guard is unchanged.
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
        """M24-5 / Paper Trading Execution Finalization (2026-09-17): explicit
        preflight check with stable denial reason codes.

        This is a pure guard evaluation step. It performs no token issuance and no HTTP calls.

        Canonical terminology (fixed going forward):
          Mock Execution  -- EXECUTION_MODE=mock -> MockExecutor is selected
                              instead of this class entirely; not reachable here.
          Paper Trading   -- EXECUTION_MODE=real, KIWOOM_MODE=mock -> this
                              class dispatches to Kiwoom's own sandbox server.
          Live Trading    -- EXECUTION_MODE=real, KIWOOM_MODE=real -> this
                              class dispatches to a real Kiwoom account.

        EXECUTION_ENABLED is a GLOBAL physical-dispatch switch, independent of
        KIWOOM_MODE -- checked FIRST, unconditionally FOR MUTATIONS. A prior
        version of this method only enforced it when KIWOOM_MODE == "real",
        which meant Paper Trading (KIWOOM_MODE=mock, a real HTTP call to
        Kiwoom's own sandbox) could dispatch with EXECUTION_ENABLED=false or
        even unset -- a real, live-reproduced bypass (see deploy/trading's
        own Real Docker Deployment audit). EXECUTION_ENABLED=false now blocks
        unconditionally, in both Paper and Live -- for mutations.

        Read/write gate separation (P1.3 Paper acceptance, 2026-09-30):
        EXECUTION_ENABLED governs broker WRITE (order-dispatch) authority
        only -- it must not also block a pure broker READ (auth, account
        query, open-order query). Every P1.3 Paper acceptance attempt with
        EXECUTION_ENABLED=false found broker reads (account balance,
        open-order snapshot) rejected the same as an order dispatch would
        be, via this exact check, even though nothing here ever reaches
        _execute_mutation() for those requests. Mutation status is
        determined by the same allowlist-based classifier
        (is_mutation_request(), libs/execution/guards/broker_mutation.py --
        MUTATION_API_IDS: kt10000/kt10001/kt10002/kt10003 = BUY/SELL/
        MODIFY/CANCEL only) already trusted elsewhere in this file for
        mutation-transport safety (retry_override=0, no-replay-on-
        token-invalid) -- reused here, not reinvented. A request this
        classifier cannot positively identify as a mutation is, by
        construction of that allowlist, never one of the four order-mutating
        API ids -- so this can only ever widen which READS are allowed
        through, never which WRITES are. When req is None (no specific
        request to classify -- an ambiguous, non-read-specific preflight
        probe), this fails closed exactly as before: treated as a mutation,
        still requiring EXECUTION_ENABLED=true.

        The ALLOW_REAL_EXECUTION / credential / base-URL checks below (the
        live-account-only guard, KIWOOM_MODE == "real" only) are
        deliberately UNCHANGED and still apply unconditionally, to both
        reads and writes -- this fix narrows only the EXECUTION_ENABLED
        check, per its own explicit scope.

        ALLOW_REAL_EXECUTION is a LIVE-ACCOUNT-ONLY additional switch, checked
        only when KIWOOM_MODE == "real" -- Paper Trading (KIWOOM_MODE=mock)
        needs only EXECUTION_ENABLED=true (mutations) or nothing (reads),
        never this second flag, since it never touches a real account
        regardless.
        """
        is_mutation = is_mutation_request(req) if req is not None else True
        enabled = self._env_flag_true("EXECUTION_ENABLED", "false")
        if not enabled and is_mutation:
            return self._deny(
                "EXECUTION_DISABLED",
                "Execution is disabled. Set EXECUTION_ENABLED=true to allow real calls.",
            )

        mode = (os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower()
        if mode == "real":
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
        # mode == "mock" (Paper Trading): EXECUTION_ENABLED=true already
        # confirmed above for mutations (reads reach here regardless of
        # EXECUTION_ENABLED); ALLOW_REAL_EXECUTION is deliberately NOT
        # required here -- it is a live-account-only guard.

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

        # Phase 1 Step 5B Fix 4 (HIGH1): the HTTP dispatch above already
        # happened -- exactly one physical submission occurred. Everything
        # from here on (response parsing, token-invalid check, mutation
        # classification) must not be allowed to raise a raw exception out
        # of this method: the caller cannot distinguish "nothing was sent"
        # from "something was sent but we failed to understand the reply",
        # and a naive caller-side retry after a raw exception would issue a
        # *second* physical dispatch for the same logical mutation, breaking
        # at-most-once. Convert any such exception into the same UNKNOWN
        # contract as a transport-level failure.
        try:
            assert resp is not None
            api_resp = ApiResponse.from_http(resp.status_code, resp.text)

            if self._is_invalid_token_response(api_resp):
                # The mutation has already been submitted once. Do not
                # refresh the token and replay the same mutation on a
                # guess -- treat the outcome as unknown and let
                # reconciliation resolve it.
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
        except Exception as exc:
            return ExecutionResult(
                response=ApiResponse(
                    status_code=getattr(resp, "status_code", 0) or 0,
                    ok=False,
                    payload={},
                    error_code=None,
                    error_message=str(exc),
                    raw_text=getattr(resp, "text", "") or "",
                ),
                meta={
                    "executor": "real",
                    "broker_outcome": "UNKNOWN",
                    "submission_phase": "mutation_response_parse",
                    "submission_attempts": 1,
                    "exception_type": type(exc).__name__,
                    "reconciliation_required": True,
                },
            )
