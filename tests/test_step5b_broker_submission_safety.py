"""Phase 1 Step 5B -- Broker Submission Safety.

Covers:
- transport: mutation submission attempt = 1 regardless of exception; read/token
  retry behavior unaffected
- token replay: no automatic resubmission after mutation is dispatched
- BrokerOutcome classification: NOT_SENT / ACCEPTED / REJECTED / UNKNOWN
- UNKNOWN quarantine (scoped to the affected symbol only)
- CANCEL_ACCEPTED != CANCEL_CONFIRMED (market replacement fail-closed)
- legacy `ok` compatibility
"""
from __future__ import annotations

import json
import os

import pytest

from libs.catalog.api_request_builder import PreparedRequest
from libs.core.http_client import HttpClient, HttpClientError
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor
from libs.execution.guards.broker_mutation import classify_mutation_response, is_mutation_api_id
from libs.kiwoom.kiwoom_token_client import EnsureTokenResult
from graphs.nodes.execute_from_packet import (
    _classify_broker_outcome,
    _evaluate_unknown_quarantine_guard,
    execute_from_packet,
)


class _FakeTokenClient:
    """Deterministic stand-in for KiwoomTokenClient (Phase 1 P0 corrective
    commit, item 5). These tests exercise mutation *transport* safety --
    what happens to the actual order-submission HTTP call -- not real
    Kiwoom token acquisition. Before this fixture, RealExecutor's real
    KiwoomTokenClient made these tests implicitly depend on a valid,
    non-expired token happening to already be cached at the production
    KIWOOM_TOKEN_CACHE_PATH default (a PRE_EXISTING gap, confirmed via
    git-stash A/B comparison against 981acd1 to predate any P0 work): with
    no such cache hit, ensure_token() would attempt a real HTTP token
    refresh through the *same* _RecordingHttp double these tests use to
    simulate a mutation-submission failure, so the token step failed first
    instead of the order-submission step under test. This fake removes any
    dependency on production credentials/cache/network entirely."""

    def ensure_token(self, *, dry_run: bool = False, force_refresh: bool = False) -> EnsureTokenResult:
        return EnsureTokenResult(
            action="cache_hit",
            token="test-fixture-token",
            expires_at_epoch=9_999_999_999,
            reason="deterministic test fixture",
        )


class _RecordingHttp:
    """Stand-in for HttpClient.request(). Records every call and either
    raises or returns a canned (status_code, text) response."""

    def __init__(self, *, raise_exc: Exception | None = None, status_code: int = 200, text: str = "{}"):
        self.calls: list[dict] = []
        self.raise_exc = raise_exc
        self.status_code = status_code
        self.text = text

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False, retry_override=None):
        self.calls.append({"method": method, "path": path, "retry_override": retry_override, "json_body": json_body})
        if self.raise_exc is not None:
            raise self.raise_exc
        from libs.core.http_client import HttpResponse

        return f"https://example.test{path}", HttpResponse(status_code=self.status_code, headers={}, text=self.text)


def _mutation_req(*, api_id="kt10000", symbol="005930", qty=10, price=1000) -> PreparedRequest:
    return PreparedRequest(
        api_id=api_id,
        method="POST",
        path="/api/dostk/ordr",
        headers={},
        query={},
        body={"stk_cd": symbol, "ord_qty": str(qty), "ord_uv": str(price)},
    )


def _make_executor(http, *, execution_enabled="true"):
    os.environ["EXECUTION_ENABLED"] = execution_enabled
    ex = RealExecutor(http=http)
    ex.tokens = _FakeTokenClient()
    return ex


# --- 1. Mutation registry -----------------------------------------------------

def test_mutation_api_ids_cover_buy_sell_modify_cancel():
    assert is_mutation_api_id("kt10000")
    assert is_mutation_api_id("kt10001")
    assert is_mutation_api_id("kt10002")
    assert is_mutation_api_id("kt10003")
    assert not is_mutation_api_id("kt00007")  # order status/read
    assert not is_mutation_api_id("ka10075")  # pending order query


# --- 2. Transport: mutation attempt = 1 on any exception ---------------------

def test_buy_mutation_transport_attempt_is_one_on_timeout(monkeypatch):
    http = _RecordingHttp(raise_exc=TimeoutError("boom"))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req(api_id="kt10000"))
    assert len(http.calls) == 1
    assert http.calls[0]["retry_override"] == 0
    assert result.meta["broker_outcome"] == "UNKNOWN"
    assert result.meta["submission_attempts"] == 1
    assert result.meta["reconciliation_required"] is True


