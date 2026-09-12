"""Step5C Fix1 -- shared ownership authority across execution paths.

Codex's independent Red-Team audit of 342060f found that the new
libs/execution/intent_execution_owner.py CAS layer only covered the
automated graphs/nodes/execute_from_packet.py path. A second, independent
live mutation path -- scripts/approval_cli.py -> ToolFacade.approve_intent
-> ExecutorAgent.approve -> ApprovalService.approve -> ExecutorAgent.
execute_order -> CompositeSkillRunner.run("order.place") ->
executor.execute() -- never went through execute_owned_order()/bind_intent()
at all, AND (independently) defaulted to a *different* SQLite file
(data/logs/intents.db) than the automated path's canonical
data/state/intent_state.db whenever INTENT_STATE_DB_PATH was unset --
verified empirically, not merely asserted. Either gap alone means "same
logical OrderIntent -> exactly one execution owner" cannot be claimed
system-wide.

Fix1 closes this two ways:
  1. A single canonical resolver (SQLiteIntentStateStore's own default /
     libs.supervisor.intent_state_store.resolve_intent_state_db_path) is
     now the only source of the default DB path for every consumer
     (intent_execution_owner, ApprovalService, and this store's own
     no-argument default), anchored to the repository root so it is
     working-directory independent in production.
  2. libs/skills/runner.py's mutation dispatch now checks for a
     pre-established canonical EXECUTING claim (e.g. one already made by
     ApprovalService.approve()'s own approved->executing CAS, which is
     left untouched and now shares the same canonical database) and,
     failing that, claims one itself via execute_owned_order() before
     ever calling the executor -- closing the APPROVAL_MODE=auto path
     (submit_order_intent -> execute_order directly, which never goes
     through ApprovalService.approve() at all) and any other caller that
     reaches this runner without prior ownership.

These tests reproduce the exact gaps first (would fail against the
pre-Fix1 code), then verify they are closed.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from graphs.nodes.execute_from_packet import _normalize_execution
from libs.execution.intent_execution_owner import execute_owned_order
from libs.supervisor.intent_state_store import (
    INTENT_STATE_EXECUTING,
    SQLiteIntentStateStore,
    resolve_intent_state_db_path,
)


# --- shared helpers -----------------------------------------------------


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


def _api_catalog_path(tmp_path: Path) -> str:
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


def _manual_mutation_args(intent_id: str = "", price=None) -> dict:
    return {"side": "buy", "symbol": "005930", "qty": 1, "order_type": "market", "price": price,
            "intent_id": intent_id}


def _order(iid: str, action: str = "BUY") -> dict:
    return {"intent_id": iid, "action": action, "symbol": "005930", "qty": 1, "price": 100, "order_type": "market"}


def _automatic_claim(executor, iid: str) -> dict:
    """Simulates graphs/nodes/execute_from_packet.py's use of the owner adapter."""
    candidate = _order(iid)
    return execute_owned_order(state={"run_id": "auto-run"}, order=candidate, request=None,
        executor=executor, normalize=lambda r: _normalize_execution(
            allowed=True, execution_result=r, allow_result=None, order=candidate))


def _authorize(iid: str, *, root=None) -> None:
    """Step5C Fix5 (HIGH2, consumer-only claim_execution): a caller-supplied
    intent_id no longer carries execution authority by itself, and
    claim_execution() no longer self-admits ANY approved-but-unadmitted row
    (Fix4's "legacy_approved_state" auto-admission was exactly Codex's
    Fix4-audit HIGH2 finding -- removed outright). These cross-path tests
    use explicit, human-readable ids to make which "logical order" is
    racing which obvious; this helper admits that id -- persisted intent +
    persisted admission bound to the SAME canonical physical fingerprint
    _order(iid) would produce -- exactly as ApprovalService.approve()/
    admit_pre_approved_intent/admit_order_intent do in production, so the
    test still exercises intent-level CAS/physical-order contention rather
    than tripping the (separately, directly tested)
    authoritative-intent-validation gate."""
    from libs.execution.intent_identity import physical_order_fingerprint

    store = SQLiteIntentStateStore(root) if root else SQLiteIntentStateStore()
    key = physical_order_fingerprint({}, _order(iid))
    admitted = store.admit_intent(iid, fingerprint=key, source="test_policy")
    assert admitted.get("admitted"), admitted


