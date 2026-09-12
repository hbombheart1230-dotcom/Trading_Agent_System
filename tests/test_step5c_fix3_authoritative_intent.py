"""Step5C Fix3 -- canonical physical order normalization, authoritative
intent validation, physical claim orphan observability, approval read-model
truth consistency.

Codex's independent Red-Team audit of Step5C Fix2 reproduced two more HIGH
findings against the actual implementation:

HIGH1 -- libs/execution/intent_identity.py::physical_order_fingerprint()
    hashed raw field values directly. Equivalent representations of the
    SAME real order (qty=10 vs qty="10", order_type="market" vs "mkt" vs
    "", a market order carrying a stray cached price) produced DIFFERENT
    keys, so the physical-order duplicate guard added in Fix2 could be
    defeated by trivial representation differences -- broker calls == 2,
    not <= 1. Fixed by canonicalizing every field BEFORE hashing
    (_canonical_action/_canonical_order_type/_canonical_qty/
    _canonical_positive_number), each grounded in this codebase's own
    existing order-building contract (verified by grep against
    graphs/nodes/execute_from_packet.py's _build_order_from_intent, not
    guessed). Fix4 subsequently established `market`/`mkt` equivalence and
    broker-native `trde_tp=3` as MARKET compatibility requirements.

HIGH2 -- Fix3 claim_execution() could self-admit a never-before-seen
    deterministic intent_id. Fix3 attempted to distinguish trusted identity
    generation with intent_identity.is_self_minted_intent_id. Fix4 supersedes
    that authorization design: deterministic identity never grants authority,
    and an explicit persisted admission is required before claim_execution.
    Missing or unapproved identities are refused (INTENT_NOT_FOUND /
    NOT_APPROVED / INVALID_INTENT_ID), never silently created. The two "auto" shortcuts
    that never went through ApprovalService.approve()'s own PENDING->
    APPROVED transition (ExecutorAgent.submit_order_intent and
    ToolFacade.order_place_intent, both APPROVAL_MODE=auto) now explicitly
    persist their intent as approved first via the new
    ApprovalService.admit_pre_approved_intent(), preserving "creation
    authority != execution authority" while keeping that legitimate
    automatic path working.

MEDIUM1 -- a physical-order lease can be left orphaned (claimed, but the
    owning process crashed or claim_execution itself raised before
    finish_execution ever ran). Fix3 does not implement automatic release/
    recovery (explicitly out of scope, deferred to Step5D) but adds
    read-only introspection (SQLiteIntentStateStore.get_physical_claim /
    list_active_physical_claims) so an orphan is at least observable.

MEDIUM2 -- ApprovalService's own JSON read-model marker could say "failed"
    while the canonical SQLite lifecycle said "executing" (an ambiguous
    exception after a claim was already taken). Fixed: the exception
    handler now only writes/transitions to "failed" when canonical state is
    still "approved" (no claim was ever taken, so there is no dispatch
    ambiguity); otherwise it writes an "executing"/reconciliation_required
    marker instead, matching canonical truth.
"""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphs.nodes.execute_from_packet import _normalize_execution
from libs.execution.intent_execution_owner import execute_owned_order
from libs.execution.intent_identity import physical_order_fingerprint
from libs.supervisor.intent_state_store import SQLiteIntentStateStore


# --- shared helpers -------------------------------------------------------


class _SpyExecutor:
    def __init__(self, outcome: str = "ACCEPTED"):
        self.calls = 0
        self.outcome = outcome

    def execute(self, req, *, auth_token=None):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        self.calls += 1
        ok = self.outcome == "ACCEPTED"
        return ExecutionResult(
            response=ApiResponse(status_code=200, ok=ok, payload={"return_code": "0" if ok else "1"},
                                  error_code=None, error_message=None, raw_text=""),
            meta={"executor": "mock", "broker_outcome": self.outcome},
        )


