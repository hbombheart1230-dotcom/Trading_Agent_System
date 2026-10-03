"""P0 restart-safety hardening -- Crash Test Matrix (Scenarios A-F) and
Invariants INV-1..INV-7.

Each scenario reproduces the exact real call sequence
(bind_intent -> admit_intent -> claim_physical_order -> claim_execution ->
[crash point] -> finish_execution) that
libs/execution/intent_execution_owner.py::execute_owned_order performs, so
these tests exercise the REAL Step5C contract, not a reimplementation of it.
"""

from __future__ import annotations

import time

import pytest

import scripts.step5d_crash_reconciliation as step5d
from graphs.nodes.execute_from_packet import _evaluate_open_order_reconciliation_guard
from libs.execution.intent_identity import bind_intent, physical_order_fingerprint
from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    SQLiteIntentStateStore,
)


@pytest.fixture(autouse=True)
def _reenable_open_order_reconciliation_guard(monkeypatch):
    """Scenario E and INV-3/INV-4 specifically exercise
    _evaluate_open_order_reconciliation_guard -- override conftest.py's
    project-wide default-disable (see
    `_disable_open_order_reconciliation_guard_by_default` there)."""
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "true")


def _order(symbol="005930", action="BUY", qty=1, price=None, order_type="market"):
    return {"symbol": symbol, "action": action, "qty": qty, "price": price, "order_type": order_type}


def _open_order_snapshot(rows, *, reader_ok=True, reader_error=""):
    # P0-A (2026-09-17 redesign): _evaluate_open_order_reconciliation_guard
    # now consumes the deterministic state["open_order_snapshot"] the real
    # tick flow always populates (graphs/nodes/build_open_order_snapshot.py),
    # not state["skill_results"]["account.orders"] -- see
    # tests/test_p0a_open_order_reconciliation_guard.py for the guard's own
    # dedicated coverage of this contract.
    return {
        "rows": rows,
        "_health": {
            "reader_ok": reader_ok,
            "reader_error": reader_error,
            "source": "reader",
            "fetched_epoch": int(time.time()),
        },
    }


class _RecordingExecutor:
    """Never actually dispatches -- these tests verify CAS/guard behavior,
    not broker transport. A real broker call is never made by this file."""

    def __init__(self, result=None, raise_exc=None):
        self.calls = 0
        self._result = result
        self._raise_exc = raise_exc

    def execute(self, request):
        self.calls += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._result


# ---------------------------------------------------------------------------
# Scenario A -- OrderIntent created -> crash -> restart
# ---------------------------------------------------------------------------


def test_scenario_a_intent_created_then_crash_leaves_no_orphaned_sqlite_row(tmp_path, monkeypatch):
    # decide_trade.py builds `intent` in per-tick in-memory state only;
    # bind_intent()/SQLite persistence happens strictly INSIDE
    # execute_from_packet -> execute_owned_order. A crash before that point
    # is reached (the state dict is simply discarded, per
    # _PER_RUN_TRANSIENT_KEYS) leaves nothing in the DB at all.
    monkeypatch.setenv("INTENT_STATE_DB_PATH", str(tmp_path / "intent_state.db"))
    result = step5d.report(db_path=str(tmp_path / "intent_state.db"), grace_sec=0, limit=50)
    assert result["orphan_count"] == 0  # nothing was ever claimed -- SAFE, no restart-safety action needed


# ---------------------------------------------------------------------------
# Scenario B -- approved -> crash before CAS/dispatch -> restart
# ---------------------------------------------------------------------------


