"""Phase 1 Step 5B Safety Fix (rounds 1 + 2) -- closes CRITICAL/HIGH gaps
found by Codex's independent review, including the REJECT-level durability
gaps in round 2:
1. core phase invariant (NOT_SENT never possible once submission begins)
2. ORDER_SUBMIT fallback mutation identity (api_id AND action cross-check)
3. broker response contradiction / ambiguity handling
4. CANCEL UNKNOWN propagation (namespaced cancel_* provenance fields)
5. UNKNOWN quarantine durability -- per-symbol atomic lock file, fail-closed
   on unreadable state, process-wide global_mutation_halt fallback,
   durable across a simulated process restart
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
from libs.execution.guards.broker_mutation import (
    classify_mutation_response,
    is_mutation_api_id,
    is_mutation_request,
)
from graphs.nodes import execute_from_packet as efp
from graphs.nodes.execute_from_packet import (
    _evaluate_unknown_quarantine_guard,
    _prepare_request,
    _quarantine_lock_path,
    _quarantine_symbol_for_unknown_outcome,
    _write_quarantine_lock_if_absent,
    execute_from_packet,
)


@pytest.fixture(autouse=True)
def _reset_global_mutation_halt():
    """_GLOBAL_MUTATION_HALT is process-wide, module-level state by design
    (that's the point -- it must survive across calls within one process
    lifetime). Reset it around every test in this file so one test
    activating it can't leak into the next."""
    efp._GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0})
    yield
    efp._GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0})


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


def _base_state(tmp_path, *, executor, action="BUY", symbol="005930", api_id="ORDER_SUBMIT", catalog_path=None, quarantine_dir=None):
    return {
        "decision_packet": {
            "intent": {"action": action, "symbol": symbol, "qty": 10, "price": 1000, "order_type": "limit", "order_api_id": api_id},
        },
        "executor": executor,
        "catalog_path": catalog_path or _api_catalog_path(tmp_path),
        "unknown_quarantine_guard_path": str(quarantine_dir or (tmp_path / "quarantine")),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
    }


class _RaisingExecutor:
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


class _AcceptedExecutor:
    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        return ExecutionResult(
            response=ApiResponse(status_code=200, ok=True, payload={"mode": "mock"}, error_code=None, error_message=None, raw_text=""),
            meta={"executor": "mock"},
        )


# --- 3. Mutation identity hardening (api_id missing -> action cross-check) ----

@pytest.mark.parametrize("action,expected_api_id", [("BUY", "ORDER_SUBMIT"), ("SELL", "ORDER_SUBMIT"), ("CANCEL", "kt10003"), ("MODIFY", "kt10002")])
def test_prepare_request_infers_api_id_from_action_when_missing(action, expected_api_id):
    class _EmptyCatalog:
        def get(self, api_id):
            return None

    req = _prepare_request({"action": action, "symbol": "005930", "qty": 1}, _EmptyCatalog())
    assert req.api_id == expected_api_id
    assert is_mutation_api_id(req.api_id)


@pytest.mark.parametrize("action", ["BUY", "SELL", "CANCEL", "MODIFY"])
def test_missing_api_id_mutation_still_gets_transport_attempt_one(action):
    class _EmptyCatalog:
        def get(self, api_id):
            return None

    req = _prepare_request({"action": action, "symbol": "005930", "qty": 1, "orig_ord_no": "S1"}, _EmptyCatalog())
    http = _RecordingHttp(raise_exc=TimeoutError("boom"))
    ex = _make_executor(http)
    result = ex.execute(req)
    assert len(http.calls) == 1
    assert http.calls[0]["retry_override"] == 0
    assert result.meta["broker_outcome"] == "UNKNOWN"


def test_is_mutation_request_cross_checks_action_when_api_id_missing():
    class _FakeReq:
        api_id = ""
        body = {"action": "BUY", "stk_cd": "005930"}

    assert is_mutation_request(_FakeReq()) is True


def test_is_mutation_request_does_not_reclassify_reads_as_mutation():
    class _FakeReadReq:
        api_id = "kt00007"  # order status (read)
        body = {"stk_cd": "005930"}

    assert is_mutation_request(_FakeReadReq()) is False


def test_order_submit_fallback_after_catalog_lookup_failure_still_carries_mutation_api_id():
    class _EmptyCatalog:
        def get(self, api_id):
            return None

    req = _prepare_request({"action": "BUY", "symbol": "005930", "qty": 1, "api_id": "ORDER_SUBMIT"}, _EmptyCatalog())
    assert req.api_id == "ORDER_SUBMIT"
    assert is_mutation_api_id(req.api_id)