def _order(iid: str, **fields) -> dict:
    base = {"intent_id": iid, "action": "BUY", "symbol": "005930", "qty": 10, "price": None,
            "order_type": "market"}
    base.update(fields)
    return base


def _authorize(iid: str, *, root=None, **order_kwargs) -> None:
    """Step5C Fix5 (HIGH2, consumer-only claim_execution): admits iid --
    persisted intent + persisted admission bound to the SAME canonical
    physical fingerprint the matching _order(iid, **order_kwargs) would
    produce -- exactly as ApprovalService.approve()/admit_pre_approved_
    intent/admit_order_intent do in production. Fix4's "legacy_approved_
    state" auto-admission inside claim_execution() (which this helper used
    to lean on implicitly by only setting state=approved with no admission
    row) was exactly Codex's Fix4-audit HIGH2 finding and has been removed
    outright."""
    from libs.execution.intent_identity import physical_order_fingerprint

    store = SQLiteIntentStateStore(root) if root else SQLiteIntentStateStore()
    key = physical_order_fingerprint({}, _order(iid, **order_kwargs))
    admitted = store.admit_intent(iid, fingerprint=key, source="test_policy")
    assert admitted.get("admitted") or admitted.get("reason") == "intent_identity_conflict", admitted


def _claim(executor, iid: str, **order_kwargs) -> dict:
    _authorize(iid, **order_kwargs)
    candidate = _order(iid, **order_kwargs)
    return execute_owned_order(state={"run_id": "run-" + iid}, order=candidate, request=None,
        executor=executor, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate))


def _api_catalog_path(tmp_path: Path) -> str:
    import json
    p = tmp_path / "catalog.jsonl"
    p.write_text(
        json.dumps({
            "api_id": "kt10000", "method": "POST", "path": "/api/dostk/ordr",
            "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]},
        }) + "\n",
        encoding="utf-8",
    )
    return str(p)


def _runner(tmp_path: Path, executor):
    from libs.core.settings import Settings
    from libs.skills.runner import CompositeSkillRunner

    r = CompositeSkillRunner(
        settings=Settings.from_env(env_path="__missing__.env"),
        catalog_path=_api_catalog_path(tmp_path),
        event_log_path=str(tmp_path / "events.jsonl"),
    )
    r.executor = executor
    return r


def _manual_args(intent_id: str, **fields) -> dict:
    base = {"side": "buy", "symbol": "005930", "qty": 10, "order_type": "market", "price": None,
            "intent_id": intent_id}
    base.update(fields)
    return base


# =========================================================================
# HIGH1: physical order fingerprint normalization (T1-T11)
# =========================================================================


def test_t1_market_alias_normalizes_to_same_key():
    key_market = physical_order_fingerprint({}, _order("a", order_type="market", qty=10, price=None))
    key_mkt = physical_order_fingerprint({}, _order("a", order_type="mkt", qty="10", price=71500))
    assert key_market is not None
    assert key_market == key_mkt


def test_t1b_market_order_ignores_cached_reference_price():
    key_no_price = physical_order_fingerprint({}, _order("a", order_type="market", qty=10, price=None))
    key_stray_price = physical_order_fingerprint({}, _order("a", order_type="market", qty=10, price=71500))
    assert key_no_price is not None
    assert key_no_price == key_stray_price


def test_t2_qty_int_and_str_forms_normalize_to_same_key():
    key_int = physical_order_fingerprint({}, _order("a", qty=10))
    key_str = physical_order_fingerprint({}, _order("a", qty="10"))
    key_padded = physical_order_fingerprint({}, _order("a", qty="010"))
    assert key_int == key_str == key_padded
    assert key_int is not None


def test_t3_limit_price_int_and_str_forms_normalize_to_same_key():
    key_int = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price=70000))
    key_str = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price="70000"))
    key_float_str = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price="70000.0"))
    assert key_int == key_str == key_float_str
    assert key_int is not None