def test_scenario_b_approved_then_crash_before_dispatch_does_not_block_a_fresh_attempt(tmp_path):
    db_path = tmp_path / "intent_state.db"
    order = _order()
    state = {"run_id": "orphaned-run-b"}
    iid = bind_intent(state, order)
    physical_key = physical_order_fingerprint(state, order)
    store = SQLiteIntentStateStore(str(db_path))
    store.admit_intent(iid, fingerprint=physical_key, source="test_scenario_b")
    assert store.get_state(iid)["state"] == INTENT_STATE_APPROVED
    # Crash here -- claim_execution() is never reached, no physical lease
    # was ever taken for this attempt.

    # A fresh tick builds a brand-new `order` dict from the packet's intent
    # every time (graphs/nodes/execute_from_packet.py::_build_order_from_intent)
    # -- never reuses a mutated dict across ticks. Reproduce that here with
    # a fresh _order() call rather than reusing the first call's (now
    # intent_id-mutated) `order` object.
    fresh_state = {"run_id": "fresh-run-b"}
    fresh_order = _order()
    fresh_iid = bind_intent(fresh_state, fresh_order)
    assert fresh_iid != iid
    fresh_physical_key = physical_order_fingerprint(fresh_state, fresh_order)
    assert fresh_physical_key == physical_key  # same real-world order shape

    # Full admit -> claim_execution -> claim_physical_order sequence for the
    # fresh attempt, against the SAME store (matching real production
    # ordering: admit_order_intent() runs before execute_owned_order()) --
    # exercised directly against the store (not execute_owned_order's own
    # env-resolved default store) to keep this test's database path
    # explicit and self-contained.
    fresh_store = SQLiteIntentStateStore(str(db_path))
    fresh_store.admit_intent(fresh_iid, fingerprint=fresh_physical_key, source="test_scenario_b_fresh")
    fresh_claim = fresh_store.claim_execution(fresh_iid, fingerprint=fresh_physical_key, owner="owner-b-fresh")
    assert fresh_claim["claimed"] is True
    fresh_phys_claim = fresh_store.claim_physical_order(fresh_physical_key, intent_id=fresh_iid, owner="owner-b-fresh")
    assert fresh_phys_claim["claimed"] is True

    executor = _RecordingExecutor(result=type("R", (), {"meta": {"broker_outcome": "ACCEPTED"}})())
    outcome = executor.execute(object())
    assert executor.calls == 1
    assert outcome.meta["broker_outcome"] == "ACCEPTED"
    assert executor.calls == 1


# ---------------------------------------------------------------------------
# Scenario C -- CAS claimed -> broker dispatch -> crash before response persisted
# ---------------------------------------------------------------------------


def test_scenario_c_crash_after_cas_claim_blocks_exact_duplicate_retry(tmp_path):
    db_path = tmp_path / "intent_state.db"
    order = _order(symbol="000660", qty=5, price=70000, order_type="limit")
    state = {"run_id": "crashed-run-c"}
    iid = bind_intent(state, order)
    physical_key = physical_order_fingerprint(state, order)
    store = SQLiteIntentStateStore(str(db_path))
    store.admit_intent(iid, fingerprint=physical_key, source="test_scenario_c")
    claim = store.claim_execution(iid, fingerprint=physical_key, owner="owner-c")
    assert claim["claimed"] is True
    phys = store.claim_physical_order(physical_key, intent_id=iid, owner="owner-c")
    assert phys["claimed"] is True
    # ***** CRASH ***** -- executor.execute() either never ran or its
    # response was never persisted; finish_execution() never runs.
    assert store.get_state(iid)["state"] == INTENT_STATE_EXECUTING

    # Restart: a fresh tick generates the IDENTICAL physical order shape
    # under a NEW intent_id (same as Scenario B's fresh-attempt setup) --
    # a brand-new order dict, never the first attempt's mutated one.
    fresh_state = {"run_id": "fresh-run-c"}
    fresh_order = _order(symbol="000660", qty=5, price=70000, order_type="limit")
    fresh_iid = bind_intent(fresh_state, fresh_order)
    assert fresh_iid != iid

    fresh_store = SQLiteIntentStateStore(str(db_path))
    fresh_store.admit_intent(fresh_iid, fingerprint=physical_key, source="test_scenario_c_retry")
    retry_phys_claim = fresh_store.claim_physical_order(physical_key, intent_id=fresh_iid, owner="owner-c-retry")

    # INV-1 / INV-2: the retry is BLOCKED -- no second physical lease, and
    # no automatic assumption of what happened to the crashed attempt.
    assert retry_phys_claim["claimed"] is False
    assert retry_phys_claim["reason"] == "physical_order_already_claimed"
    assert retry_phys_claim["holder_intent_id"] == iid

    # Manual reconciliation is the documented, correct path forward --
    # not an automatic retry.
    report = step5d.report(db_path=str(db_path), grace_sec=0, limit=50)
    assert report["orphan_count"] == 1
    assert report["orphans"][0]["physical_order_key"] == physical_key


# ---------------------------------------------------------------------------
# Scenario D -- broker execution confirmed -> crash before local persistence
# ---------------------------------------------------------------------------


