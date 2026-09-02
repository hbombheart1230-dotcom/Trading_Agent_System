"""Phase 1 Step 5B Fix 4 -- corrective implementation closing the 4 HIGH
findings from Codex's independent final audit that rejected Fix 3:

HIGH1: RealExecutor's mutation exception boundary only wrapped the HTTP
       transport call, not response parsing / classification -- a
       post-dispatch exception there escaped raw, and a caller-side retry
       on that raw exception could issue a second physical HTTP dispatch
       for the same logical mutation (Codex reproduced physical_http_calls
       = 2).
HIGH2: CompositeSkillRunner's shared quarantine only activated when
       RealExecutor returned a normal UNKNOWN-classified result -- HIGH1's
       raw exception meant no UNKNOWN was ever produced, so no quarantine.
HIGH3: Fix 3's nested-CANCEL `dispatched=True` flag only ever got set
       *after* executor.execute() returned; a real RealExecutor
       post-response parsing exception (HIGH1) meant execute() never
       returned normally in the old code, so `dispatched` stayed False and
       the CANCEL's own UNKNOWN outcome/quarantine was skipped.
HIGH4: symbol-quarantine-lock-write failure and global-mutation-halt
       marker write failure could both fail together (same filesystem),
       leaving no restart-survivable trace.

The fix for HIGH1 (extending RealExecutor's mutation exception boundary
through response parsing and classification, converting any exception in
that window into the existing BrokerOutcome.UNKNOWN contract instead of
raising) is the single source-of-truth change that closes HIGH2 and HIGH3
as a structural consequence -- see the comments on each test below for
exactly which invariant demonstrates that.
"""
from __future__ import annotations

import json

import pytest

from graphs.nodes import execute_from_packet as efp
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.http_client import HttpResponse
from libs.execution.executors.real_executor import RealExecutor
from libs.execution.guards import unknown_quarantine as uq
from libs.kiwoom.kiwoom_token_client import EnsureTokenResult
import libs.execution.executors.real_executor as real_executor_module


# --- shared fixtures / doubles -----------------------------------------------


def _clear_fallback_marker():
    try:
        (uq._GLOBAL_MUTATION_HALT_FALLBACK_DIR / uq._GLOBAL_MUTATION_HALT_MARKER_NAME).unlink()
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True)
def _reset_global_mutation_halt():
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_fallback_marker()
    yield
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_fallback_marker()


class _FakeTokenClient:
    """Same fixture used by tests/test_step5b_broker_submission_safety.py --
    removes any dependency on real Kiwoom token acquisition/network."""

    def ensure_token(self, *, dry_run: bool = False, force_refresh: bool = False) -> EnsureTokenResult:
        return EnsureTokenResult(action="cache_hit", token="test-fixture-token", expires_at_epoch=9_999_999_999, reason="fixture")


class _RecordingHttp:
    """Same double used by tests/test_step5b_broker_submission_safety.py --
    records every physical HTTP call and returns a canned response."""

    def __init__(self, *, status_code: int = 200, text: str = "{}"):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.text = text

    def request(self, method, path, *, headers=None, params=None, json_body=None, data=None, dry_run=False, retry_override=None):
        self.calls.append({"method": method, "path": path, "retry_override": retry_override, "json_body": json_body})
        return f"https://example.test{path}", HttpResponse(status_code=self.status_code, headers={}, text=self.text)


def _mutation_req(*, api_id="kt10000", symbol="005930", qty=10, price=1000) -> PreparedRequest:
    return PreparedRequest(
        api_id=api_id, method="POST", path="/api/dostk/ordr", headers={}, query={},
        body={"stk_cd": symbol, "ord_qty": str(qty), "ord_uv": str(price)},
    )


def _real_executor(http) -> RealExecutor:
    ex = RealExecutor(http=http)
    ex.tokens = _FakeTokenClient()
    return ex