def test_t4_action_case_aliases_normalize_to_same_key():
    key_upper = physical_order_fingerprint({}, _order("a", action="BUY", qty=10, price=None))
    key_lower = physical_order_fingerprint({}, _order("a", action="buy", qty=10, price=None))
    key_mixed = physical_order_fingerprint({}, _order("a", action="Buy", qty=10, price=None))
    assert key_upper == key_lower == key_mixed
    assert key_upper is not None


def test_t5_symbol_prefixed_alias_normalizes_to_same_key():
    # normalize_symbol (libs/core/symbols.py, the existing production
    # contract, reused verbatim here -- not reimplemented) already strips a
    # leading "A" from a 6-digit live KRX code.
    key_plain = physical_order_fingerprint({}, _order("a", qty=10, price=None) | {"symbol": "005930"})
    key_prefixed = physical_order_fingerprint({}, _order("a", qty=10, price=None) | {"symbol": "A005930"})
    assert key_plain == key_prefixed
    assert key_plain is not None


def test_t6_different_qty_are_different_keys():
    key10 = physical_order_fingerprint({}, _order("a", qty=10, price=None))
    key20 = physical_order_fingerprint({}, _order("a", qty=20, price=None))
    assert key10 != key20


def test_t7_buy_vs_sell_are_different_keys():
    key_buy = physical_order_fingerprint({}, _order("a", action="BUY", qty=10, price=None))
    key_sell = physical_order_fingerprint({}, _order("a", action="SELL", qty=10, price=None))
    assert key_buy != key_sell


def test_t8_market_vs_limit_are_different_keys():
    key_mkt = physical_order_fingerprint({}, _order("a", order_type="market", qty=10, price=None))
    key_lmt = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price=70000))
    assert key_mkt != key_lmt


def test_t9_different_limit_price_are_different_keys():
    key_a = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price=70000))
    key_b = physical_order_fingerprint({}, _order("a", order_type="limit", qty=10, price=71000))
    assert key_a != key_b


def test_t10_different_account_scope_are_different_keys(monkeypatch):
    key_a = physical_order_fingerprint({"account_id": "ACC-A"}, _order("a", qty=10, price=None))
    key_b = physical_order_fingerprint({"account_id": "ACC-B"}, _order("a", qty=10, price=None))
    assert key_a != key_b


def test_invalid_qty_forms_fail_closed():
    assert physical_order_fingerprint({}, _order("a", qty="10.5", price=None)) is None
    assert physical_order_fingerprint({}, _order("a", qty=-1, price=None)) is None
    assert physical_order_fingerprint({}, _order("a", qty=0, price=None)) is None
    assert physical_order_fingerprint({}, _order("a", qty="abc", price=None)) is None
    assert physical_order_fingerprint({}, _order("a", qty=None, price=None)) is None


def test_cancel_requires_orig_ord_no_and_never_collides_with_original_order():
    buy_key = physical_order_fingerprint({}, _order("a", action="BUY", qty=10, price=None, orig_ord_no=""))
    cancel_key = physical_order_fingerprint({}, {"action": "CANCEL", "symbol": "005930",
                                                  "orig_ord_no": "0099001", "cncl_qty": 10})
    assert buy_key != cancel_key
    assert physical_order_fingerprint({}, {"action": "CANCEL", "symbol": "005930", "orig_ord_no": ""}) is None


# --- T12/T13-equivalent: real cross-process alias attack ------------------


def _t12_worker_a(db, event_claimed, queue, order_fields):
    import time as _time
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    from libs.execution.intent_identity import physical_order_fingerprint as _pof
    ex = _SpyExecutor()
    iid = "cross-process-alias-A"
    store = SQLiteIntentStateStore(db)
    candidate = _order(iid, **order_fields)
    store.admit_intent(iid, fingerprint=_pof({}, candidate), source="test_policy")

    def _hold_lease_briefly():
        event_claimed.set()
        _time.sleep(0.3)  # keep the physical lease active while B attempts its alias

    result = execute_owned_order(state={"run_id": "run-" + iid}, order=candidate, request=None,
        executor=ex, on_submit=_hold_lease_briefly, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate))
    queue.put(("A", ex.calls, result["broker_outcome"], _pof({}, candidate)))