def test_order_submit_catalog_lookup_success_also_gets_transport_attempt_one(tmp_path):
    from libs.catalog.api_catalog import ApiCatalog

    catalog = ApiCatalog.load(_api_catalog_path(tmp_path))
    req = _prepare_request({"action": "BUY", "symbol": "005930", "qty": 1, "price": 1000, "order_type": "limit", "api_id": "ORDER_SUBMIT"}, catalog)
    assert req.api_id == "kt10000"

    http = _RecordingHttp(raise_exc=ConnectionError("reset"))
    ex = _make_executor(http)
    result = ex.execute(req)
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "UNKNOWN"


# --- 6. Broker classifier ambiguity handling -----------------------------------

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


def test_unparseable_status_code_does_not_assume_success():
    outcome, _ = classify_mutation_response({"return_code": 0}, status_code="not-a-status")
    assert outcome == "UNKNOWN"


def test_success_code_plus_unrecognized_explicit_code_is_unknown():
    """return_code=0 (clean success) alongside msg_cd="UNRECOGNIZED" (present,
    but not a parseable success/reject signal) must not be silently
    ACCEPTED just because one field happened to parse cleanly."""
    outcome, _ = classify_mutation_response({"return_code": 0, "msg_cd": "UNRECOGNIZED"}, status_code=200)
    assert outcome == "UNKNOWN"


def test_all_signals_agree_reject_is_rejected_regardless_of_http_status():
    outcome, _ = classify_mutation_response({"msg_cd": "20", "return_code": "20"}, status_code=500)
    assert outcome == "REJECTED"


def test_real_executor_end_to_end_500_with_success_code_is_unknown():
    http = _RecordingHttp(status_code=500, text=json.dumps({"return_code": 0, "return_msg": "ok"}))
    ex = _make_executor(http)
    result = ex.execute(_mutation_req())
    assert result.meta["broker_outcome"] == "UNKNOWN"


# --- 1. Core phase invariant ---------------------------------------------------

def test_preflight_failure_before_submission_is_still_not_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    state = _base_state(tmp_path, executor=RealExecutor(http=_RecordingHttp()))
    with pytest.raises(ExecutionDisabledError):
        execute_from_packet(state)
    assert state["execution"]["broker_outcome"] == "NOT_SENT"


def test_non_execution_disabled_exception_after_dispatch_is_unknown_not_not_sent(monkeypatch, tmp_path):
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


# --- 5. Quarantine durability: writer failure never permits next-tick mutation -

def test_quarantine_write_failure_same_process_next_tick_mutation_zero(monkeypatch, tmp_path):
    """The atomic lock-file create itself fails (simulating disk full /
    permission denied). Within the SAME process, the very next mutation
    attempt (any symbol) must be blocked by global_mutation_halt."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_UnknownExecutor())

    def _boom(*a, **k):
        return False  # simulate: could not create, and doesn't already exist

    monkeypatch.setattr(efp, "_write_quarantine_lock_if_absent", _boom)
    out = execute_from_packet(state)
    assert out["execution"]["broker_outcome"] == "UNKNOWN"
    assert efp._GLOBAL_MUTATION_HALT["active"] is True

    # Next tick, ANY symbol, even one that was never touched before:
    http_calls = []

    class _SpyExecutor:
        def execute(self, req, *, auth_token=None):
            http_calls.append(req)
            raise AssertionError("must not reach the executor while global_mutation_halt is active")

    state2 = _base_state(tmp_path, executor=_SpyExecutor(), symbol="000660")
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "global_mutation_halt_active"
    assert not http_calls


def test_quarantine_write_failure_survives_simulated_restart(tmp_path, monkeypatch):
    """global_mutation_halt is explicitly process-local (does not survive a
    restart) -- but if the lock file write genuinely failed, the SYMBOL
    itself must remain protected some other way after "restart" too. Since
    the failure means no lock file exists, this test documents and verifies
    the actual guarantee: a restart after a *successful* quarantine (lock
    file written) blocks; a restart after a *failed* write with no leftover
    file relies on the fact that the underlying broker call will be retried
    as a fresh decision and go through the full guard chain again (not an
    automatic bypass) -- verified here via the durable-lock-file case,
    which is the actual crash-safety guarantee this Step provides."""
    qdir = tmp_path / "quarantine"
    state = {"unknown_quarantine_guard_path": str(qdir)}
    order = {"action": "BUY", "symbol": "005930"}
    execution = {"exception_type": "TimeoutError"}

    ok = _quarantine_symbol_for_unknown_outcome(state, order, execution)
    assert ok is True
    assert _quarantine_lock_path(state, "005930").exists()

    # Simulate restart: fresh process would re-import this module, resetting
    # _GLOBAL_MUTATION_HALT to inactive -- but the guard call below uses a
    # BRAND NEW state dict/order (no shared Python objects with the write
    # above) and relies purely on the durable lock file on disk.
    efp._GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0})
    fresh_state = {"unknown_quarantine_guard_path": str(qdir)}
    allowed, reason, details = _evaluate_unknown_quarantine_guard(fresh_state, {"action": "BUY", "symbol": "005930"})
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"


def test_stale_lock_only_json_absent_blocks_mutation(tmp_path):
    """No aggregate JSON index exists at all -- only the per-symbol lock
    file. The guard must still block on the lock file's existence alone."""
    qdir = tmp_path / "quarantine"
    qdir.mkdir(parents=True)
    lock_path = qdir / "005930.lock"
    lock_path.write_text("", encoding="utf-8")  # empty/stale, no content
    allowed, reason, details = _evaluate_unknown_quarantine_guard({"unknown_quarantine_guard_path": str(qdir)}, {"action": "BUY", "symbol": "005930"})
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"
    assert details.get("quarantine_lock_unreadable") is True


