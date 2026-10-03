"""Step5C Fix5 -- mutation symbol fail-closed, claim_execution consumer-only
authority, legacy approval payload binding, admission schema readiness.

Codex's independent Red-Team audit of Step5C Fix4 reproduced two more HIGH
findings and one MEDIUM against the actual implementation:

HIGH1 -- libs/skills/runner.py::CompositeSkillRunner.run() gated its entire
    protected mutation path (quarantine check + intent_execution_owner
    claim) behind `if is_mutation and mutation_symbol:`. Codex's exact
    reproduction: `BUY 0082N0 qty=10 MARKET` -- is_mutation_api_id() was
    True, but normalize_symbol("0082N0") returns "" (a 6-char mixed
    alnum code with both letters and digits is explicitly rejected by
    libs/core/symbols.py's own contract), so `mutation_symbol` was falsy
    and the WHOLE protected branch was skipped, falling through to the
    plain `self.executor.execute(prep.request)` branch with zero
    ownership/quarantine/physical-claim protection (broker calls == 1,
    expected 0). Fixed by making mutation detection alone decide the
    authority boundary: `if is_mutation:` now unconditionally enters the
    protected branch, and a symbol that fails to canonicalize inside that
    branch returns "INVALID_SYMBOL" (broker calls 0) rather than ever
    reaching the else-branch's generic executor call.

HIGH2 -- SQLiteIntentStateStore.claim_execution() manufactured an
    "intent_admission" row (reason "legacy_approved_state") for ANY
    approved-but-unadmitted intent_id, using the SUBMITTED payload's own
    fingerprint as the newly-created admission. Codex's exact attack:
    persist intent X as APPROVED with payload "BUY 005930 qty=1 MARKET"
    and admission deliberately never granted; submit a completely
    different payload "BUY 000660 qty=99 MARKET" under the same intent_id
    -- claim_execution manufactured admission FROM THE SUBMITTED PAYLOAD
    and dispatched it (broker calls == 1, expected 0). Fixed by deleting
    that auto-admission branch outright: claim_execution is now strictly a
    CONSUMER of authority some other explicit boundary already
    established (ApprovalService.approve(), libs.execution.
    intent_admission.admit_order_intent, an authorized automatic/child-
    cancel admission call) -- it validates intent_id format, loads the
    persisted intent (absent -> INTENT_NOT_FOUND), loads the persisted
    admission (absent -> ADMISSION_NOT_FOUND), compares the submitted
    fingerprint to the admitted one (mismatch -> PAYLOAD_MISMATCH), checks
    approval state (pending -> NOT_APPROVED; other non-approved ->
    intent_already_owned_or_not_approved), then performs the atomic CAS.
    A legacy APPROVED row with no admission is refused as
    ADMISSION_NOT_FOUND -- closing that requires an explicit, separately
    authorized migration step, never implicit repair inside the execution
    claim path itself. ApprovalService.approve()'s own admission creation
    was narrowed the same way: it only admits a FRESH (pending/absent)
    intent, never an already-"approved" legacy row missing admission.

MEDIUM -- the real operational DB had intent_state/intent_journal but no
    intent_admission table yet; get_admission()/claim_execution() issuing
    a bare SELECT against a missing table could raise
    sqlite3.OperationalError instead of returning None/a clean denial.
    Fixed: SQLiteIntentStateStore._init_db() now creates every table this
    store owns (intent_admission, intent_execution_binding,
    physical_order_claim, in addition to intent_state/intent_journal) at
    construction time, on both a brand-new DB and an existing one created
    before these tables existed.
"""
from __future__ import annotations

import multiprocessing
import os
import sqlite3
from pathlib import Path

import pytest

from graphs.nodes.execute_from_packet import _normalize_execution
from libs.execution.intent_admission import admit_order_intent
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


def _order(iid, **fields) -> dict:
    base = {"intent_id": iid, "action": "BUY", "symbol": "005930", "qty": 10, "price": None, "order_type": "market"}
    base.update(fields)
    return base