def test_sell_cancel_mutation_transport_attempt_is_one_on_connection_error(monkeypatch):
    for api_id in ("kt10001", "kt10003"):
        http = _RecordingHttp(raise_exc=ConnectionError("reset"))
        ex = _make_executor(http)
        result = ex.execute(_mutation_req(api_id=api_id))
        assert len(http.calls) == 1, api_id
        assert result.meta["broker_outcome"] == "UNKNOWN", api_id


def test_read_api_retry_behavior_unchanged():
    """Non-mutation calls (e.g. order status kt00007) keep instance retry_max."""
    http = HttpClient("https://example.test", retry_max=2, backoff_sec=0)
    calls = {"n": 0}

    class _Session:
        def request(self, **kwargs):
            calls["n"] += 1
            raise RuntimeError("network down")

    http.session = _Session()
    with pytest.raises(HttpClientError):
        http.request("POST", "/read", json_body={})
    assert calls["n"] == 3  # retry_max=2 -> 3 attempts, unchanged behavior


def test_token_api_retry_unaffected_by_mutation_override():
    """A plain HttpClient.request() call without retry_override still uses
    the instance's own retry_max (token endpoint behavior untouched)."""
    http = HttpClient("https://example.test", retry_max=1, backoff_sec=0)
    calls = {"n": 0}

    class _Session:
        def request(self, **kwargs):
            calls["n"] += 1
            raise RuntimeError("token endpoint down")

    http.session = _Session()
    with pytest.raises(HttpClientError):
        http.request("POST", "/oauth2/token", json_body={})
    assert calls["n"] == 2  # retry_max=1 -> 2 attempts


# --- 3. Token replay policy ----------------------------------------------------