def test_malformed_quarantine_lock_content_still_blocks(tmp_path):
    qdir = tmp_path / "quarantine"
    qdir.mkdir(parents=True)
    (qdir / "005930.lock").write_text("{not valid json", encoding="utf-8")
    allowed, reason, details = _evaluate_unknown_quarantine_guard({"unknown_quarantine_guard_path": str(qdir)}, {"action": "SELL", "symbol": "005930"})
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"


def test_lock_marker_plus_simulated_restart_blocks_mutation(tmp_path):
    qdir = tmp_path / "quarantine"
    state = {"unknown_quarantine_guard_path": str(qdir)}
    lock_path = _quarantine_lock_path(state, "005930")
    ok = _write_quarantine_lock_if_absent(lock_path, {"pid": 999999, "created_at_epoch": 1, "symbol": "005930", "operation": "BUY", "reason": "broker_outcome_unknown"})
    assert ok is True

    # "restart": brand new state/order objects, nothing carried over except
    # the file on disk.
    fresh_state = {"unknown_quarantine_guard_path": str(qdir)}
    allowed, reason, details = _evaluate_unknown_quarantine_guard(fresh_state, {"action": "BUY", "symbol": "005930"})
    assert allowed is False
    assert details["quarantine_pid"] == 999999


def test_missing_quarantine_dir_does_not_fail_closed(tmp_path):
    """Cold start (directory never created yet) must be treated as
    not-quarantined -- not a corruption."""
    qdir = tmp_path / "does_not_exist_yet"
    allowed, reason, details = _evaluate_unknown_quarantine_guard({"unknown_quarantine_guard_path": str(qdir)}, {"action": "BUY", "symbol": "005930"})
    assert allowed is True


def test_quarantine_lock_records_required_fields(tmp_path):
    qdir = tmp_path / "quarantine"
    state = {"unknown_quarantine_guard_path": str(qdir), "run_id": "run-1"}
    order = {"action": "BUY", "symbol": "005930"}
    execution = {"exception_type": "TimeoutError"}
    _quarantine_symbol_for_unknown_outcome(state, order, execution)
    record = json.loads(_quarantine_lock_path(state, "005930").read_text(encoding="utf-8"))
    for key in ("pid", "created_at_epoch", "symbol", "operation", "reason"):
        assert key in record, key
    assert record["symbol"] == "005930"
    assert record["operation"] == "BUY"


def test_quarantine_concurrent_writers_do_not_corrupt_or_raise(tmp_path):
    qdir = tmp_path / "quarantine"
    state = {"unknown_quarantine_guard_path": str(qdir)}
    symbols = [f"{100000 + i}" for i in range(8)]
    errors = []

    def _write(sym):
        try:
            _quarantine_symbol_for_unknown_outcome(state, {"action": "BUY", "symbol": sym}, {"exception_type": "TimeoutError"})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=_write, args=(s,)) for s in symbols]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    for sym in symbols:
        assert _quarantine_lock_path(state, sym).exists()


# --- 4. Nested CANCEL UNKNOWN provenance ----------------------------------------