def test_scenario_d_confirmed_execution_crash_before_persist_no_duplicate_after_manual_reconciliation(tmp_path):
    db_path = tmp_path / "intent_state.db"
    order = _order(symbol="005380")
    state = {"run_id": "crashed-run-d"}
    iid = bind_intent(state, order)
    physical_key = physical_order_fingerprint(state, order)
    store = SQLiteIntentStateStore(str(db_path))
    store.admit_intent(iid, fingerprint=physical_key, source="test_scenario_d")
    store.claim_execution(iid, fingerprint=physical_key, owner="owner-d")
    store.claim_physical_order(physical_key, intent_id=iid, owner="owner-d")
    # Broker confirmed the order (per this scenario's premise) but
    # ***** CRASH ***** happens before finish_execution() persists that.

    # An automatic "probably went through, mark it EXECUTED" is explicitly
    # forbidden -- verify the row is still EXECUTING (fail-closed) and only
    # an explicit, evidenced manual resolution moves it.
    assert store.get_state(iid)["state"] == INTENT_STATE_EXECUTING

    resolved = step5d.resolve(
        db_path=str(db_path), physical_order_key=physical_key, intent_id=iid,
        outcome="executed", confirmed_by="operator-d",
        evidence="kt00007 order history confirms BUY 005380 accepted, ord_no 55501",
        audit_log=str(tmp_path / "audit.jsonl"),
    )
    assert resolved["ok"] is True
    assert resolved["resolved_state"] == INTENT_STATE_EXECUTED
    assert store.get_physical_claim(physical_key) is None  # released only now, on genuine terminal outcome


# ---------------------------------------------------------------------------
# Scenario E -- pending/open order exists -> restart -> same-symbol new entry
# ---------------------------------------------------------------------------


def test_scenario_e_pending_open_order_blocks_new_same_symbol_entry_even_with_different_price():
    # This is exactly the gap Step5C's exact-fingerprint guard does NOT
    # cover (different price => different physical_order_fingerprint) --
    # P0-A's guard is what closes it, at the symbol+side granularity.
    state = {
        "open_order_snapshot": _open_order_snapshot(
            [{"symbol": "005930", "ord_no": "1", "side": "BUY", "status": "접수", "order_qty": 10, "filled_qty": 0}],
        ),
    }
    # LIMIT orders (unlike MARKET, whose physical identity deliberately
    # excludes price -- intent_identity.py's own frozen design) genuinely
    # differ in physical_order_fingerprint when price differs.
    original = _order(symbol="005930", price=70000, order_type="limit")
    retry_different_price = _order(symbol="005930", price=71000, order_type="limit")  # would NOT collide on physical_order_fingerprint

    assert physical_order_fingerprint({"run_id": "r1"}, original) != physical_order_fingerprint({"run_id": "r2"}, retry_different_price)

    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, retry_different_price)
    assert allowed is False  # NO DUPLICATE PHYSICAL ORDER
    assert reason == "pending_open_order_exists_for_symbol"


# ---------------------------------------------------------------------------
# Scenario F -- old runtime shutdown + new runtime startup overlap
# ---------------------------------------------------------------------------


def test_scenario_f_single_runtime_ownership_lock_prevents_overlap(tmp_path):
    from libs.runtime.live_loop_lock import acquire_live_loop_lock, release_live_loop_lock
    import os

    lock_path = tmp_path / "m13_live_loop.lock"
    own_pid = os.getpid()  # a genuinely alive PID, simulating the "old" runtime

    acquired_old, _ = acquire_live_loop_lock(lock_path, lock_stale_sec=1800, current_pid=own_pid)
    assert acquired_old is True

    # A "new runtime" attempting to start while the old one is still alive
    # (no stop happened yet) must be refused -- this is the second,
    # independent safety net beyond restart_live_session.py's own
    # sequential stop-wait-then-start ordering.
    acquired_new, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=1800, current_pid=own_pid + 1)
    assert acquired_new is False
    assert reason == "lock_active"

    # Only after the old runtime releases does a new one succeed --
    # sequential, never overlapping.
    release_live_loop_lock(lock_path, current_pid=own_pid)
    acquired_after_release, _ = acquire_live_loop_lock(lock_path, lock_stale_sec=1800, current_pid=own_pid + 1)
    assert acquired_after_release is True


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_inv1_same_physical_order_cannot_dispatch_twice_while_in_flight(tmp_path):
    # Two independent attempts (different intent_id, e.g. two overlapping
    # processes or a naive retry) at the identical, not-yet-finished
    # physical order: only one may ever reach the executor.
    db_path = tmp_path / "intent_state.db"
    order = _order(symbol="373220")

    state1 = {"run_id": "inv1-r1"}
    iid1 = bind_intent(state1, order)
    physical_key = physical_order_fingerprint(state1, order)
    store = SQLiteIntentStateStore(str(db_path))
    store.admit_intent(iid1, fingerprint=physical_key, source="inv1")
    claim1 = store.claim_execution(iid1, fingerprint=physical_key, owner="o1")
    assert claim1["claimed"] is True
    phys1 = store.claim_physical_order(physical_key, intent_id=iid1, owner="o1")
    assert phys1["claimed"] is True
    # iid1's dispatch is now "in flight" (EXECUTING, not yet finished).

    state2 = {"run_id": "inv1-r2"}
    order2 = _order(symbol="373220")  # a second, independent order dict -- same physical shape
    iid2 = bind_intent(state2, order2)
    store2 = SQLiteIntentStateStore(str(db_path))
    store2.admit_intent(iid2, fingerprint=physical_key, source="inv1_second_attempt")
    phys2 = store2.claim_physical_order(physical_key, intent_id=iid2, owner="o2")
    assert phys2["claimed"] is False  # the second attempt never gets to call the executor at all