def _t12_worker_b(db, event_claimed, queue, order_fields):
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    from libs.execution.intent_identity import physical_order_fingerprint as _pof
    event_claimed.wait(timeout=10)
    ex = _SpyExecutor()
    iid = "cross-process-alias-B"
    store = SQLiteIntentStateStore(db)
    candidate = _order(iid, **order_fields)
    store.admit_intent(iid, fingerprint=_pof({}, candidate), source="test_policy")
    result = execute_owned_order(state={"run_id": "run-" + iid}, order=candidate, request=None,
        executor=ex, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate))
    queue.put(("B", ex.calls, result["broker_outcome"], _pof({}, candidate)))


def test_t12_real_multiprocess_normalization_alias_attack_total_calls_le_1(tmp_path):
    """Codex's exact reproduction, closed: process A submits qty=10 (int)
    with no price; process B submits qty="10" (str) with a stray market
    price -- different string/numeric representations of the SAME real
    market order. Genuine overlap (not mere sequencing -- see
    test_step5c_fix2_ownership_capability.py's t8/t8b for why that
    distinction matters) is forced via an Event: B only attempts its alias
    while A's physical lease is still held."""
    context = multiprocessing.get_context("spawn")
    db = str(tmp_path / "alias_attack.db")
    event_claimed, queue = context.Event(), context.Queue()
    processes = [
        context.Process(target=_t12_worker_a, args=(db, event_claimed, queue,
                         {"qty": 10, "order_type": "market", "price": None})),
        context.Process(target=_t12_worker_b, args=(db, event_claimed, queue,
                         {"qty": "10", "order_type": "mkt", "price": 71500})),
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(30)
        assert p.exitcode == 0
    results = [queue.get(timeout=5) for _ in processes]
    keys = {key for _, _, _, key in results}
    assert len(keys) == 1, "int vs str qty, and a stray market price, must canonicalize to the SAME key"
    total_calls = sum(calls for _, calls, _, _ in results)
    assert total_calls == 1


# =========================================================================
# HIGH2: authoritative intent validation (T11-T16)
# =========================================================================


@pytest.mark.parametrize("bad_id", [None, "", "   ", "bad id", "@@@"])
def test_t11_malformed_or_blank_intent_id_is_broker_zero(tmp_path, bad_id):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(bad_id or ""))
    assert result.action == "error"
    assert ex.calls == 0


def test_t12_well_formed_but_nonexistent_intent_id_is_broker_zero(tmp_path):
    """The core of HIGH2: format alone is not authorization. A
    perfectly-well-formed, uuid4-shaped id that was never created/approved
    anywhere must still be refused."""
    import uuid
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    never_seen = uuid.uuid4().hex
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(never_seen))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "INTENT_NOT_FOUND"
    assert ex.calls == 0


def test_t13_pending_intent_is_broker_zero(tmp_path):
    """A bare pending intent, with no admission at all, is refused as
    ADMISSION_NOT_FOUND -- the admission check (item 8, step 4-5) runs
    before the approval-state check (step 6), and in practice admission
    creation and the pending->approved promotion happen atomically
    together (admit_intent), so a genuinely pending-with-no-admission row
    is the realistic shape of "not approved yet"."""
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "pending-only-intent"
    store = SQLiteIntentStateStore()
    store.ensure_intent(iid)  # left pending -- never approved, never admitted
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "ADMISSION_NOT_FOUND"
    assert ex.calls == 0


