"""Step5C Fix2 -- ownership capability, canonical intent propagation,
cross-path physical duplicate closure, UNKNOWN lifecycle consistency.

Codex's independent Red-Team audit of Step5C Fix1 reproduced three HIGH
findings against the actual implementation, not against a hypothetical:

HIGH1 -- libs/skills/runner.py trusted a bare `state == EXECUTING` read as
    permission to dispatch ("Process A claims via ApprovalService -> Process
    A's runner call dispatches; Process B's INDEPENDENT runner call for the
    SAME intent_id ALSO sees EXECUTING and ALSO dispatches -- broker calls
    == 2, not <= 1"). Fixed by deleting that shortcut entirely: every real
    mutation now goes through libs/execution/intent_execution_owner.py::
    execute_owned_order()'s single atomic claim_execution() CAS,
    unconditionally, with no "someone else already looks like they own
    it, so just dispatch" branch anywhere. ApprovalService.approve() no
    longer performs its own separate approved->executing transition for
    the same reason -- that was the second, independent claiming mechanism
    that made the state-only trust exploitable.

HIGH2 -- the actual production CLI chain is
    scripts/approval_cli.py -> ToolFacade.approve_intent (libs/tools/
    tool_facade.py) -> ApprovalService -> ToolFacade.order_execute ->
    CompositeSkillRunner. It never goes through
    libs/agent/executor/executor_agent.py::ExecutorAgent at all. Fix1 only
    patched ExecutorAgent's copy of this plumbing, so the real CLI path
    still silently minted a brand-new content-hash intent_id at the runner
    boundary instead of forwarding the original approved intent_id. Fixed
    by threading intent.get("intent_id") through
    libs/tools/tool_facade.py::ToolFacade.order_execute() (and, for
    consistency, the otherwise-unused libs/tools/tool_schema.py::
    ToolFacade.order_execute()) the same way ExecutorAgent.execute_order()
    already did.

HIGH3 -- two DIFFERENT intent_id values (the automated path's content-hash
    scheme and the manual approval path's uuid4 scheme) can describe the
    SAME real-world physical order (account/symbol/side/order_type/qty/
    price/orig_ord_no). Intent-level ownership alone cannot catch this.
    Fixed by adding a second, independent guard -- libs/supervisor/
    intent_state_store.py::claim_physical_order()/release_physical_order(),
    keyed by libs/execution/intent_identity.py::physical_order_fingerprint()
    -- composed inside execute_owned_order() ahead of the intent-level
    claim.

MEDIUM1 -- an UNKNOWN broker outcome must never be recorded as "executed".
    Fixed as a structural consequence of removing ApprovalService's own
    separate transition: it now reads the canonical intent_state row
    (written solely by execute_owned_order) after execute_fn returns,
    rather than force-writing EXECUTED.

MEDIUM2 -- a relative INTENT_STATE_DB_PATH env value resolved against the
    process's cwd, so two processes with the same relative override but
    different working directories landed on different physical files.
    Fixed in resolve_intent_state_db_path(): a relative explicit path or
    env value is now anchored to the repository root, not cwd.
"""
from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphs.nodes.execute_from_packet import _normalize_execution
from libs.execution.intent_execution_owner import execute_owned_order
from libs.execution.intent_identity import physical_order_fingerprint
from libs.supervisor.intent_state_store import SQLiteIntentStateStore, resolve_intent_state_db_path


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


def _order(iid: str, *, action: str = "BUY", qty=1, price=100, order_type: str = "market",
           orig_ord_no: str = "") -> dict:
    return {"intent_id": iid, "action": action, "symbol": "005930", "qty": qty, "price": price,
            "order_type": order_type, "orig_ord_no": orig_ord_no}


