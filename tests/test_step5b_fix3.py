"""Phase 1 Step 5B Fix 3 -- closes three HIGH gaps confirmed by Codex's
independent re-verification of the prior Step 5B state:

HIGH1: ToolFacade / ExecutorAgent / CompositeSkillRunner's direct mutation
       path never checked or wrote the durable UNKNOWN quarantine state, so
       the same logical mutation could be resubmitted through that path
       even while quarantined on the canonical execute_from_packet.py path
       (or vice versa).
HIGH2: A nested CANCEL (upper-limit auto-cancel / unfilled-order recovery)
       whose response parsing/classification raised an exception (after the
       mutation was already physically dispatched) escaped as a bare
       exception string with no quarantine.
HIGH3: _GLOBAL_MUTATION_HALT was purely in-memory, so it did not survive a
       process restart.

No BrokerOutcome states, quarantine storage model, or trading logic were
changed -- these tests exercise the *existing* mechanisms (durable
per-symbol lock file, existence-based fail-closed guard,
_GLOBAL_MUTATION_HALT) through the paths that previously bypassed them.
"""
from __future__ import annotations

import json
import os

import pytest

from graphs.nodes import execute_from_packet as efp
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.execution.guards import unknown_quarantine as uq


# --- shared fixtures ---------------------------------------------------------


def _clear_fallback_marker():
    try:
        (uq._global_mutation_halt_fallback_dir() / uq._GLOBAL_MUTATION_HALT_MARKER_NAME).unlink()
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True)
def _reset_global_mutation_halt():
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_fallback_marker()
    yield
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    _clear_fallback_marker()


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


class _UnknownExecutor:
    calls = 0

    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        self.calls += 1
        return ExecutionResult(
            response=ApiResponse(status_code=0, ok=False, payload={}, error_code=None, error_message="timeout", raw_text=""),
            meta={"executor": "real", "broker_outcome": "UNKNOWN", "submission_phase": "mutation_http_call", "submission_attempts": 1, "exception_type": "TimeoutError", "reconciliation_required": True},
        )


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


# --- HIGH1: cross-path quarantine sharing -----------------------------------


def test_high1_symbol_quarantined_via_execute_from_packet_blocks_runner_path(tmp_path, monkeypatch):
    """A symbol quarantined through the canonical execute_from_packet.py
    guard chain (UNKNOWN outcome) must also block CompositeSkillRunner's
    independent mutation path -- physical mutation call count on that
    second path must be zero."""
    qdir = tmp_path / "quarantine"
    state = _base_state(tmp_path, executor=_UnknownExecutor(), symbol="005930", quarantine_dir=qdir)
    out = execute_from_packet(state)
    assert out["execution"]["broker_outcome"] == "UNKNOWN"
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    from libs.skills.runner import CompositeSkillRunner
    from libs.core.settings import Settings

    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(qdir))
    runner = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        catalog_path=_api_catalog_path(tmp_path),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    spy = _AcceptedExecutor()
    runner.executor = spy

    result = runner.run(
        run_id="run-2",
        skill="order.place",
        args={"side": "buy", "symbol": "005930", "qty": 1, "order_type": "market", "price": None},
    )
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "symbol_quarantined_pending_reconciliation"
    assert spy.calls == 0  # physical mutation call-count reproduction: must never dispatch


def test_high1_runner_unknown_outcome_quarantines_symbol_for_execute_from_packet(tmp_path, monkeypatch):
    """The reverse direction: an UNKNOWN outcome from CompositeSkillRunner's
    own mutation dispatch must quarantine the symbol so a subsequent
    execute_from_packet.py attempt on the same symbol is blocked."""
    qdir = tmp_path / "quarantine"
    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(qdir))

    from libs.skills.runner import CompositeSkillRunner
    from libs.core.settings import Settings

    runner = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        catalog_path=_api_catalog_path(tmp_path),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    runner.executor = _UnknownExecutor()

    result = runner.run(
        run_id="run-1",
        skill="order.place",
        args={"side": "buy", "symbol": "005930", "qty": 1, "order_type": "market", "price": None},
    )
    assert result.action == "ready"  # the skill call itself completes; quarantine is a side effect
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()

    spy = _AcceptedExecutor()
    state = _base_state(tmp_path, executor=spy, symbol="005930", quarantine_dir=qdir)
    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "symbol_quarantined_pending_reconciliation"
    assert spy.calls == 0  # physical mutation call-count reproduction: must never dispatch


def test_high1_read_skill_unaffected_by_quarantine(tmp_path, monkeypatch):
    """Non-mutation skills must never be gated by the quarantine guard --
    scoped strictly to mutation api_ids."""
    qdir = tmp_path / "quarantine"
    uq.quarantine_symbol_for_unknown_outcome(
        symbol="005930", operation="BUY", now_epoch=1, override_path=str(qdir)
    )
    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(qdir))

    from libs.skills.runner import CompositeSkillRunner
    from libs.core.settings import Settings

    catalog_path = tmp_path / "catalog_quote.jsonl"
    catalog_path.write_text(
        json.dumps({"api_id": "ka10003", "method": "POST", "path": "/api/dostk/mrkcond", "params": {"body": ["stk_cd"]}}) + "\n",
        encoding="utf-8",
    )
    runner = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        catalog_path=str(catalog_path),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    spy = _AcceptedExecutor()
    runner.executor = spy
    result = runner.run(run_id="run-3", skill="market.quote", args={"symbol": "005930"})
    assert result.action == "ready"
    assert spy.calls == 1  # a read call is never blocked by the mutation quarantine