def test_t13b_pending_intent_with_admission_is_not_approved_broker_zero(tmp_path):
    """The NOT_APPROVED reason (item 8, step 6) is still reachable in the
    synthetic case where admission exists but the state transition into
    approved has not (yet) happened -- e.g. a crash between admit_intent's
    own two writes, or direct DB manipulation. claim_execution must still
    refuse it, distinctly from ADMISSION_NOT_FOUND."""
    import sqlite3
    import time as _time

    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "pending-with-admission-intent"
    store = SQLiteIntentStateStore()
    store.ensure_intent(iid)  # state stays pending_approval
    from libs.execution.intent_identity import physical_order_fingerprint
    key = physical_order_fingerprint({}, _order(iid))
    conn = sqlite3.connect(str(store.path))
    conn.execute("INSERT INTO intent_admission VALUES(?,?,?,?)", (iid, key, "test_direct_insert", int(_time.time())))
    conn.commit()
    conn.close()
    assert store.get_state(iid)["state"] == "pending_approval"
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "NOT_APPROVED"
    assert ex.calls == 0


def test_t14_approved_intent_claims_and_dispatches(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "approved-intent"
    _authorize(iid)
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert result.action == "ready"
    assert ex.calls == 1


def test_t15_executing_intent_second_attempt_is_broker_zero(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "executing-intent"
    _authorize(iid)
    first = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert first.action == "ready"
    ex2 = _SpyExecutor()
    runner.executor = ex2
    second = runner.run(run_id="run-2", skill="order.place", args=_manual_args(iid))
    assert second.action == "error"
    assert ex2.calls == 0


def test_t16_executed_and_failed_intents_are_broker_zero(tmp_path):
    for outcome, iid in (("ACCEPTED", "already-executed-intent"), ("REJECTED", "already-failed-intent")):
        ex = _SpyExecutor(outcome=outcome)
        runner = _runner(tmp_path, ex)
        _authorize(iid)
        first = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
        assert first.action == "ready"
        ex2 = _SpyExecutor()
        runner.executor = ex2
        second = runner.run(run_id="run-2", skill="order.place", args=_manual_args(iid))
        assert second.action == "error"
        assert ex2.calls == 0


def test_self_minted_identity_without_admission_is_broker_zero(monkeypatch):
    """A deterministic identity proves identity, never authority."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex = _SpyExecutor()
    candidate = {"action": "BUY", "symbol": "005930", "qty": 10, "price": None, "order_type": "market"}
    result = execute_owned_order(state={"run_id": "auto-run"}, order=candidate, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=candidate))
    assert result["broker_outcome"] == "NOT_SENT"
    assert result["reason"] == "INTENT_NOT_FOUND"
    assert ex.calls == 0


# --- item 18: approval_cli / auto-path regression through the real chain --


def test_approval_mode_auto_via_real_toolfacade_still_dispatches(tmp_path, monkeypatch):
    """ToolFacade.order_place_intent's APPROVAL_MODE=auto shortcut never
    goes through approve()'s own PENDING->APPROVED transition -- it must
    now explicitly persist the intent as approved itself
    (ApprovalService.admit_pre_approved_intent) before Fix3's authoritative
    check would otherwise refuse it as INTENT_NOT_FOUND."""
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "auto")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)

    from libs.tools.tool_facade import ToolFacade

    facade = ToolFacade(
        catalog=_api_catalog_path(tmp_path),
        event_log=str(tmp_path / "events.jsonl"),
        intent_store=str(tmp_path / "intents.jsonl"),
    )
    spy = _SpyExecutor()
    facade.runner.executor = spy
    res = facade.order_place_intent(side="buy", symbol="005930", qty=10, order_type="market")
    assert "execution" in res
    assert spy.calls == 1
    iid = res["decision"]["intent"]["intent_id"]
    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    row = store.get_state(iid)
    assert row is not None and row["state"] == "executed"


def test_approval_mode_auto_via_real_executor_agent_still_dispatches(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "auto")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    monkeypatch.delenv("MAX_ORDER_NOTIONAL", raising=False)
    monkeypatch.delenv("MAX_NOTIONAL", raising=False)
    monkeypatch.delenv("MAX_ORDER_QTY", raising=False)
    monkeypatch.delenv("MAX_QTY", raising=False)

    from libs.core.settings import Settings
    from libs.skills.runner import CompositeSkillRunner
    from libs.agent.executor.executor_agent import ExecutorAgent
    from libs.supervisor.intent_store import IntentStore
    from libs.supervisor.two_phase import TwoPhaseSupervisor

    store_path = tmp_path / "intents.jsonl"
    store = IntentStore(str(store_path))
    sup = TwoPhaseSupervisor(Settings.from_env())
    runner = CompositeSkillRunner.from_env()
    agent = ExecutorAgent(runner=runner, supervisor=sup, intent_store=store, intent_store_path=store_path)

    res = agent.submit_order_intent(side="buy", symbol="005930", qty=10, order_type="market",
        approval_mode="auto", execution_enabled=True, rationale="fix3 auto-mode regression")
    assert "execution" in res
    iid = res["decision"]["intent"]["intent_id"]
    state_store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    row = state_store.get_state(iid)
    assert row is not None and row["state"] in ("executed", "failed")


# =========================================================================
# MEDIUM1: physical claim orphan observability
# =========================================================================


def test_orphan_from_deterministic_pre_dispatch_denial_is_released_safely(monkeypatch):
    """A physical claim immediately followed by a claim_execution denial
    that PROVABLY happened before any dispatch (no crash, ordinary Python
    control flow) is safe to release -- there is no ambiguity."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    iid_a, iid_b = "orphan-safe-a", "orphan-safe-b"
    _authorize(iid_a)
    # iid_b is deliberately NOT authorized -- its claim_execution call will
    # be denied (INTENT_NOT_FOUND) immediately after the physical claim
    # succeeds, with certainty that no dispatch occurred.
    ex_a = _SpyExecutor()
    first = _claim(ex_a, iid_a, qty=10, price=None)
    assert first["broker_outcome"] == "ACCEPTED"

    key = physical_order_fingerprint({"run_id": "run-" + iid_b}, _order(iid_b, qty=99, price=None))
    ex_b = _SpyExecutor()
    candidate_b = _order(iid_b, qty=99, price=None)
    denied = execute_owned_order(state={"run_id": "run-" + iid_b}, order=candidate_b, request=None,
        executor=ex_b, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate_b))
    assert denied["reason"] == "INTENT_NOT_FOUND"
    assert ex_b.calls == 0
    store = SQLiteIntentStateStore()
    # The physical lease iid_b momentarily reserved must be released -- no
    # ambiguity, so a later legitimate attempt at that SAME physical shape
    # (qty=99) is not permanently blocked.
    assert store.get_physical_claim(key) is None


def _orphan_crash_worker(db):
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    _authorize("orphan-crash-intent", root=db)
    candidate = _order("orphan-crash-intent", qty=10, price=None)

    class _CrashingExecutor:
        def execute(self, request):
            os._exit(0)  # hard exit -- no cleanup code runs, matching a real crash/SIGKILL

    execute_owned_order(state={"run_id": "run-orphan-crash"}, order=candidate, request=None,
        executor=_CrashingExecutor(), normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate))


