"""Phase 1 Step 5B Safety Fix -- closes CRITICAL/HIGH gaps found by Codex's
independent review of the original Step 5B implementation:
1. core phase invariant (NOT_SENT never possible once submission begins)
2. ORDER_SUBMIT fallback mutation identity
3. broker response contradiction handling
4. CANCEL UNKNOWN propagation
5. UNKNOWN quarantine persistence semantics (fail-closed read, no silent
   write-failure -> NOT_SENT downgrade)
6. forced liquidation is fail-closed under quarantine too
"""
from __future__ import annotations

import json
import os
import threading

import pytest

from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor
from libs.execution.guards.broker_mutation import classify_mutation_response, is_mutation_api_id
from graphs.nodes.execute_from_packet import (
    _acquire_quarantine_lock,
    _evaluate_unknown_quarantine_guard,
    _prepare_request,
    _quarantine_symbol_for_unknown_outcome,
    _read_unknown_quarantine,
    _unknown_quarantine_path,
    execute_from_packet,
)


class _RecordingHttp:
    def __init__(self, *, raise_exc: Exception | None = None, status_code: int = 200, text: str = "{}"):
        self.calls: list[dict] = []
        self.raise_exc = raise_exc
        self.status_code = status_code
        self.text = text

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False, retry_override=None):
        self.calls.append({"method": method, "path": path, "retry_override": retry_override})
        if self.raise_exc is not None:
            raise self.raise_exc
        from libs.core.http_client import HttpResponse

        return f"https://example.test{path}", HttpResponse(status_code=self.status_code, headers={}, text=self.text)


def _mutation_req(*, api_id="kt10000", symbol="005930") -> PreparedRequest:
    return PreparedRequest(api_id=api_id, method="POST", path="/api/dostk/ordr", headers={}, query={}, body={"stk_cd": symbol, "ord_qty": "10", "ord_uv": "1000"})


def _make_executor(http, *, execution_enabled="true"):
    os.environ["EXECUTION_ENABLED"] = execution_enabled
    return RealExecutor(http=http)