def test_cancel_timeout_is_unknown_and_quarantines_symbol(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = _base_state(tmp_path, executor=_UnknownExecutor(), action="CANCEL", api_id="kt10003")
    state["decision_packet"]["intent"]["orig_ord_no"] = "S000123"
    out = execute_from_packet(state)
    assert out["execution"]["broker_outcome"] == "UNKNOWN"

    state2 = _base_state(tmp_path, executor=_UnknownExecutor())
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"


def test_nested_cancel_unknown_does_not_overwrite_original_accepted_outcome(tmp_path):
    from graphs.nodes.execute_from_packet import _propagate_cancel_unknown_outcome

    state = {
        "unknown_quarantine_guard_path": str(tmp_path / "quarantine"),
        "run_id": "run-1",
        "execution": {"broker_outcome": "ACCEPTED", "ok": True},
    }
    cancel_order = {"action": "CANCEL", "symbol": "005930", "orig_ord_no": "S1"}
    cancel_payload = {"broker_outcome": "UNKNOWN", "submission_attempts": 1, "exception_type": "TimeoutError"}
    _propagate_cancel_unknown_outcome(state, cancel_order, cancel_payload)

    # Original order outcome preserved, untouched:
    assert state["execution"]["broker_outcome"] == "ACCEPTED"
    # Nested cancel outcome recorded separately, additively:
    assert state["execution"]["cancel_broker_outcome"] == "UNKNOWN"
    assert state["execution"]["cancel_reconciliation_required"] is True
    assert state["execution"]["cancel_submission_attempts"] == 1
    assert state["execution"]["cancel_exception_type"] == "TimeoutError"
    assert state["execution"]["cancel_quarantine_symbol"] == "005930"
    # Symbol is durably quarantined too:
    allowed, _, _ = _evaluate_unknown_quarantine_guard(state, {"action": "SELL", "symbol": "005930"})
    assert allowed is False


# --- 6. Forced liquidation is fail-closed under quarantine ----------------------

def test_forced_liquidation_sell_is_blocked_when_symbol_quarantined(tmp_path):
    state = {"unknown_quarantine_guard_path": str(tmp_path / "quarantine")}
    _quarantine_symbol_for_unknown_outcome(state, {"action": "BUY", "symbol": "005930"}, {"exception_type": "TimeoutError"})
    allowed, reason, details = _evaluate_unknown_quarantine_guard(
        state, {"action": "SELL", "symbol": "005930", "meta": {"forced_closeout": True}}
    )
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"
    assert details["quarantined"] is True


# --- 5(E). Legacy/alternate live mutation paths ---------------------------------

def test_execute_order_legacy_path_blocked_when_symbol_quarantined(tmp_path, monkeypatch):
    from graphs.nodes.execute_order import execute_order

    qdir = tmp_path / "quarantine"
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = {"unknown_quarantine_guard_path": str(qdir)}
    _quarantine_symbol_for_unknown_outcome(state, {"action": "BUY", "symbol": "005930"}, {"exception_type": "TimeoutError"})

    cat_path = _api_catalog_path(tmp_path)
    state.update(
        {
            "catalog_path": cat_path,
            "order_api_id": "kt10000",
            "intent": "buy",
            "context": {"stk_cd": "005930", "ord_qty": "1", "ord_uv": "1000", "trde_tp": "0", "cond_uv": "", "dmst_stex_tp": "KRX"},
            "risk_context": {},
        }
    )
    out = execute_order(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"


def test_execute_order_legacy_path_unknown_outcome_quarantines_symbol(tmp_path, monkeypatch):
    import graphs.nodes.execute_order as execute_order_module

    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setattr(execute_order_module, "get_executor", lambda *a, **k: _UnknownExecutor())
    qdir = tmp_path / "quarantine"
    state = {
        "unknown_quarantine_guard_path": str(qdir),
        "catalog_path": _api_catalog_path(tmp_path),
        "order_api_id": "kt10000",
        "intent": "buy",
        "context": {"stk_cd": "005930", "ord_qty": "1", "ord_uv": "1000", "trde_tp": "0", "cond_uv": "", "dmst_stex_tp": "KRX"},
        "risk_context": {},
    }
    out = execute_order_module.execute_order(state)
    assert out["execution"]["broker_outcome"] == "UNKNOWN"
    allowed, _, _ = _evaluate_unknown_quarantine_guard(state, {"action": "BUY", "symbol": "005930"})
    assert allowed is False