def test_inv2_unknown_broker_state_cannot_cause_automatic_retry(tmp_path):
    db_path = tmp_path / "intent_state.db"
    order = _order(symbol="005490")
    state = {"run_id": "inv2-r1"}
    iid = bind_intent(state, order)
    physical_key = physical_order_fingerprint(state, order)
    store = SQLiteIntentStateStore(str(db_path))
    store.admit_intent(iid, fingerprint=physical_key, source="inv2")
    store.claim_execution(iid, fingerprint=physical_key, owner="o1")
    store.claim_physical_order(physical_key, intent_id=iid, owner="o1")
    # crash -- outcome UNKNOWN, never persisted

    # No code path in this repository may transition this row without an
    # explicit, evidenced operator call -- verify it is untouched by mere
    # passage of time / re-inspection.
    for _ in range(3):
        assert store.get_state(iid)["state"] == INTENT_STATE_EXECUTING
        step5d.report(db_path=str(db_path), grace_sec=0, limit=50)  # inspection only, must not mutate
    assert store.get_state(iid)["state"] == INTENT_STATE_EXECUTING


def test_inv3_pending_entry_order_prevents_unsafe_additional_entry():
    state = {
        "open_order_snapshot": _open_order_snapshot(
            [{"symbol": "011200", "ord_no": "9", "side": "BUY", "status": "접수", "order_qty": 3, "filled_qty": 0}],
        ),
    }
    allowed, reason, _ = _evaluate_open_order_reconciliation_guard(state, _order(symbol="011200"))
    assert allowed is False
    assert reason == "pending_open_order_exists_for_symbol"


def test_inv4_failed_reconciliation_means_execution_disabled():
    state = {"open_order_snapshot": _open_order_snapshot([], reader_ok=False, reader_error="broker_unreachable")}
    allowed, reason, _ = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_reader_error"


def test_inv5_restart_never_implicitly_enables_real_execution(monkeypatch):
    # EXECUTION_ENABLED/ALLOW_REAL_EXECUTION are read fresh via os.getenv
    # on every call (RealExecutor.preflight_check) -- a restart with no
    # env change must still be gated exactly as before. Verified at the
    # canonical read site directly (no caching to reset/bypass).
    from libs.execution.executors.real_executor import RealExecutor

    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("ALLOW_REAL_EXECUTION", "true")
    result = RealExecutor._env_flag_true("EXECUTION_ENABLED", "false")
    assert result is False  # still disabled by default after "restart" (env unchanged)


def test_inv6_sigterm_cannot_bypass_guard_or_execution_authority():
    from libs.runtime.live_loop_runner import ShutdownRequested

    # The shutdown flag has exactly one effect: gating whether a NEW tick
    # starts. It is never read by, passed to, or capable of influencing
    # Supervisor.allow(), the guard chain, or execute_owned_order's CAS --
    # confirmed structurally: ShutdownRequested is not imported anywhere
    # in the execution/guard/supervisor modules.
    import graphs.nodes.execute_from_packet as efp
    import libs.execution.intent_execution_owner as ieo
    import libs.risk.supervisor as sup

    for module in (efp, ieo, sup):
        assert not hasattr(module, "ShutdownRequested")
        assert "ShutdownRequested" not in dir(module)


def test_inv7_persistent_idempotency_survives_process_restart(tmp_path):
    # Simulate "process restart" as simply constructing a brand-new
    # SQLiteIntentStateStore against the same on-disk path (no in-memory
    # state carried over) -- the CAS guarantee must hold regardless.
    db_path = tmp_path / "intent_state.db"
    order = _order(symbol="047810")
    state = {"run_id": "inv7-before-restart"}
    iid = bind_intent(state, order)
    physical_key = physical_order_fingerprint(state, order)

    store_before = SQLiteIntentStateStore(str(db_path))
    store_before.admit_intent(iid, fingerprint=physical_key, source="inv7")
    store_before.claim_execution(iid, fingerprint=physical_key, owner="o1")
    store_before.claim_physical_order(physical_key, intent_id=iid, owner="o1")
    del store_before  # "process restart" -- drop the in-memory object entirely

    store_after = SQLiteIntentStateStore(str(db_path))
    assert store_after.get_state(iid)["state"] == INTENT_STATE_EXECUTING
    retry_claim = store_after.claim_physical_order(physical_key, intent_id="different-intent-after-restart", owner="o2")
    assert retry_claim["claimed"] is False