def _api_catalog_path(tmp_path, extra_line: str = "") -> str:
    p = tmp_path / "catalog.jsonl"
    lines = [json.dumps({"api_id": "kt10000", "method": "POST", "path": "/api/dostk/ordr", "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]}})]
    if extra_line:
        lines.append(extra_line)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _base_state(tmp_path, *, executor, action="BUY", symbol="005930", api_id="ORDER_SUBMIT", catalog_path=None):
    return {
        "decision_packet": {
            "intent": {"action": action, "symbol": symbol, "qty": 10, "price": 1000, "order_type": "limit", "order_api_id": api_id},
        },
        "executor": executor,
        "catalog_path": catalog_path or _api_catalog_path(tmp_path),
        "unknown_quarantine_guard_path": str(tmp_path / "quarantine.json"),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
    }


class _RaisingExecutor:
    """Simulates a network exception surfacing from executor.execute()
    itself (e.g. a non-RealExecutor implementation), as opposed to
    RealExecutor's own mutation path (which never raises post-submission)."""

    def __init__(self, exc):
        self.exc = exc

    def execute(self, req, *, auth_token=None):
        raise self.exc


class _UnknownExecutor:
    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        return ExecutionResult(
            response=ApiResponse(status_code=0, ok=False, payload={}, error_code=None, error_message="timeout", raw_text=""),
            meta={"executor": "real", "broker_outcome": "UNKNOWN", "submission_phase": "mutation_http_call", "submission_attempts": 1, "exception_type": "TimeoutError", "reconciliation_required": True},
        )


# --- 2. ORDER_SUBMIT fallback mutation identity -------------------------------

def test_order_submit_fallback_after_catalog_lookup_failure_still_carries_mutation_api_id():
    class _EmptyCatalog:
        def get(self, api_id):
            return None

    req = _prepare_request({"action": "BUY", "symbol": "005930", "qty": 1, "api_id": "ORDER_SUBMIT"}, _EmptyCatalog())
    assert req.api_id == "ORDER_SUBMIT"
    assert is_mutation_api_id(req.api_id)


def test_order_submit_fallback_gets_transport_attempt_one(monkeypatch):
    class _EmptyCatalog:
        def get(self, api_id):
            return None

    req = _prepare_request({"action": "SELL", "symbol": "005930", "qty": 1, "api_id": "ORDER_SUBMIT"}, _EmptyCatalog())
    http = _RecordingHttp(raise_exc=TimeoutError("boom"))
    ex = _make_executor(http)
    result = ex.execute(req)
    assert len(http.calls) == 1
    assert http.calls[0]["retry_override"] == 0
    assert result.meta["broker_outcome"] == "UNKNOWN"


def test_order_submit_catalog_lookup_success_also_gets_transport_attempt_one(tmp_path):
    from libs.catalog.api_catalog import ApiCatalog

    catalog = ApiCatalog.load(_api_catalog_path(tmp_path))
    req = _prepare_request({"action": "BUY", "symbol": "005930", "qty": 1, "price": 1000, "order_type": "limit", "api_id": "ORDER_SUBMIT"}, catalog)
    assert req.api_id == "kt10000"
    assert is_mutation_api_id(req.api_id)

    http = _RecordingHttp(raise_exc=ConnectionError("reset"))
    ex = _make_executor(http)
    result = ex.execute(req)
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "UNKNOWN"


# --- 3. Broker response contradiction handling --------------------------------

def test_http_500_with_success_broker_code_is_unknown():
    outcome, _ = classify_mutation_response({"return_code": 0, "return_msg": "ok"}, status_code=500)
    assert outcome == "UNKNOWN"


def test_http_200_with_conflicting_business_codes_is_unknown():
    outcome, _ = classify_mutation_response({"msg_cd": "0000", "return_code": 20}, status_code=200)
    assert outcome == "UNKNOWN"


def test_http_200_with_no_business_signal_is_unknown():
    outcome, _ = classify_mutation_response({}, status_code=200)
    assert outcome == "UNKNOWN"


def test_http_2xx_with_all_signals_agreeing_success_is_accepted():
    outcome, ref_missing = classify_mutation_response({"msg_cd": "0", "return_code": "0"}, status_code=200)
    assert outcome == "ACCEPTED"
    assert ref_missing is True


def test_http_missing_status_does_not_block_accept_when_business_code_present():
    """status_code=None (unknown) must not itself veto an explicit success code."""
    outcome, _ = classify_mutation_response({"return_code": 0}, status_code=None)
    assert outcome == "ACCEPTED"


def test_all_signals_agree_reject_is_rejected_regardless_of_http_status():
    outcome, _ = classify_mutation_response({"msg_cd": "20", "return_code": "20"}, status_code=500)
    assert outcome == "REJECTED"


def test_real_executor_end_to_end_500_with_success_code_is_unknown():
    http = _RecordingHttp(status_code=500, text=json.dumps({"return_code": 0, "return_msg": "ok"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "UNKNOWN"


def test_real_executor_end_to_end_conflicting_codes_is_unknown():
    http = _RecordingHttp(status_code=200, text=json.dumps({"msg_cd": "0000", "return_code": 20}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "UNKNOWN"


# --- 1. Core phase invariant ---------------------------------------------------

def test_preflight_failure_before_submission_is_still_not_sent(tmp_path, monkeypatch):
    # execute_from_packet re-raises after recording state["execution"] (this
    # is existing, unchanged behavior, not something this Step alters) --
    # so the outcome is checked on `state`, not on a normal return value.
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    state = _base_state(tmp_path, executor=RealExecutor(http=_RecordingHttp()))
    with pytest.raises(ExecutionDisabledError):
        execute_from_packet(state)
    assert state["execution"]["broker_outcome"] == "NOT_SENT"


def test_exception_after_valid_outcome_determined_does_not_downgrade_to_not_sent(monkeypatch, tmp_path):
    """A downstream failure (quarantine persistence in this case) after
    _normalize_execution already produced a valid outcome must not be
    reported as NOT_SENT -- the mutation was, in fact, submitted."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_UnknownExecutor())

    def _boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr("graphs.nodes.execute_from_packet._acquire_quarantine_lock", _boom)
    # The quarantine-persistence failure propagates (existing exception
    # handling re-raises after recording state["execution"]) -- what matters
    # for this test is that the ALREADY-DETERMINED UNKNOWN outcome survives
    # that failure instead of being overwritten to NOT_SENT.
    with pytest.raises(RuntimeError):
        execute_from_packet(state)
    assert state["execution"]["broker_outcome"] == "UNKNOWN"
    assert state["execution"]["ok"] is False
    assert state["execution"].get("post_submission_error") == "disk full"


def test_non_execution_disabled_exception_after_dispatch_is_unknown_not_not_sent(monkeypatch, tmp_path):
    """An executor implementation other than RealExecutor that raises a
    plain exception (not ExecutionDisabledError) *during* execute() must be
    treated as UNKNOWN, not NOT_SENT -- we cannot prove nothing was sent."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_RaisingExecutor(RuntimeError("mystery failure mid-dispatch")))
    with pytest.raises(RuntimeError):
        execute_from_packet(state)
    assert state["execution"]["broker_outcome"] == "UNKNOWN"
    assert state["execution"]["reconciliation_required"] is True


def test_execution_disabled_error_from_executor_is_not_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_RaisingExecutor(ExecutionDisabledError("[EXECUTION_DISABLED] no")))
    with pytest.raises(ExecutionDisabledError):
        execute_from_packet(state)
    assert state["execution"]["broker_outcome"] == "NOT_SENT"


# --- 5. Quarantine persistence semantics ---------------------------------------

def test_malformed_quarantine_state_blocks_mutation_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    qpath = tmp_path / "quarantine.json"
    qpath.write_text("{not valid json", encoding="utf-8")
    state = _base_state(tmp_path, executor=_UnknownExecutor())
    state["unknown_quarantine_guard_path"] = str(qpath)
    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "quarantine_store_unreadable_fail_closed"


def test_missing_quarantine_file_does_not_fail_closed(tmp_path):
    """Cold start (file never created yet) must be treated as an empty,
    readable store -- not a corruption."""
    qpath = tmp_path / "does_not_exist.json"
    data = _read_unknown_quarantine(qpath)
    assert data.get("_read_ok") is True
    assert data.get("symbols") == {}
    allowed, reason, details = _evaluate_unknown_quarantine_guard({"unknown_quarantine_guard_path": str(qpath)}, {"action": "BUY", "symbol": "005930"})
    assert allowed is True


def test_quarantine_write_failure_does_not_raise(tmp_path, monkeypatch):
    """A lock-acquire timeout during persistence must be swallowed -- never
    propagate and be mistaken for "mutation never sent"."""
    qpath = tmp_path / "quarantine.json"
    monkeypatch.setattr(
        "graphs.nodes.execute_from_packet._acquire_quarantine_lock",
        lambda *a, **k: (_ for _ in ()).throw(__import__("graphs.nodes.execute_from_packet", fromlist=["_QuarantineLockTimeout"])._QuarantineLockTimeout("timeout")),
    )
    ok = _quarantine_symbol_for_unknown_outcome({"unknown_quarantine_guard_path": str(qpath)}, {"action": "BUY", "symbol": "005930"}, {"exception_type": "TimeoutError"})
    assert ok is False
    assert not qpath.exists()


def test_quarantine_concurrent_writers_do_not_corrupt_or_lose_updates(tmp_path):
    qpath = tmp_path / "quarantine.json"
    symbols = [f"{100000 + i}" for i in range(8)]
    errors = []

    def _write(sym):
        try:
            _quarantine_symbol_for_unknown_outcome(
                {"unknown_quarantine_guard_path": str(qpath)},
                {"action": "BUY", "symbol": sym},
                {"exception_type": "TimeoutError"},
            )
        except Exception as exc:  # pragma: no cover - fail via errors list instead
            errors.append(exc)

    threads = [threading.Thread(target=_write, args=(s,)) for s in symbols]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    data = _read_unknown_quarantine(qpath)
    assert data.get("_read_ok") is True
    assert set(data.get("symbols", {}).keys()) == set(symbols)  # no lost updates


# --- 4. CANCEL UNKNOWN propagation ----------------------------------------------

def test_cancel_timeout_is_unknown_and_quarantines_symbol(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_UnknownExecutor(), action="CANCEL", api_id="kt10003")
    state["decision_packet"]["intent"]["orig_ord_no"] = "S000123"
    out = execute_from_packet(state)
    assert out["execution"]["broker_outcome"] == "UNKNOWN"

    # Next tick: any mutation on the same symbol is blocked by quarantine.
    state2 = _base_state(tmp_path, executor=_UnknownExecutor())
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"


# --- 6. Forced liquidation is fail-closed under quarantine ----------------------

def test_forced_liquidation_sell_is_blocked_when_symbol_quarantined(tmp_path):
    qpath = tmp_path / "quarantine.json"
    _quarantine_symbol_for_unknown_outcome(
        {"unknown_quarantine_guard_path": str(qpath)},
        {"action": "BUY", "symbol": "005930"},
        {"exception_type": "TimeoutError"},
    )
    # A forced-liquidation SELL is, from this guard's point of view, just
    # another SELL on the same symbol -- must be blocked the same way.
    allowed, reason, details = _evaluate_unknown_quarantine_guard(
        {"unknown_quarantine_guard_path": str(qpath)}, {"action": "SELL", "symbol": "005930", "meta": {"forced_closeout": True}}
    )
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"
    assert details["quarantined"] is True