# --- 1. canonical DB authority -------------------------------------------


def test_fix1_canonical_resolver_shared_by_all_consumers(monkeypatch, tmp_path):
    from libs.approval.service import ApprovalService
    from libs.execution.intent_execution_owner import _store as owner_store
    from libs.supervisor.intent_store import IntentStore

    monkeypatch.delenv("INTENT_STATE_DB_PATH", raising=False)
    # conftest.py's autouse isolation fixture normally sets
    # INTENT_STATE_DB_PATH per test; this test explicitly clears it to
    # exercise the *default* resolver all three consumers now share.
    approval = ApprovalService(IntentStore(str(tmp_path / "intents.jsonl")))
    owner_path = owner_store().path
    generic_path = SQLiteIntentStateStore().path
    assert approval.state_store is not None
    assert approval.state_store.path == owner_path == generic_path


def test_fix1_explicit_env_override_still_wins_for_every_consumer(monkeypatch, tmp_path):
    from libs.approval.service import ApprovalService
    from libs.execution.intent_execution_owner import _store as owner_store
    from libs.supervisor.intent_store import IntentStore

    override = tmp_path / "custom_intent_state.db"
    monkeypatch.setenv("INTENT_STATE_DB_PATH", str(override))
    approval = ApprovalService(IntentStore(str(tmp_path / "intents.jsonl")))
    assert approval.state_store.path == owner_store().path == override.resolve()


def test_fix1_cwd_independent_default_path(tmp_path):
    """The production (non-pytest) default must be an absolute,
    repo-root-anchored path -- not a bare relative literal that would
    resolve differently depending on the caller's working directory. Run
    in a real subprocess (so running_under_pytest() is False, matching
    production) from two different working directories."""
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from libs.supervisor.intent_state_store import resolve_intent_state_db_path\n"
        "print(resolve_intent_state_db_path())\n"
    ) % str(repo_root)
    env = dict(os.environ)
    env.pop("INTENT_STATE_DB_PATH", None)
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
    assert resolved_a == resolved_b
    assert resolved_a == str(repo_root / "data" / "state" / "intent_state.db")


# --- 2. cross-path duplicate: automated vs manual, same intent_id -------