# --- HIGH2: nested CANCEL classification exception still quarantines -------


def test_high2_nested_cancel_classification_exception_quarantines_symbol(tmp_path, monkeypatch):
    """If the CANCEL was physically dispatched (executor.execute() already
    returned) and a *subsequent* exception occurs while classifying/
    normalizing that response, the outcome must still be treated as UNKNOWN
    and the symbol quarantined -- never a bare, unquarantined error."""
    qdir = tmp_path / "quarantine"

    class _CancelDispatchedThenExplodes:
        def __init__(self):
            self.calls = 0

        def execute(self, req, *, auth_token=None):
            self.calls += 1
            from libs.core.api_response import ApiResponse
            from libs.execution.executors.base import ExecutionResult

            # Physically dispatched successfully (transport succeeded).
            return ExecutionResult(
                response=ApiResponse(status_code=200, ok=True, payload={"return_code": 0}, error_code=None, error_message=None, raw_text=""),
                meta={"executor": "real"},
            )

    executor = _CancelDispatchedThenExplodes()

    def _boom_normalize(**kwargs):
        # Simulate an exception raised while classifying/normalizing the
        # CANCEL's own response -- happens strictly after executor.execute()
        # already returned (dispatched=True by the time this is called).
        raise ValueError("malformed cancel response body")

    monkeypatch.setattr(efp, "_normalize_execution", _boom_normalize)
    # Isolate this test to HIGH2's own concern (post-dispatch exception
    # handling): force entry into the cancel-attempt branch directly,
    # instead of also reproducing the real upper-limit-detection trigger
    # conditions (execution_mode=real + guard details), which are a
    # separate, already-covered concern.
    monkeypatch.setattr(
        efp,
        "_should_attempt_upper_limit_cancel",
        lambda state, execution, order: (True, {"guard_applied": True, "order_id": "ORD-1"}),
    )

    state = _base_state(tmp_path, executor=executor, symbol="005930", quarantine_dir=qdir)
    result = efp._attempt_upper_limit_cancel(
        state=state,
        catalog=efp._import_api_catalog().load(_api_catalog_path(tmp_path)),
        executor=executor,
        order={"action": "BUY", "symbol": "005930", "dmst_stex_tp": "KRX"},
        execution={
            "allowed": True,
            "ok": True,
            "payload": {"order_id": "ORD-1"},
        },
    )
    assert executor.calls == 1  # confirms the CANCEL was physically dispatched
    assert result["cancel_ok"] is False
    assert result["cancel"]["broker_outcome"] == "UNKNOWN"
    assert uq.quarantine_lock_path("005930", str(qdir)).exists()


# --- HIGH3: durable global-mutation-halt marker survives a restart ---------


def test_high3_global_mutation_halt_marker_survives_simulated_restart(tmp_path):
    qdir = tmp_path / "quarantine"
    uq.activate_global_mutation_halt("disk_full_simulated", now_epoch=1000, override_path=str(qdir))
    assert uq.GLOBAL_MUTATION_HALT["active"] is True
    marker = qdir / uq._GLOBAL_MUTATION_HALT_MARKER_NAME
    assert marker.exists()

    # "restart": brand new in-memory state, nothing carried over except the
    # durable marker file on disk.
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})
    active, details = uq.global_mutation_halt_active(str(qdir))
    assert active is True
    assert details["reason"] == "disk_full_simulated"

    # And the guard itself fails closed post-"restart", for a symbol never
    # touched before.
    allowed, reason, guard_details = uq.evaluate_unknown_quarantine_guard("000660", override_path=str(qdir))
    assert allowed is False
    assert reason == "global_mutation_halt_active"


def test_high3_execute_from_packet_reflects_durable_halt_after_restart(tmp_path):
    """End-to-end: the durable marker (written by a hypothetical prior
    process incarnation) blocks execute_from_packet.py's own guard even
    though this test never itself called activate_global_mutation_halt in
    the current process."""
    qdir = tmp_path / "quarantine"
    uq.activate_global_mutation_halt("quarantine_lock_write_failed:999999", now_epoch=1, override_path=str(qdir))
    uq.GLOBAL_MUTATION_HALT.update({"active": False, "reason": "", "since_epoch": 0, "pid": 0, "durable": False})  # simulate restart

    spy = _AcceptedExecutor()
    state = _base_state(tmp_path, executor=spy, symbol="000660", quarantine_dir=qdir)
    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "global_mutation_halt_active"
    assert spy.calls == 0