def _authorize(iid: str, *, root=None, **order_kwargs) -> None:
    """Step5C Fix5 (HIGH2, consumer-only claim_execution): a caller-supplied
    intent_id no longer carries execution authority by itself, and
    claim_execution() no longer self-admits ANY approved-but-unadmitted row
    (Fix4's "legacy_approved_state" auto-admission was exactly Codex's
    Fix4-audit HIGH2 finding -- removed outright). Every test in this file
    uses explicit, readable ids to name which logical intent is under test
    (intent-level CAS, physical-order dedup, etc., not
    authoritative-intent-validation itself -- that gets its own dedicated
    coverage in test_step5c_fix3_authoritative_intent.py), so _claim admits
    the id first -- persisted intent + persisted admission bound to the
    SAME canonical physical fingerprint the matching _order(iid, **kwargs)
    would produce -- exactly as ApprovalService.approve()/
    admit_pre_approved_intent/admit_order_intent do in production."""
    from libs.execution.intent_identity import physical_order_fingerprint

    store = SQLiteIntentStateStore(root) if root else SQLiteIntentStateStore()
    key = physical_order_fingerprint({}, _order(iid, **order_kwargs))
    try:
        admitted = store.admit_intent(iid, fingerprint=key, source="test_policy")
        assert admitted.get("admitted") or admitted.get("reason") == "intent_identity_conflict", admitted
    except Exception:
        pass  # tolerate a race with another process also authorizing this id


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


def _manual_args(intent_id: str, *, qty=1, price=100, order_type: str = "market") -> dict:
    return {"side": "buy", "symbol": "005930", "qty": qty, "order_type": order_type, "price": price,
            "intent_id": intent_id}


# --- HIGH1: EXECUTING state alone is never ownership evidence -----------