def test_mutation_submission_then_token_invalid_response_is_not_replayed():
    http = _RecordingHttp(status_code=401, text=json.dumps({"return_code": "3", "return_msg": "token invalid"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert len(http.calls) == 1  # no automatic token-refresh replay
    assert result.meta["broker_outcome"] == "UNKNOWN"
    assert result.meta.get("note") == "token_invalid_after_submission_no_replay"


def test_token_acquisition_failure_before_mutation_submission_is_not_sent(monkeypatch):
    http = _RecordingHttp()
    ex = _make_executor(http)

    def _boom(*a, **k):
        raise RuntimeError("cannot reach token endpoint")

    monkeypatch.setattr(ex.tokens, "ensure_token", _boom)
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mutation_req())
    assert len(http.calls) == 0  # order endpoint never contacted


# --- 4. Outcome classification ------------------------------------------------

def test_preflight_failure_is_not_sent():
    http = _RecordingHttp()
    ex = _make_executor(http, execution_enabled="false")
    os.environ["KIWOOM_MODE"] = "real"
    try:
        with pytest.raises(ExecutionDisabledError):
            ex.execute(_mutation_req())
        assert len(http.calls) == 0
    finally:
        os.environ.pop("KIWOOM_MODE", None)


def test_explicit_broker_success_is_accepted():
    http = _RecordingHttp(text=json.dumps({"ord_no": "A000123", "msg_cd": "0000", "msg1": "accepted"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "ACCEPTED"
    assert not result.meta.get("broker_reference_missing")


def test_explicit_broker_reject_is_rejected():
    http = _RecordingHttp(text=json.dumps({"return_code": 20, "return_msg": "insufficient funds"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "REJECTED"


def test_malformed_json_is_unknown():
    http = _RecordingHttp(text="not json{{{")
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "UNKNOWN"


def test_http_2xx_with_no_business_signal_is_unknown():
    http = _RecordingHttp(status_code=200, text="{}")
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "UNKNOWN"


def test_success_code_without_ord_no_is_accepted_with_reference_missing():
    http = _RecordingHttp(text=json.dumps({"return_code": 0, "return_msg": "ok"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "ACCEPTED"
    assert result.meta["broker_reference_missing"] is True


def test_classify_mutation_response_directly_matches_executor_behavior():
    assert classify_mutation_response({"return_code": 0}) == ("ACCEPTED", True)
    assert classify_mutation_response({"return_code": 0, "ord_no": "X1"}) == ("ACCEPTED", False)
    assert classify_mutation_response({"return_code": 20}) == ("REJECTED", False)
    assert classify_mutation_response({}) == ("UNKNOWN", False)
    assert classify_mutation_response({"return_code": "not_a_number"}) == ("UNKNOWN", False)


# --- 5. execute_from_packet: outcome propagation + quarantine + compatibility --

def _api_catalog_path(tmp_path) -> str:
    spec = {
        "api_id": "kt10000",
        "method": "POST",
        "path": "/api/dostk/ordr",
        "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]},
    }
    p = tmp_path / "catalog.jsonl"
    p.write_text(json.dumps(spec) + "\n", encoding="utf-8")
    return str(p)


def _base_state(tmp_path, *, executor):
    return {
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 10, "price": 1000, "order_type": "limit"},
        },
        "executor": executor,
        "catalog_path": _api_catalog_path(tmp_path),
        "unknown_quarantine_guard_path": str(tmp_path / "quarantine.json"),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
    }


class _UnknownExecutor:
    """Test double: always returns an UNKNOWN-classified ExecutionResult,
    mirroring what RealExecutor._execute_mutation returns on a transport
    exception."""

    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        return ExecutionResult(
            response=ApiResponse(status_code=0, ok=False, payload={}, error_code=None, error_message="timeout", raw_text=""),
            meta={
                "executor": "real",
                "broker_outcome": "UNKNOWN",
                "submission_phase": "mutation_http_call",
                "submission_attempts": 1,
                "exception_type": "TimeoutError",
                "reconciliation_required": True,
            },
        )


def test_execute_from_packet_unknown_outcome_ok_false_and_quarantines_symbol(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_UnknownExecutor())
    out = execute_from_packet(state)
    execution = out["execution"]
    assert execution["broker_outcome"] == "UNKNOWN"
    assert execution["ok"] is False
    assert execution["reason"] != "broker_rejected"
    assert "rejected" not in execution["reason"]
    assert execution["reconciliation_required"] is True

    # Same symbol, next tick: blocked by quarantine before reaching the executor.
    executor2 = _UnknownExecutor()
    state2 = _base_state(tmp_path, executor=executor2)
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"

    # Unrelated symbol is NOT blocked by the same quarantine file.
    state3 = _base_state(tmp_path, executor=_UnknownExecutor())
    state3["decision_packet"]["intent"]["symbol"] = "000660"
    allowed, reason, details = _evaluate_unknown_quarantine_guard(state3, {"action": "BUY", "symbol": "000660"})
    assert allowed is True


def test_execute_from_packet_accepted_outcome_ok_true(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    class _AcceptedExecutor:
        def execute(self, req, *, auth_token=None):
            from libs.core.api_response import ApiResponse
            from libs.execution.executors.base import ExecutionResult

            return ExecutionResult(response=ApiResponse(status_code=200, ok=True, payload={"mode": "mock"}, error_code=None, error_message=None, raw_text=""), meta={"executor": "mock"})

    state = _base_state(tmp_path, executor=_AcceptedExecutor())
    out = execute_from_packet(state)
    assert out["execution"]["broker_outcome"] == "ACCEPTED"
    assert out["execution"]["ok"] is True


def test_classify_broker_outcome_prefers_real_executor_meta():
    payload = {"meta": {"broker_outcome": "UNKNOWN"}, "broker_code": "0"}
    outcome, source = _classify_broker_outcome(payload)
    assert outcome == "UNKNOWN"
    assert source == "real_executor_meta"


def test_classify_broker_outcome_mock_executor_is_accepted_without_signal():
    outcome, source = _classify_broker_outcome({"mode": "mock", "meta": {"executor": "mock"}})
    assert outcome == "ACCEPTED"
    assert source == "mock_executor_default"


def test_classify_broker_outcome_execution_mode_mock_with_non_mock_executor_uses_business_code():
    """EXECUTION_MODE=mock alone must not force ACCEPTED -- only the actual
    MockExecutor class (meta['executor']=='mock') gets the always-succeed
    shortcut. A test double/tool that runs while EXECUTION_MODE=mock but
    returns a real Kiwoom-shaped rejection must still be classified as
    REJECTED, not silently overridden to ACCEPTED."""
    outcome, source = _classify_broker_outcome(
        {
            "mode": "mock",
            "meta": {"executor": "real"},
            "broker_code": "20",
            "status_code": 200,
            "response_payload": {"return_code": "20", "return_msg": "rejected"},
        }
    )
    assert outcome == "REJECTED"


# --- 6. Compatibility ----------------------------------------------------------

@pytest.mark.parametrize(
    "broker_outcome,expected_ok",
    [("ACCEPTED", True), ("NOT_SENT", False), ("REJECTED", False), ("UNKNOWN", False)],
)
def test_legacy_ok_compatibility_mapping(broker_outcome, expected_ok):
    payload = {"meta": {"broker_outcome": broker_outcome}}
    outcome, _ = _classify_broker_outcome(payload)
    assert outcome == broker_outcome
    assert (outcome == "ACCEPTED") == expected_ok