def _api_catalog_path(tmp_path) -> str:
    p = tmp_path / "catalog.jsonl"
    p.write_text(
        json.dumps(
            {
                "api_id": "kt10000",
                "method": "POST",
                "path": "/api/dostk/ordr",
                "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return str(p)


def _base_state(tmp_path, *, executor, action="BUY", symbol="005930", quarantine_dir=None):
    return {
        "decision_packet": {
            "intent": {"action": action, "symbol": symbol, "qty": 10, "price": 1000, "order_type": "limit", "order_api_id": "ORDER_SUBMIT"},
        },
        "executor": executor,
        "catalog_path": _api_catalog_path(tmp_path),
        "unknown_quarantine_guard_path": str(quarantine_dir or (tmp_path / "quarantine")),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
    }


class _AcceptedExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        self.calls += 1
        return ExecutionResult(
            response=ApiResponse(status_code=200, ok=True, payload={"return_code": 0, "ord_no": "1"}, error_code=None, error_message=None, raw_text=""),
            meta={"executor": "mock"},
        )


# --- T1: RealExecutor post-response parser exception (HIGH1) ---------------


def test_t1_real_executor_post_response_parser_exception_returns_unknown_not_raise(monkeypatch):
    http = _RecordingHttp(text=json.dumps({"return_code": 0, "ord_no": "X1"}))
    ex = _real_executor(http)

    def _boom_classify(*a, **k):
        raise ValueError("malformed structure")

    monkeypatch.setattr(real_executor_module, "classify_mutation_response", _boom_classify)

    result = ex.execute(_mutation_req())  # must NOT raise
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "UNKNOWN"
    assert result.meta["submission_phase"] == "mutation_response_parse"
    assert result.meta["submission_attempts"] == 1
    assert result.meta["exception_type"] == "ValueError"
    assert result.meta["reconciliation_required"] is True


def test_t1_real_executor_token_invalid_check_exception_also_returns_unknown_not_raise(monkeypatch):
    """The token-invalid-response check also runs after dispatch, inside
    the same extended boundary -- confirm it is covered too, not just the
    classifier."""
    http = _RecordingHttp(text=json.dumps({"return_code": 0}))
    ex = _real_executor(http)

    def _boom_token_check(*a, **k):
        raise RuntimeError("malformed payload during token check")

    monkeypatch.setattr(ex, "_is_invalid_token_response", _boom_token_check)
    result = ex.execute(_mutation_req())
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "UNKNOWN"
    assert result.meta["submission_phase"] == "mutation_response_parse"


# --- T2: repeated runner mutation after a real post-response exception (HIGH2) --


def test_t2_runner_blocks_second_mutation_after_real_post_response_parse_exception(tmp_path, monkeypatch):
    """Structural consequence of the HIGH1 fix: CompositeSkillRunner's
    pre-existing (Fix 3) quarantine check/write around executor.execute()
    already handles broker_outcome==UNKNOWN correctly -- it just never
    triggered before because RealExecutor raised instead of returning
    UNKNOWN. No runner.py change was needed for this test to pass."""
    from libs.skills.runner import CompositeSkillRunner
    from libs.core.settings import Settings

    qdir = tmp_path / "quarantine"
    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(qdir))

    http = _RecordingHttp(text=json.dumps({"return_code": 0, "ord_no": "X1"}))
    real_ex = _real_executor(http)
    monkeypatch.setattr(real_executor_module, "classify_mutation_response", lambda *a, **k: (_ for _ in ()).throw(ValueError("malformed structure")))

    runner = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        catalog_path=_api_catalog_path(tmp_path),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    runner.executor = real_ex

    args = {"side": "buy", "symbol": "005930", "qty": 1, "order_type": "market", "price": None}
    result1 = runner.run(run_id="run-1", skill="order.place", args=args)
    assert result1.action == "ready"  # the skill call completes; UNKNOWN is a side effect, not a runner error
    assert len(http.calls) == 1
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    result2 = runner.run(run_id="run-2", skill="order.place", args=args)
    assert result2.action == "error"
    assert result2.meta.get("blocked_reason") == "symbol_quarantined_pending_reconciliation"
    assert len(http.calls) == 1  # blocked before a second physical dispatch


# --- T3 / T4: nested CANCEL with a real post-response parser exception (HIGH3) --


def test_t3_upper_limit_cancel_real_post_response_parser_exception(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    http = _RecordingHttp(text=json.dumps({"return_code": 0, "ord_no": "CANCEL-1"}))
    real_ex = _real_executor(http)
    monkeypatch.setattr(real_executor_module, "classify_mutation_response", lambda *a, **k: (_ for _ in ()).throw(ValueError("malformed cancel response body")))
    monkeypatch.setattr(
        efp, "_should_attempt_upper_limit_cancel",
        lambda state, execution, order: (True, {"guard_applied": True, "order_id": "ORD-1"}),
    )

    state = {
        "unknown_quarantine_guard_path": str(qdir),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
        "run_id": "run-t3",
    }
    state["execution"] = {"allowed": True, "ok": True, "broker_outcome": "ACCEPTED", "payload": {"order_id": "ORD-1"}}

    result = efp._attempt_upper_limit_cancel(
        state=state,
        catalog=efp._import_api_catalog().load(_api_catalog_path(tmp_path)),
        executor=real_ex,
        order={"action": "BUY", "symbol": "005930", "dmst_stex_tp": "KRX"},
        execution=state["execution"],
    )
    assert len(http.calls) == 1  # cancel physically dispatched exactly once
    assert result["cancel_ok"] is False
    assert result["cancel"]["broker_outcome"] == "UNKNOWN"
    # Parent order's own outcome is untouched (namespaced, additive fields only).
    assert state["execution"]["broker_outcome"] == "ACCEPTED"
    assert state["execution"]["cancel_broker_outcome"] == "UNKNOWN"
    assert state["execution"]["cancel_reconciliation_required"] is True
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    spy = _AcceptedExecutor()
    state2 = _base_state(tmp_path, executor=spy, symbol="005930", quarantine_dir=qdir)
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"
    assert spy.calls == 0


def test_t4_unfilled_order_recovery_cancel_real_post_response_parser_exception(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    http = _RecordingHttp(text=json.dumps({"return_code": 0, "ord_no": "CANCEL-2"}))
    real_ex = _real_executor(http)
    monkeypatch.setattr(real_executor_module, "classify_mutation_response", lambda *a, **k: (_ for _ in ()).throw(ValueError("malformed cancel response body")))
    monkeypatch.setattr(
        efp, "evaluate_unfilled_order_recovery_start",
        lambda **kwargs: {"attempted": True, "remaining_qty": 5, "cancel_reason": "unfilled_recovery_test"},
    )

    state = {
        "unknown_quarantine_guard_path": str(qdir),
        "recent_buy_guard_path": str(tmp_path / "recent_buy.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell.json"),
        "run_id": "run-t4",
    }
    state["execution"] = {"allowed": True, "ok": True, "broker_outcome": "ACCEPTED", "payload": {"order_id": "ORD-2"}}

    result = efp._attempt_unfilled_order_recovery(
        state=state,
        catalog=efp._import_api_catalog().load(_api_catalog_path(tmp_path)),
        executor=real_ex,
        order={"action": "SELL", "symbol": "005930", "dmst_stex_tp": "KRX"},
        execution=state["execution"],
    )
    assert len(http.calls) == 1
    assert result["cancel_ok"] is False
    assert result["cancel"]["broker_outcome"] == "UNKNOWN"
    assert state["execution"]["broker_outcome"] == "ACCEPTED"
    assert state["execution"]["cancel_broker_outcome"] == "UNKNOWN"
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    spy = _AcceptedExecutor()
    state2 = _base_state(tmp_path, executor=spy, symbol="005930", quarantine_dir=qdir)
    out2 = execute_from_packet(state2)
    assert out2["execution"]["allowed"] is False
    assert spy.calls == 0


# --- T5-T8: existing BrokerOutcome contract, confirmed unaffected -----------
#
# T5 (explicit ACCEPTED), T6 (explicit REJECTED), T7 (pre-dispatch failure ->
# NOT_SENT), and T8 (post-dispatch transport failure -> UNKNOWN) are already
# covered by tests/test_step5b_broker_submission_safety.py::
#   test_explicit_broker_success_is_accepted (T5)
#   test_explicit_broker_reject_is_rejected (T6)
#   test_preflight_failure_is_not_sent (T7)
#   test_buy_mutation_transport_attempt_is_one_on_timeout (T8)
# Re-run here as part of the same session to confirm the Fix 4 boundary
# change did not alter any of them.


def test_t5_explicit_accepted_unaffected_by_fix4():
    http = _RecordingHttp(text=json.dumps({"ord_no": "A1", "msg_cd": "0000", "msg1": "accepted"}))
    ex = _real_executor(http)
    result = ex.execute(_mutation_req())
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "ACCEPTED"


def test_t6_explicit_rejected_unaffected_by_fix4():
    http = _RecordingHttp(text=json.dumps({"return_code": 20, "return_msg": "insufficient funds"}))
    ex = _real_executor(http)
    result = ex.execute(_mutation_req())
    assert len(http.calls) == 1
    assert result.meta["broker_outcome"] == "REJECTED"


def test_t7_pre_dispatch_failure_is_not_sent_zero_physical_calls(monkeypatch):
    from libs.execution.executors.base import ExecutionDisabledError

    http = _RecordingHttp()
    ex = _real_executor(http)
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mutation_req())
    assert len(http.calls) == 0


def test_t8_post_dispatch_transport_failure_is_unknown_one_physical_call():
    class _RaisingHttp:
        def __init__(self):
            self.calls = 0

        def request(self, *a, **k):
            self.calls += 1
            raise TimeoutError("boom")

    http = _RaisingHttp()
    ex = _real_executor(http)
    result = ex.execute(_mutation_req())
    assert http.calls == 1
    assert result.meta["broker_outcome"] == "UNKNOWN"
    assert result.meta["submission_phase"] == "mutation_http_call"


# --- T9: durable symbol quarantine survives a simulated restart ------------


def test_t9_symbol_quarantine_survives_simulated_restart(tmp_path):
    qdir = tmp_path / "quarantine"
    persisted = uq.quarantine_symbol_for_unknown_outcome(symbol="005930", operation="BUY", now_epoch=1000, override_path=str(qdir))
    assert persisted is True
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    # Simulated restart: no shared in-memory state carried over.
    allowed, reason, _ = uq.evaluate_unknown_quarantine_guard("005930", override_path=str(qdir))
    assert allowed is False
    assert reason == "symbol_quarantined_pending_reconciliation"


# --- T10: global halt persistence fallback (HIGH4) --------------------------


def test_t10_global_halt_survives_primary_directory_write_failure_via_fallback(tmp_path, monkeypatch):
    qdir = tmp_path / "quarantine"
    real_write = uq.write_quarantine_lock_if_absent

    def _fail_primary_only(lock_path, payload):
        if str(uq._GLOBAL_MUTATION_HALT_FALLBACK_DIR) in str(lock_path):
            return real_write(lock_path, payload)
        return False  # primary quarantine dir simulated unwritable

    monkeypatch.setattr(uq, "write_quarantine_lock_if_absent", _fail_primary_only)

    persisted = uq.quarantine_symbol_for_unknown_outcome(symbol="005930", operation="BUY", now_epoch=1000, override_path=str(qdir))
    assert persisted is False  # per-symbol lock itself genuinely failed
    assert uq.GLOBAL_MUTATION_HALT["active"] is True
    assert uq.GLOBAL_MUTATION_HALT["durable"] is True  # fallback temp-dir write succeeded
    assert not (qdir / uq._GLOBAL_MUTATION_HALT_MARKER_NAME).exists()
    assert (uq._GLOBAL_MUTATION_HALT_FALLBACK_DIR / uq._GLOBAL_MUTATION_HALT_MARKER_NAME).exists()

    # Simulated restart: primary directory still "unwritable" in this
    # process too (irrelevant -- we only need to *read*, not write, to
    # detect the halt), in-memory flag cleared.
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    active, details = uq.global_mutation_halt_active(str(qdir))
    assert active is True
    assert "quarantine_lock_write_failed:005930" in str(details.get("reason") or "")

    spy = _AcceptedExecutor()
    state = _base_state(tmp_path, executor=spy, symbol="000660", quarantine_dir=qdir)  # unrelated symbol
    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "global_mutation_halt_active"
    assert spy.calls == 0


# --- T11: dual persistence failure -- honest residual-risk reporting -------


def test_t11_dual_persistence_failure_is_reported_honestly_not_masked(tmp_path, monkeypatch):
    """Both the primary quarantine dir AND the OS-temp-dir fallback fail to
    persist (e.g. genuine whole-volume outage on a single-disk host). The
    in-memory halt still protects the CURRENT process (fail-closed), but
    the system must not claim restart-survivability it cannot deliver --
    this is Step 5B Fix 4's explicitly required honesty requirement, not a
    bug to hide."""
    qdir = tmp_path / "quarantine"
    monkeypatch.setattr(uq, "write_quarantine_lock_if_absent", lambda *a, **k: False)

    persisted = uq.quarantine_symbol_for_unknown_outcome(symbol="005930", operation="BUY", now_epoch=1000, override_path=str(qdir))
    assert persisted is False

    # Current process: still fail-closed, in-memory.
    assert uq.GLOBAL_MUTATION_HALT["active"] is True
    allowed, reason, _ = uq.evaluate_unknown_quarantine_guard("000660", override_path=str(qdir))
    assert allowed is False
    assert reason == "global_mutation_halt_active"

    # Honest self-report: neither location durably persisted.
    assert uq.GLOBAL_MUTATION_HALT["durable"] is False

    # Simulated restart: this specific double failure is a genuine,
    # documented residual risk -- filesystem-only persistence cannot close
    # it without external infrastructure (explicitly out of scope). The
    # guard must not silently pretend to be safe here.
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    active, _details = uq.global_mutation_halt_active(str(qdir))
    assert active is False  # documented gap, not a false guarantee