def test_high1_t1_owner_a_claims_and_dispatches(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex = _SpyExecutor()
    result = _claim(ex, "high1-intent-x")
    assert result["broker_outcome"] == "ACCEPTED"
    assert ex.calls == 1


def test_high1_t2_second_independent_claim_attempt_is_denied(monkeypatch):
    """A second, independent execute_owned_order() call for the SAME
    intent_id -- standing in for "Process B" in Codex's reproduction --
    must be denied even though the intent now genuinely reads EXECUTING
    (then EXECUTED) from Process A's own successful claim."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex_a, ex_b = _SpyExecutor(), _SpyExecutor()
    first = _claim(ex_a, "high1-intent-y")
    assert first["broker_outcome"] == "ACCEPTED"
    second = _claim(ex_b, "high1-intent-y")
    assert second["broker_outcome"] == "NOT_SENT"
    assert ex_b.calls == 0
    assert ex_a.calls == 1


def test_high1_t3_state_reads_executing_with_no_prior_claim_from_this_call_still_denies(tmp_path):
    """Directly reproduces Codex's exact complaint: an intent_id that
    reads EXECUTING (claimed by someone else, e.g. ApprovalService's own
    downstream execute_owned_order call) but this call never itself won
    the CAS -- must never dispatch just because the state VALUE says
    executing."""
    db = tmp_path / "state.db"
    store = SQLiteIntentStateStore(str(db))
    store.ensure_intent("high1-intent-z")
    store.transition(intent_id="high1-intent-z", to_state="approved")
    admitted = store.admit_intent("high1-intent-z", fingerprint="external-fp", source="test_external_owner")
    assert admitted.get("admitted")
    claim = store.claim_execution("high1-intent-z", fingerprint="external-fp", owner="external-owner")
    assert claim["claimed"]
    assert store.get_state("high1-intent-z")["state"] == "executing"

    os.environ["INTENT_STATE_DB_PATH"] = str(db)
    ex = _SpyExecutor()
    result = _claim(ex, "high1-intent-z")
    assert result["broker_outcome"] == "NOT_SENT"
    assert ex.calls == 0


def test_high1_t4_real_multiprocess_same_intent_total_calls_le_1(tmp_path):
    context = multiprocessing.get_context("spawn")
    db = str(tmp_path / "concurrent.db")
    _authorize("high1-multiprocess-shared", root=db)
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_high1_worker, args=(db, barrier, queue)) for _ in range(2)]
    for p in processes:
        p.start()
    for p in processes:
        p.join(30)
        assert p.exitcode == 0
    results = [queue.get(timeout=5) for _ in processes]
    assert sum(calls for calls, _ in results) == 1


def _high1_worker(db, barrier, queue):
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    ex = _SpyExecutor()
    barrier.wait()
    result = _claim(ex, "high1-multiprocess-shared")
    queue.put((ex.calls, result["broker_outcome"]))


# --- HIGH2: real ToolFacade chain preserves original intent_id ----------


def test_high2_t5_toolfacade_chain_preserves_original_intent_id(tmp_path, monkeypatch):
    """End-to-end through the ACTUAL production chain Codex traced:
    ToolFacade.order_place_intent -> approve_intent -> ApprovalService ->
    ToolFacade.order_execute -> CompositeSkillRunner. The original
    intent_id assigned at creation (TwoPhaseSupervisor.create_intent) must
    be the SAME id all the way through approval, execution, and the
    terminal canonical state -- never replaced by a runner-minted
    content-hash identity."""
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
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

    created = facade.order_place_intent(side="buy", symbol="005930", qty=1, order_type="market")
    original_iid = created["decision"]["intent"]["intent_id"]
    assert original_iid

    approved = facade.approve_intent(intent_id=original_iid)
    assert approved["ok"] is True
    assert approved["status"] == "executed"
    assert approved["intent_id"] == original_iid
    assert spy.calls == 1

    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    row = store.get_state(original_iid)
    assert row is not None and row["state"] == "executed"
    # No shadow "intent-v1-..." content-hash identity was ever created for
    # this real order -- the original id is the only one that was claimed.
    assert store.get_owner(original_iid) is not None


def test_high2_t6_replay_same_approved_intent_dispatches_once(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
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

    created = facade.order_place_intent(side="buy", symbol="005930", qty=1, order_type="market")
    iid = created["decision"]["intent"]["intent_id"]
    first = facade.approve_intent(intent_id=iid)
    assert first["status"] == "executed"
    second = facade.approve_intent(intent_id=iid)
    assert second["ok"] is True
    assert second.get("note")  # cached-execution response, not a re-dispatch
    assert spy.calls == 1


def test_high2_t7_unknown_outcome_is_not_recorded_as_executed(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "manual")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)

    from libs.tools.tool_facade import ToolFacade

    facade = ToolFacade(
        catalog=_api_catalog_path(tmp_path),
        event_log=str(tmp_path / "events.jsonl"),
        intent_store=str(tmp_path / "intents.jsonl"),
    )
    facade.runner.executor = _SpyExecutor(outcome="UNKNOWN")

    created = facade.order_place_intent(side="buy", symbol="005930", qty=1, order_type="market")
    iid = created["decision"]["intent"]["intent_id"]
    result = facade.approve_intent(intent_id=iid)

    assert result["ok"] is False
    assert result["status"] == "executing"
    assert result.get("reconciliation_required") is True

    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    row = store.get_state(iid)
    assert row is not None and row["state"] == "executing"
    assert row["state"] != "executed"

    # A second attempt at the same original intent must not replay.
    fresh_spy = _SpyExecutor()
    facade.runner.executor = fresh_spy
    replay = facade.approve_intent(intent_id=iid)
    assert replay["ok"] is False
    assert fresh_spy.calls == 0


# --- HIGH3: different intent_id, same physical order --------------------


def test_high3_t8_different_intent_ids_same_physical_order_concurrent_total_calls_le_1(monkeypatch):
    """Genuine overlap, not mere sequencing: the physical-order lease is
    deliberately released once its owning intent reaches a terminal state
    (see test_high3_later_legitimate_cycle_can_reuse_physical_key_after_
    terminal_state below), so two attempts that never actually overlap in
    time are both legitimately allowed -- that is the explicitly required
    "later legitimate cycle" boundary (section 10), not a bug. This test
    instead forces B's attempt to happen WHILE A's lease is still held
    (inside A's own on_submit callback, before A's finish_execution/release
    has run), which is what "concurrently existing ingress" actually means."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    _authorize("physical-auto-A", action="BUY", qty=10, price=None, order_type="market")
    ex_a, ex_b = _SpyExecutor(), _SpyExecutor()
    captured: dict = {}

    def _b_attempts_while_a_still_holds_the_lease():
        captured["second"] = _claim(ex_b, "physical-manual-B", action="BUY", qty=10, price=None, order_type="market")

    candidate_a = _order("physical-auto-A", action="BUY", qty=10, price=None, order_type="market")
    first = execute_owned_order(
        state={"run_id": "run-a"}, order=candidate_a, request=None, executor=ex_a,
        on_submit=_b_attempts_while_a_still_holds_the_lease,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=candidate_a),
    )
    assert first["broker_outcome"] == "ACCEPTED"
    assert ex_a.calls == 1

    second = captured["second"]
    assert second["broker_outcome"] == "NOT_SENT"
    assert second["reason"] == "physical_order_already_claimed"
    assert ex_b.calls == 0