def test_orphan_from_real_process_crash_is_retained_and_observable(tmp_path):
    """The inverse of the safe-release case: a REAL OS process hard-exits
    between claim_physical_order succeeding and finish_execution ever
    running. No automatic release/recovery is implemented (explicitly out
    of scope for Fix3 -- Step5D's job); the lease must stay held (fail
    closed, blocking a broker retry) AND be observable via the new
    introspection API."""
    db = str(tmp_path / "orphan_crash.db")
    process = multiprocessing.get_context("spawn").Process(target=_orphan_crash_worker, args=(db,))
    process.start()
    process.join(30)
    assert process.exitcode == 0

    store = SQLiteIntentStateStore(db)
    assert store.get_state("orphan-crash-intent")["state"] == "executing"

    key = physical_order_fingerprint({"run_id": "run-orphan-crash"}, _order("orphan-crash-intent", qty=10, price=None))
    claim_row = store.get_physical_claim(key)
    assert claim_row is not None
    assert claim_row["intent_id"] == "orphan-crash-intent"
    assert claim_row["state"] == "active"
    active = store.list_active_physical_claims()
    assert any(row["physical_order_key"] == key for row in active)

    # A retry (real or naive) against the same physical order is blocked --
    # broker call 0, exactly as an unresolved orphan lease must behave.
    ex_retry = _SpyExecutor()
    retry_candidate = _order("orphan-crash-retry-intent", qty=10, price=None)
    _authorize("orphan-crash-retry-intent", root=db)
    os.environ["INTENT_STATE_DB_PATH"] = db
    retry = execute_owned_order(state={"run_id": "retry-run"}, order=retry_candidate, request=None,
        executor=ex_retry, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=retry_candidate))
    assert retry["broker_outcome"] == "NOT_SENT"
    assert ex_retry.calls == 0