def test_fix1_automatic_first_blocks_manual_replay(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    iid = "cross-path-one"
    _authorize(iid)
    auto_ex = _SpyExecutor()
    first = _automatic_claim(auto_ex, iid)
    assert first["broker_outcome"] == "ACCEPTED"
    assert auto_ex.calls == 1

    manual_ex = _SpyExecutor()
    runner = _runner(tmp_path, manual_ex)
    result = runner.run(run_id="manual-run", skill="order.place", args=_manual_mutation_args(iid, price=100))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "intent_already_owned_or_not_approved"
    assert manual_ex.calls == 0  # TOTAL broker mutation for this logical intent stays 1


def test_fix1_manual_first_blocks_automatic_replay(tmp_path):
    iid = "cross-path-two"
    _authorize(iid)
    manual_ex = _SpyExecutor()
    runner = _runner(tmp_path, manual_ex)
    result = runner.run(run_id="manual-run", skill="order.place", args=_manual_mutation_args(iid, price=100))
    assert result.action == "ready"
    assert manual_ex.calls == 1

    auto_ex = _SpyExecutor()
    second = _automatic_claim(auto_ex, iid)
    assert second["broker_outcome"] == "NOT_SENT"
    assert auto_ex.calls == 0  # TOTAL broker mutation for this logical intent stays 1


def _cross_process_auto_worker(db_path, catalog_path, barrier_, queue_):
    os.environ["INTENT_STATE_DB_PATH"] = db_path
    os.environ["EXECUTION_MODE"] = "mock"
    ex = _SpyExecutor()
    barrier_.wait()
    result = _automatic_claim(ex, "cross-process-shared")
    queue_.put(("auto", ex.calls, result["broker_outcome"]))


def _cross_process_manual_worker(db_path, catalog_path, barrier_, queue_):
    os.environ["INTENT_STATE_DB_PATH"] = db_path
    os.environ["EXECUTION_MODE"] = "mock"
    from libs.core.settings import Settings
    from libs.skills.runner import CompositeSkillRunner

    r = CompositeSkillRunner(settings=Settings.from_env(env_path="__missing__.env"),
                              catalog_path=catalog_path, event_log_path=db_path + ".events.jsonl")
    ex = _SpyExecutor()
    r.executor = ex
    barrier_.wait()
    result = r.run(run_id="manual-proc", skill="order.place",
                    args=_manual_mutation_args("cross-process-shared", price=100))
    queue_.put(("manual", ex.calls, result.action))


def test_fix1_real_multiprocess_cross_path(tmp_path):
    """Two real OS processes racing the SAME intent_id on the canonical
    DB -- one taking the automated-path shape (execute_owned_order
    directly), the other taking the manual-path shape (CompositeSkillRunner's
    own self-claim branch, exercised the same way APPROVAL_MODE=auto would
    reach it). Total physical dispatch across both must be exactly 1."""
    context = multiprocessing.get_context("spawn")
    db = str(tmp_path / "cross_process.db")
    catalog = _api_catalog_path(tmp_path)
    _authorize("cross-process-shared", root=db)
    barrier, queue = context.Barrier(2), context.Queue()

    processes = [
        context.Process(target=_cross_process_auto_worker, args=(db, catalog, barrier, queue)),
        context.Process(target=_cross_process_manual_worker, args=(db, catalog, barrier, queue)),
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(30)
        assert p.exitcode == 0
    results = [queue.get(timeout=5) for _ in processes]
    total_calls = sum(calls for _, calls, _ in results)
    assert total_calls == 1


# --- 3. manual path ownership absent / duplicate -------------------------


def test_fix1_manual_path_claims_when_prior_ownership_authorized(tmp_path):
    """APPROVAL_MODE=auto reaches CompositeSkillRunner directly, with no
    prior ApprovalService.approve() CAS -- but (Step5C Fix3, superseding
    this test's original Fix1-era premise) a caller-supplied intent_id no
    longer carries execution authority by itself, so the runner claims
    successfully here only because the intent was explicitly persisted as
    approved first (exactly what ExecutorAgent.submit_order_intent's own
    auto-mode branch now does via ApprovalService.admit_pre_approved_intent
    -- see test_step5c_fix2_ownership_capability.py /
    test_step5c_fix3_authoritative_intent.py for the "no prior
    authorization -> broker 0" case this used to (incorrectly) not test)."""
    _authorize("auto-mode-intent")
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    result = runner.run(run_id="auto-mode-run", skill="order.place", args=_manual_mutation_args("auto-mode-intent"))
    assert result.action == "ready"
    assert ex.calls == 1
    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    assert store.get_state("auto-mode-intent")["state"] == "executed"


def test_fix1_manual_path_duplicate_second_call_zero_broker(tmp_path):
    _authorize("manual-dup-intent")
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    args = _manual_mutation_args("manual-dup-intent")
    first = runner.run(run_id="run-1", skill="order.place", args=args)
    second = runner.run(run_id="run-2", skill="order.place", args=args)
    assert first.action == "ready"
    assert second.action == "error"
    assert second.meta.get("blocked_reason") == "intent_already_owned_or_not_approved"
    assert ex.calls == 1


def test_fix1_manual_path_db_unavailable_zero_broker(monkeypatch, tmp_path):
    monkeypatch.setenv("INTENT_STATE_DB_PATH", str(tmp_path))  # a directory, not a file -- forces failure
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_mutation_args("db-down-intent"))
    assert result.action == "error"
    assert ex.calls == 0


def test_fix1_manual_path_payload_mismatch_blocked(tmp_path):
    iid = "payload-mismatch-intent"
    _authorize(iid)
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    first = runner.run(run_id="run-1", skill="order.place", args=_manual_mutation_args(iid))
    assert first.action == "ready"
    # Same intent_id, different qty -- must be treated as an identity
    # conflict, not a plain duplicate, and must never re-dispatch.
    mismatched_args = dict(_manual_mutation_args(iid), qty=99)
    second = runner.run(run_id="run-2", skill="order.place", args=mismatched_args)
    assert second.action == "error"
    # Step5C Fix5: the admitted payload's fingerprint is checked before the
    # approval-state check, so a payload change under one intent_id is
    # PAYLOAD_MISMATCH even once the first attempt has already reached a
    # terminal state.
    assert second.meta.get("blocked_reason") == "PAYLOAD_MISMATCH"
    assert ex.calls == 1


# --- 4. end-to-end: APPROVAL_MODE=auto via the real ExecutorAgent -------


def _make_agent(tmp_path: Path):
    from libs.core.settings import Settings
    from libs.skills.runner import CompositeSkillRunner
    from libs.agent.executor.executor_agent import ExecutorAgent
    from libs.supervisor.intent_store import IntentStore
    from libs.supervisor.two_phase import TwoPhaseSupervisor

    store_path = tmp_path / "intents.jsonl"
    store = IntentStore(str(store_path))
    settings = Settings.from_env()
    sup = TwoPhaseSupervisor(settings)
    runner = CompositeSkillRunner.from_env()
    return ExecutorAgent(runner=runner, supervisor=sup, intent_store=store, intent_store_path=store_path)


def test_fix1_approval_mode_auto_duplicate_submission_dispatches_once(monkeypatch, tmp_path):
    """submit_order_intent(approval_mode="auto", execution_enabled=True)
    calls execute_order() directly, entirely bypassing
    ApprovalService.approve()'s own CAS -- reproduces the exact gap Codex's
    audit flagged (no canonical ownership claim on this path pre-Fix1).
    Two independent OrderIntents for the "same" order (each gets its own
    Supervisor-assigned intent_id, since large-scale identity redesign is
    out of scope for Fix1) each dispatch once -- the invariant this test
    protects is that a single such intent, even reached without prior
    approval-service gating, is claimed and cannot double-dispatch if
    resubmitted with its own already-used intent_id."""
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("APPROVAL_MODE", "auto")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    monkeypatch.delenv("MAX_ORDER_NOTIONAL", raising=False)
    monkeypatch.delenv("MAX_NOTIONAL", raising=False)
    monkeypatch.delenv("MAX_ORDER_QTY", raising=False)
    monkeypatch.delenv("MAX_QTY", raising=False)

    agent = _make_agent(tmp_path)
    res = agent.submit_order_intent(side="buy", symbol="005930", qty=1, order_type="market",
        approval_mode="auto", execution_enabled=True, rationale="fix1 auto-mode test")
    assert "execution" in res
    iid = res["decision"]["intent"]["intent_id"]
    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    row = store.get_state(iid)
    assert row is not None and row["state"] in ("executed", "failed")

    # Resubmitting execute_order directly with the SAME already-assigned
    # intent_id (e.g. a naive retry of the same OrderIntent object) must
    # not dispatch a second time.
    replay = agent.execute_order(intent=res["decision"]["intent"])
    assert replay.get("action") == "error"
    assert replay.get("meta", {}).get("blocked_reason") == "intent_already_owned_or_not_approved"