def _physical_worker_a(db, event_claimed, queue):
    import time as _time
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    ex = _SpyExecutor()

    def _hold_lease_briefly():
        event_claimed.set()
        _time.sleep(0.3)  # keep the physical lease active while B attempts

    candidate = _order("physical-mp-A", action="BUY", qty=10, price=None, order_type="market")
    result = execute_owned_order(
        state={"run_id": "run-mp-a"}, order=candidate, request=None, executor=ex,
        on_submit=_hold_lease_briefly,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=candidate),
    )
    queue.put(("A", ex.calls, result["broker_outcome"]))


def _physical_worker_b(db, event_claimed, queue):
    os.environ["INTENT_STATE_DB_PATH"] = db
    os.environ["EXECUTION_MODE"] = "mock"
    event_claimed.wait(timeout=10)
    ex = _SpyExecutor()
    result = _claim(ex, "physical-mp-B", action="BUY", qty=10, price=None, order_type="market")
    queue.put(("B", ex.calls, result["broker_outcome"]))


def test_high3_t8b_real_multiprocess_different_intents_same_physical_order(tmp_path):
    context = multiprocessing.get_context("spawn")
    db = str(tmp_path / "physical_concurrent.db")
    _authorize("physical-mp-A", root=db, action="BUY", qty=10, price=None, order_type="market")
    _authorize("physical-mp-B", root=db, action="BUY", qty=10, price=None, order_type="market")
    event_claimed, queue = context.Event(), context.Queue()
    processes = [
        context.Process(target=_physical_worker_a, args=(db, event_claimed, queue)),
        context.Process(target=_physical_worker_b, args=(db, event_claimed, queue)),
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(30)
        assert p.exitcode == 0
    results = {label: (calls, outcome) for label, calls, outcome in (queue.get(timeout=5) for _ in processes)}
    assert results["A"] == (1, "ACCEPTED")
    assert results["B"] == (0, "NOT_SENT")


def test_high3_t9_different_qty_are_independent_orders(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex10, ex20 = _SpyExecutor(), _SpyExecutor()
    r10 = _claim(ex10, "qty-10-intent", qty=10, price=None, order_type="market")
    r20 = _claim(ex20, "qty-20-intent", qty=20, price=None, order_type="market")
    assert r10["broker_outcome"] == "ACCEPTED"
    assert r20["broker_outcome"] == "ACCEPTED"
    assert ex10.calls == 1 and ex20.calls == 1


def test_high3_t10_buy_and_sell_are_independent_orders(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex_buy, ex_sell = _SpyExecutor(), _SpyExecutor()
    r_buy = _claim(ex_buy, "buy-intent", action="BUY", qty=10, price=None, order_type="market")
    r_sell = _claim(ex_sell, "sell-intent", action="SELL", qty=10, price=None, order_type="market")
    assert r_buy["broker_outcome"] == "ACCEPTED"
    assert r_sell["broker_outcome"] == "ACCEPTED"
    assert ex_buy.calls == 1 and ex_sell.calls == 1


def test_high3_t11_market_and_limit_are_independent_orders(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex_mkt, ex_lmt = _SpyExecutor(), _SpyExecutor()
    r_mkt = _claim(ex_mkt, "market-intent", qty=10, price=None, order_type="market")
    r_lmt = _claim(ex_lmt, "limit-intent", qty=10, price=70000, order_type="limit")
    assert r_mkt["broker_outcome"] == "ACCEPTED"
    assert r_lmt["broker_outcome"] == "ACCEPTED"
    assert ex_mkt.calls == 1 and ex_lmt.calls == 1


def test_high3_later_legitimate_cycle_can_reuse_physical_key_after_terminal_state(monkeypatch):
    """Section 10's explicit boundary: a genuinely later decision cycle
    (T2) placing "the same" order after T1's attempt has reached a
    terminal outcome must not be blocked forever -- the physical-order
    lease releases on EXECUTED/FAILED (never on an ambiguous outcome)."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex_t1, ex_t2 = _SpyExecutor(), _SpyExecutor()
    t1 = _claim(ex_t1, "cycle-t1-intent", qty=10, price=None, order_type="market")
    assert t1["broker_outcome"] == "ACCEPTED"
    t2 = _claim(ex_t2, "cycle-t2-intent", qty=10, price=None, order_type="market")
    assert t2["broker_outcome"] == "ACCEPTED"
    assert ex_t1.calls == 1 and ex_t2.calls == 1


def test_high3_ambiguous_outcome_does_not_release_physical_lease(monkeypatch):
    """The inverse of the above: an UNKNOWN outcome must NOT release the
    physical-order lease (Option A / fail-closed, no auto-release on
    ambiguity -- reconciliation is Step5D's job, not implemented here)."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    ex_unknown = _SpyExecutor(outcome="UNKNOWN")
    first = _claim(ex_unknown, "ambiguous-intent", qty=10, price=None, order_type="market")
    assert first["broker_outcome"] == "UNKNOWN"
    ex_retry = _SpyExecutor()
    second = _claim(ex_retry, "ambiguous-intent-retry", qty=10, price=None, order_type="market")
    assert second["broker_outcome"] == "NOT_SENT"
    assert second["reason"] == "physical_order_already_claimed"
    assert ex_retry.calls == 0


# --- item 22: child CANCEL ownership + non-collision with original order --


def test_child_cancel_ownership_and_no_physical_collision_with_original_buy(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    original_order = {"intent_id": "", "action": "BUY", "symbol": "005930", "qty": 10, "price": None,
                       "order_type": "market", "orig_ord_no": ""}
    ex_buy = _SpyExecutor()
    buy_state = {"run_id": "cancel-flow-run"}
    from libs.execution.intent_admission import admit_order_intent
    admit_order_intent(state=buy_state, order=original_order, source="test_buy")
    buy_result = execute_owned_order(state=buy_state, order=original_order, request=None, executor=ex_buy,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=original_order))
    assert buy_result["broker_outcome"] == "ACCEPTED"
    assert ex_buy.calls == 1

    cancel_order = {"action": "CANCEL", "symbol": "005930", "orig_ord_no": "0099001", "cncl_qty": 10}
    admit_order_intent(state=buy_state, order=cancel_order, source="test_cancel", child=True)
    ex_cancel_a = _SpyExecutor()
    cancel_first = execute_owned_order(state=buy_state, order=dict(cancel_order), request=None, executor=ex_cancel_a,
        child=True, normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=cancel_order))
    assert cancel_first["broker_outcome"] == "ACCEPTED"
    assert ex_cancel_a.calls == 1  # the CANCEL's own physical key never collided with the BUY's

    ex_cancel_b = _SpyExecutor()
    cancel_dup = execute_owned_order(state=dict(buy_state), order=dict(cancel_order), request=None, executor=ex_cancel_b,
        child=True, normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=cancel_order))
    assert cancel_dup["broker_outcome"] == "NOT_SENT"
    assert ex_cancel_b.calls == 0  # a duplicate CANCEL attempt for the same original order is blocked


# --- item 14/15: relative INTENT_STATE_DB_PATH is repo-root anchored ----


def test_relative_env_override_is_repo_root_anchored_not_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from libs.supervisor.intent_state_store import resolve_intent_state_db_path\n"
        "print(resolve_intent_state_db_path())\n"
    ) % str(repo_root)
    env = dict(os.environ)
    env["INTENT_STATE_DB_PATH"] = "env/intent_relative.db"
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("TRADING_AGENT_PYTEST", None)
    cwd_a = tmp_path / "cwd_a"
    cwd_b = tmp_path / "cwd_b" / "nested"
    cwd_a.mkdir()
    cwd_b.mkdir(parents=True)
    out_a = subprocess.run([sys.executable, "-c", script], cwd=str(cwd_a), env=env,
                            capture_output=True, text=True, timeout=30)
    out_b = subprocess.run([sys.executable, "-c", script], cwd=str(cwd_b), env=env,
                            capture_output=True, text=True, timeout=30)
    assert out_a.returncode == 0, out_a.stderr
    assert out_b.returncode == 0, out_b.stderr
    resolved_a, resolved_b = out_a.stdout.strip(), out_b.stdout.strip()
    assert resolved_a == resolved_b == str(repo_root / "env" / "intent_relative.db")


def test_explicit_absolute_path_used_as_is(tmp_path):
    absolute = tmp_path / "absolute_intent_state.db"
    resolved = resolve_intent_state_db_path(str(absolute))
    assert resolved == absolute.resolve()


# --- item 16: runner refuses a mutation with no canonical intent_id -----


def test_runner_refuses_mutation_with_missing_intent_id_rather_than_inventing_one(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    args = _manual_args("")  # explicitly no canonical identity supplied
    result = runner.run(run_id="run-1", skill="order.place", args=args)
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "missing_canonical_intent_identity"
    assert ex.calls == 0