# =========================================================================
# MEDIUM2: approval read-model must not contradict canonical SQLite truth
# =========================================================================


def test_unknown_outcome_read_model_marker_is_not_failed(tmp_path, monkeypatch):
    """Section 25's exact scenario via the real ToolFacade chain: SQLite
    stays "executing", the JSON read-model marker must NOT say "failed",
    broker_outcome is UNKNOWN, reconciliation_required is True, and a
    retry dispatches zero broker calls."""
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)

    from libs.tools.tool_facade import ToolFacade

    intent_store_path = tmp_path / "intents.jsonl"
    facade = ToolFacade(
        catalog=_api_catalog_path(tmp_path),
        event_log=str(tmp_path / "events.jsonl"),
        intent_store=str(intent_store_path),
    )
    facade.runner.executor = _SpyExecutor(outcome="UNKNOWN")

    created = facade.order_place_intent(side="buy", symbol="005930", qty=10, order_type="market")
    iid = created["decision"]["intent"]["intent_id"]
    result = facade.approve_intent(intent_id=iid)

    assert result["status"] == "executing"
    assert result.get("reconciliation_required") is True

    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    assert store.get_state(iid)["state"] == "executing"

    # The JSON read-model's own markers for this intent must never claim
    # "failed" -- canonical SQLite truth (executing) is authoritative and
    # the read-model must not contradict it.
    rows = facade.intent_store.load_all_rows()
    statuses = [r.get("status") for r in rows if str(r.get("intent_id") or "") == str(iid)]
    assert "failed" not in statuses

    fresh = _SpyExecutor()
    facade.runner.executor = fresh
    replay = facade.approve_intent(intent_id=iid)
    assert replay["ok"] is False
    assert fresh.calls == 0


def test_exception_before_any_claim_is_recorded_failed_both_places(tmp_path, monkeypatch):
    """The inverse: when NO canonical claim was ever taken (state is still
    "approved" at the moment execute_fn raises), there is no ambiguity, and
    it IS correct for both canonical SQLite and the JSON read-model to say
    "failed"."""
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)

    from libs.supervisor.intent_store import IntentStore
    from libs.approval.service import ApprovalService
    from libs.supervisor.two_phase import TwoPhaseSupervisor

    intent_store = IntentStore(str(tmp_path / "intents.jsonl"))
    sup = TwoPhaseSupervisor()
    decision = sup.create_intent({"action": "BUY", "symbol": "005930", "qty": 10, "order_type": "market"})
    from dataclasses import asdict
    intent = asdict(decision)["intent"]
    intent_store.save(intent)
    iid = intent["intent_id"]

    svc = ApprovalService(intent_store)

    def _boom(it):
        raise RuntimeError("pre-claim failure, never reached execute_owned_order")

    with pytest.raises(RuntimeError):
        svc.approve(intent_id=iid, execution_enabled=True, execute_fn=_boom)

    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    assert store.get_state(iid)["state"] == "failed"
    rows = intent_store.load_all_rows()
    statuses = [r.get("status") for r in rows if str(r.get("intent_id") or "") == str(iid)]
    assert statuses[-1] == "failed"