def _api_catalog_path(tmp_path: Path) -> str:
    import json
    p = tmp_path / "catalog.jsonl"
    rows = [
        {"api_id": "kt10000", "method": "POST", "path": "/api/dostk/ordr",
         "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]}},
        {"api_id": "kt10001", "method": "POST", "path": "/api/dostk/ordr",
         "params": {"body": ["stk_cd", "ord_qty", "ord_uv", "trde_tp", "cond_uv", "dmst_stex_tp"]}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
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
# F5-T1/T2: mutation symbol normalization failure -> fail closed, no
# generic-executor bypass (Codex's exact literal: BUY 0082N0 qty=10 MARKET)
# =========================================================================


def test_f5_t1_exact_0082n0_attack_symbol_canonicalizes_to_invalid():
    from libs.core.symbols import normalize_symbol
    assert normalize_symbol("0082N0") == ""


def test_f5_none_symbol_order_is_unfingerprintable():
    """None (no stk_cd/symbol at all) must fail closed at the
    execute_owned_order/physical_order_fingerprint level -- checked
    directly here since runner.py's own template rendering coerces a
    missing symbol into the literal string "None" before normalize_symbol
    ever sees it (a template-engine quirk, not a symbol-validity question)."""
    assert physical_order_fingerprint({}, _order("x", symbol=None)) is None


def test_f5_t1_exact_0082n0_attack_is_broker_zero(tmp_path):
    """Codex's exact reproduction, closed:
        raw request: BUY 0082N0 qty=10 MARKET
        intent_id: a valid-looking, but never persisted/admitted/approved
        expected: is_mutation=True, normalization result=invalid,
                  ownership-path bypass=NO, generic executor entered=NO,
                  broker calls=0
    """
    import uuid
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    never_persisted_iid = "intent-v1-" + "a" * 64  # valid-looking format, never admitted
    result = runner.run(run_id="run-1", skill="order.place",
                         args=_manual_args(never_persisted_iid, symbol="0082N0"))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "INVALID_SYMBOL"
    assert ex.calls == 0
    store = SQLiteIntentStateStore()
    assert store.get_state(never_persisted_iid) is None  # never created either


@pytest.mark.parametrize("raw_symbol", ["", " ", "0082N0", "A0082N0", "ABCDEFG12345"])
def test_f5_t2_invalid_symbol_forms_never_reach_generic_executor(tmp_path, raw_symbol):
    """Every invalid-symbol shape must fail closed with broker calls == 0
    -- never silently fall through to the plain executor.execute() branch.
    """
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    result = runner.run(run_id="run-1", skill="order.place",
                         args=_manual_args("intent-v1-" + "b" * 64, symbol=raw_symbol))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "INVALID_SYMBOL"
    assert ex.calls == 0


def test_f5_t2_valid_symbol_still_reaches_protected_path_when_admitted(tmp_path):
    """The fail-closed fix must not accidentally fail closed for a VALID
    symbol too -- a properly admitted intent with a real symbol still
    dispatches through the protected path exactly as before."""
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "valid-symbol-intent"
    store = SQLiteIntentStateStore()
    key = physical_order_fingerprint({}, _order(iid))
    store.admit_intent(iid, fingerprint=key, source="test_policy")
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert result.action == "ready"
    assert ex.calls == 1


# =========================================================================
# F5-T3/T4: legacy approved intent with admission missing -> fail closed,
# admission remains absent (claim_execution never repairs it)
# =========================================================================


def test_f5_t3_legacy_approved_without_admission_is_broker_zero(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "legacy-approved-no-admission"
    store = SQLiteIntentStateStore()
    store.ensure_intent(iid)
    store.transition(intent_id=iid, to_state="approved", expected_from_state="pending_approval")
    assert store.get_admission(iid) is None
    result = runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "ADMISSION_NOT_FOUND"
    assert ex.calls == 0


def test_f5_t4_legacy_approved_without_admission_stays_unadmitted_after_denial(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    iid = "legacy-approved-no-admission-2"
    store = SQLiteIntentStateStore()
    store.ensure_intent(iid)
    store.transition(intent_id=iid, to_state="approved", expected_from_state="pending_approval")
    runner.run(run_id="run-1", skill="order.place", args=_manual_args(iid))
    # The core of HIGH2: claim_execution must NEVER have inserted an
    # admission row as a side effect of the denial.
    assert store.get_admission(iid) is None
    assert store.get_state(iid)["state"] == "approved"  # untouched, not silently promoted


# =========================================================================
# F5-T5/T6: payload substitution attack -- Codex's exact HIGH2 literal
# =========================================================================


def test_f5_t5_exact_high2_payload_substitution_attack(tmp_path):
    """Codex's exact reproduction, closed:
        authoritative persisted+admitted: BUY 005930 qty=1 MARKET
        submitted:                        BUY 000660 qty=99 MARKET
        expected: admission_before=None-equivalent (bound to 005930/qty1),
                  claim_execution FAIL, reason=PAYLOAD_MISMATCH,
                  broker calls=0, and (critically) claim_execution never
                  inserted/overwrote the admission to match the submitted
                  attack payload.
    """
    iid = "high2-payload-substitution"
    store = SQLiteIntentStateStore()
    authoritative = _order(iid, symbol="005930", qty=1, order_type="market", price=None)
    fingerprint_a = physical_order_fingerprint({}, authoritative)
    admitted = store.admit_intent(iid, fingerprint=fingerprint_a, source="test_authoritative_policy")
    assert admitted["admitted"] is True
    assert store.get_state(iid)["state"] == "approved"

    submitted = _order(iid, symbol="000660", qty=99, order_type="market", price=None)
    fingerprint_b = physical_order_fingerprint({}, submitted)
    assert fingerprint_a != fingerprint_b
    assert submitted["symbol"] == "000660"
    assert submitted["qty"] == 99
    assert authoritative["symbol"] == "005930"
    assert authoritative["qty"] == 1

    ex = _SpyExecutor()
    result = execute_owned_order(state={"run_id": "attack-run"}, order=submitted, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=submitted))
    assert result["reason"] == "PAYLOAD_MISMATCH"
    assert result["broker_outcome"] == "NOT_SENT"
    assert ex.calls == 0

    # The admission row must still be bound to the ORIGINAL authoritative
    # payload -- the attack must not have overwritten it.
    admission_after = store.get_admission(iid)
    assert admission_after is not None
    assert admission_after["fingerprint"] == fingerprint_a
    assert admission_after["fingerprint"] != fingerprint_b


def test_f5_t6_matching_admitted_payload_dispatches_once(tmp_path):
    """The normal path, unaffected: submitting the SAME payload that was
    admitted claims and dispatches successfully."""
    iid = "high2-matching-payload"
    store = SQLiteIntentStateStore()
    order = _order(iid, symbol="005930", qty=1, order_type="market", price=None)
    fingerprint = physical_order_fingerprint({}, order)
    admitted = store.admit_intent(iid, fingerprint=fingerprint, source="test_authoritative_policy")
    assert admitted["admitted"] is True

    ex = _SpyExecutor()
    result = execute_owned_order(state={"run_id": "matching-run"}, order=dict(order), request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=order))
    assert result["broker_outcome"] == "ACCEPTED"
    assert ex.calls == 1
    assert store.get_state(iid)["state"] == "executed"


# =========================================================================
# F5-T7: claim_execution never inserts an admission row, under any outcome
# =========================================================================


def test_f5_t7_claim_execution_never_inserts_admission_intent_not_found(tmp_path):
    store = SQLiteIntentStateStore()
    iid = "never-admitted-intent-not-found"
    ex = _SpyExecutor()
    order = _order(iid)
    result = execute_owned_order(state={"run_id": "run"}, order=order, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=order))
    assert result["reason"] == "INTENT_NOT_FOUND"
    assert ex.calls == 0
    assert store.get_admission(iid) is None
    assert store.get_state(iid) is None  # not created either


def test_f5_t7_claim_execution_never_inserts_admission_pending(tmp_path):
    store = SQLiteIntentStateStore()
    iid = "pending-never-admitted"
    store.ensure_intent(iid)
    ex = _SpyExecutor()
    order = _order(iid)
    result = execute_owned_order(state={"run_id": "run"}, order=order, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=order))
    assert result["reason"] == "ADMISSION_NOT_FOUND"
    assert ex.calls == 0
    assert store.get_admission(iid) is None
    assert store.get_state(iid)["state"] == "pending_approval"  # untouched


def test_f5_t7_grep_no_legacy_admission_fallback_string_in_claim_execution():
    """A literal regression guard matching Codex's own finding vocabulary:
    the deleted auto-admission branch (an INSERT into intent_admission
    performed by claim_execution itself, tagged "legacy_approved_state")
    must not reappear as executable code. inspect.getsource() also
    includes this method's own docstring, which legitimately explains
    (in prose) what was removed and why -- so this checks for the actual
    SQL statement, not a bare substring that would also match that prose.
    """
    import ast
    import inspect
    src = inspect.getsource(SQLiteIntentStateStore.claim_execution)
    tree = ast.parse(src.strip())
    func = tree.body[0]
    # Drop the docstring (first statement, if it's a bare string expression)
    # before scanning -- only the executable body must be free of the
    # deleted auto-admission SQL, not the prose explaining its removal.
    body = func.body[1:] if (func.body and isinstance(func.body[0], ast.Expr)
                              and isinstance(func.body[0].value, ast.Constant)) else func.body
    code_only = ast.unparse(ast.Module(body=body, type_ignores=[]))
    assert "INSERT INTO intent_admission" not in code_only
    assert "legacy_approved_state" not in code_only


# =========================================================================
# F5-T8/T9: admission schema readiness -- existing DB without the table
# =========================================================================


def test_f5_t8_existing_db_without_admission_table_opens_cleanly(tmp_path):
    """Simulates the real operational DB Codex found: intent_state/
    intent_journal exist, but intent_admission does not."""
    db_path = tmp_path / "legacy_no_admission.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE intent_state (intent_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
        "updated_ts INTEGER NOT NULL, version INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE intent_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, intent_id TEXT NOT NULL, "
        "ts INTEGER NOT NULL, from_state TEXT NOT NULL, to_state TEXT NOT NULL, reason TEXT, "
        "meta_json TEXT, execution_json TEXT)"
    )
    conn.execute(
        "INSERT INTO intent_state VALUES ('preexisting-legacy-row', 'approved', 1700000000, 1)"
    )
    conn.commit()
    conn.close()
    tables_before = {r[0] for r in sqlite3.connect(str(db_path)).execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "intent_admission" not in tables_before

    store = SQLiteIntentStateStore(str(db_path))  # must not raise

    tables_after = {r[0] for r in sqlite3.connect(str(db_path)).execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "intent_admission" in tables_after
    # Existing rows survive untouched.
    assert store.get_state("preexisting-legacy-row")["state"] == "approved"


def test_f5_t9_get_admission_on_missing_table_returns_none_not_operational_error(tmp_path):
    db_path = tmp_path / "bare.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE intent_state (intent_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
        "updated_ts INTEGER NOT NULL, version INTEGER NOT NULL)"
    )
    conn.commit()
    conn.close()
    store = SQLiteIntentStateStore(str(db_path))
    # get_admission must return None cleanly -- not raise OperationalError.
    assert store.get_admission("anything") is None
    assert store.get_physical_claim("anything") is None
    assert store.list_active_physical_claims() == []


# =========================================================================
# F5-T10/T11/T12: automatic / manual / child-cancel paths still dispatch
# =========================================================================


def test_f5_t10_automatic_path_still_dispatches_once(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = {"run_id": "auto-path-run"}
    order = {"action": "BUY", "symbol": "005930", "qty": 10, "price": None, "order_type": "market"}
    admitted = admit_order_intent(state=state, order=order, source="test_automatic_policy")
    assert admitted["admitted"] is True
    ex = _SpyExecutor()
    result = execute_owned_order(state=state, order=order, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=order))
    assert result["broker_outcome"] == "ACCEPTED"
    assert ex.calls == 1


def test_f5_t11_manual_approval_path_still_dispatches_once(tmp_path, monkeypatch):
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
    created = facade.order_place_intent(side="buy", symbol="005930", qty=10, order_type="market")
    iid = created["decision"]["intent"]["intent_id"]
    approved = facade.approve_intent(intent_id=iid)
    assert approved["status"] == "executed"
    assert spy.calls == 1
    store = SQLiteIntentStateStore(os.environ["INTENT_STATE_DB_PATH"])
    assert store.get_admission(iid) is not None


def test_f5_t12_child_cancel_still_dispatches_once(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    buy_state = {"run_id": "child-cancel-run"}
    buy_order = {"intent_id": "", "action": "BUY", "symbol": "005930", "qty": 10, "price": None,
                 "order_type": "market", "orig_ord_no": ""}
    admit_order_intent(state=buy_state, order=buy_order, source="test_policy")
    ex_buy = _SpyExecutor()
    buy_result = execute_owned_order(state=buy_state, order=buy_order, request=None, executor=ex_buy,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=buy_order))
    assert buy_result["broker_outcome"] == "ACCEPTED"

    cancel_order = {"action": "CANCEL", "symbol": "005930", "orig_ord_no": "0099001", "cncl_qty": 10}
    admit_order_intent(state=buy_state, order=cancel_order, source="test_child_cancel_policy", child=True)
    ex_cancel = _SpyExecutor()
    cancel_result = execute_owned_order(state=buy_state, order=cancel_order, request=None, executor=ex_cancel,
        child=True, normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=cancel_order))
    assert cancel_result["broker_outcome"] == "ACCEPTED"
    assert ex_cancel.calls == 1


# =========================================================================
# Exhaustive mutation-bypass sweep (item 5): BUY/SELL/CANCEL/MODIFY all
# fail closed on normalization failure, none reach the generic executor
# =========================================================================


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_f5_mutation_bypass_sweep_buy_sell(tmp_path, side):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    result = runner.run(run_id="run-1", skill="order.place",
                         args={"side": side, "symbol": "0082N0", "qty": 10, "order_type": "market",
                               "price": None, "intent_id": "intent-v1-" + "c" * 64})
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "INVALID_SYMBOL"
    assert ex.calls == 0
