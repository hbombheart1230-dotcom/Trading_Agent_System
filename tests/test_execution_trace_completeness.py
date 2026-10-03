"""Execution Trace Completeness -- minimal observability patch tests.

2026-09-14 Opening Alpha incident: Scanner Rank-1 -> Strategist -> Commander
-> Opening Alpha reservation -> NOT_SENT -> broker submission=0 was
observable, but the SAME intent's terminal block reason, executable price,
notional, and broker-attempt status did not all survive into one
reconstructable record. This file proves the fix is observability-only:
every one of these fields is now present (or explicitly null with an
existing-authority reason) on `state["execution"]`, for every one of the
outcome classes below, with ZERO change to any guard/order/broker decision
(re-confirmed by `tests/test_opening_alpha_executable_quote_refresh.py`
and `tests/test_execute_from_packet.py` staying green, unmodified).

Additive-only: no guard threshold, order semantics, or broker behavior is
exercised differently than before this patch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from graphs.nodes.execute_from_packet import execute_from_packet
import graphs.nodes.execute_from_packet as efp


@dataclass
class _FakeSkillRunResult:
    action: str
    skill: str = "market.quote"
    outputs: str = "QuoteDTO"
    data: Any = None
    missing: List[str] = field(default_factory=list)
    question: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


class _FakeSkillRunner:
    def __init__(self, *, quote_by_symbol: Optional[Dict[str, Dict[str, Any]]] = None):
        self.quote_by_symbol = dict(quote_by_symbol or {})
        self.calls: List[Dict[str, Any]] = []

    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> _FakeSkillRunResult:
        self.calls.append({"run_id": run_id, "skill": skill, "args": dict(args)})
        if skill != "market.quote":
            return _FakeSkillRunResult(action="error", skill=skill, meta={"error_type": "unsupported_skill"})
        symbol = str(args.get("symbol") or "")
        row = self.quote_by_symbol.get(symbol)
        if row is None:
            return _FakeSkillRunResult(action="error", skill=skill, meta={"error_type": "quote_not_available"})
        return _FakeSkillRunResult(action="ready", skill=skill, data=dict(row))


class _NeverCalledExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        raise AssertionError("broker API must not be called")


class _AcceptingExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        self.calls += 1
        return ExecutionResult(
            response=ApiResponse(status_code=200, ok=True, payload={"mode": "mock", "ord_no": "TEST-ORD-1", "rt_cd": "0"}, error_code=None, error_message=None, raw_text=""),
            meta={"executor": "mock"},
        )


def _catalog_path(tmp_path) -> str:
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    return str(cat)


def _controlled_lane_state(tmp_path, *, symbol: str, executor, run_id: str, skill_runner=None) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": run_id,
        "catalog_path": _catalog_path(tmp_path),
        "executor": executor,
        "portfolio_snapshot": {"positions": [], "open_positions": 0},
        "persisted_state": {"mock_cash": 1_000_000.0},
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": symbol,
                "qty": 1,
                "price": None,
                "order_api_id": "ORDER_SUBMIT",
                "order_type": "market",
                "meta": {
                    "controlled_mock_lane": {
                        "lane_id": "TEST_LANE",
                        "signal_id": f"TEST_LANE_{symbol}",
                    }
                },
            },
            "risk": {"open_positions": 0, "max_positions": 3},
            "exec_context": {},
        },
    }
    if skill_runner is not None:
        state["skill_runner"] = skill_runner
    return state


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED", "false")
    # MAX_ORDER_NOTIONAL is deliberately NOT set here (matches the
    # pre-existing test_opening_alpha_executable_quote_refresh.py fixture) --
    # the order_limit_guard (an EARLIER guard than the controlled-lane
    # executable-quote check) must stay a no-op for tests C/D, which are
    # specifically about the LATER controlled-lane guard. Test A opts in to
    # MAX_ORDER_NOTIONAL itself, to exercise the notional trace's non-null path.


# =========================================================================
# Test A -- successful broker submission: complete trace
# =========================================================================


def test_a_successful_broker_submission_has_complete_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "50000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")
    symbol = "004310"
    executor = _AcceptingExecutor()
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 8140.0, "best_ask": 8150.0, "best_bid": 8130.0}})
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, run_id="trace-test-a", skill_runner=runner)

    out = execute_from_packet(state)
    execution = out["execution"]

    assert execution["allowed"] is True
    assert executor.calls == 1

    # Broker Attempt Invariant: attempted AND (here) accepted -- both true.
    assert execution["broker_attempted"] is True
    assert execution["broker_attempt_count"] >= 1
    assert execution["order_sent"] is True

    # Executable Price Trace: value + provenance both present.
    assert execution["executable_price"] == pytest.approx(8150.0)
    assert execution["executable_price_source"]
    assert "market.quote" in execution["executable_price_source"]

    # Notional Trace: both present (MAX_ORDER_NOTIONAL is configured and
    # price/qty both resolved, so the guard actually computed a notional).
    assert execution["order_notional"] is not None
    assert execution["order_notional_price"] is not None
    assert execution["order_notional"] == pytest.approx(execution["order_notional_price"] * 1)  # qty=1

    # Terminal reason/state coherent for a successful outcome.
    assert execution["broker_outcome"] == "ACCEPTED"
    assert execution["intent_id"]


# =========================================================================
# Test B -- guard blocked before broker (order_notional_price_missing)
# =========================================================================


def test_b_guard_blocked_before_broker_has_complete_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")
    state = {
        "run_id": "trace-test-b",
        "catalog_path": _catalog_path(tmp_path),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "069500", "qty": 1, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    execution = out["execution"]

    assert execution["allowed"] is False
    assert execution["reason"] == "order_notional_price_missing"  # pre-existing canonical reason, unchanged

    # Broker Attempt Invariant: never attempted -- must never be confused
    # with "attempted but rejected".
    assert execution["broker_attempted"] is False
    assert execution["broker_attempt_count"] == 0
    assert execution["order_sent"] is False

    # Executable price was never reached (guard blocked earlier in the
    # pipeline) -- null, and the SAME terminal reason already explains why;
    # no separate reason taxonomy invented.
    assert execution["executable_price"] is None
    assert execution["order_notional"] is None
    assert execution["order_notional_price"] is None

    # Terminal Reason Invariant.
    assert execution["reason"] not in (None, "")
    assert execution["intent_id"]

    # Same-intent lineage: the guard's own detail dict (order_notional_price_missing
    # evidence) is still nested in the SAME record under the SAME intent_id.
    guard = execution.get("order_limit_guard") or {}
    assert guard.get("limit_exceeded") == "notional_price_missing"


# =========================================================================
# Test C -- quote unavailable (controlled-lane executable quote missing)
# =========================================================================


def test_c_quote_unavailable_has_complete_trace(tmp_path):
    symbol = "004310"
    executor = _NeverCalledExecutor()
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, run_id="trace-test-c", skill_runner=None)

    out = execute_from_packet(state)
    execution = out["execution"]

    assert execution["allowed"] is False
    assert execution["reason"] == "controlled_lane_executable_quote_missing"  # pre-existing canonical reason
    assert execution["executable_price"] is None
    assert execution["broker_attempted"] is False
    assert execution["broker_attempt_count"] == 0
    assert execution["order_sent"] is False
    assert execution["reason"] not in (None, "")  # missing-price reason present, not a bare null
    assert execution["intent_id"]
    assert executor.calls == 0


# =========================================================================
# Test D -- existing successful semantics unchanged (order behavior BEFORE == AFTER)
# =========================================================================


def test_d_existing_successful_order_behavior_is_unchanged(tmp_path, monkeypatch):
    # Exact shape of the pre-existing
    # test_opening_alpha_executable_quote_refresh.py::test_t1_valid_fresh_quote_already_present_skips_refresh
    symbol = "004310"
    executor = _AcceptingExecutor()
    runner = _FakeSkillRunner()  # would error if ever called -- proves refresh is still skipped
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, run_id="trace-test-d", skill_runner=runner)

    def _fake_extract(_state, _symbol):
        return {
            "symbol": symbol, "quote_present": True, "source": "skill.market.quote",
            "current_price": 8140.0, "best_ask": 8150.0, "best_bid": 8130.0,
            "change_pct": 0.0, "raw_row_present": True, "observed_at": "2026-09-03T00:00:07+00:00",
            "observed_epoch": 1788393607,
        }

    monkeypatch.setattr(efp, "_extract_upper_limit_quote_snapshot", _fake_extract)
    out = execute_from_packet(state)
    execution = out["execution"]

    # Every pre-existing assertion this scenario already had to satisfy:
    assert execution["allowed"] is True
    assert runner.calls == []
    assert executor.calls == 1
    # The new trace fields are ADDITIVE -- present alongside, not instead of,
    # the pre-existing fields:
    assert execution["ok"] is True
    assert execution["broker_outcome"] == "ACCEPTED"
    assert "broker_attempted" in execution and "executable_price" in execution


# =========================================================================
# Test E -- same-intent lineage: intent_id reconstructs the full story,
# including in the SQLite intent-state journal (not just the in-memory dict)
# =========================================================================


def test_e_same_intent_lineage_reconstructable_from_intent_id_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "50000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")
    symbol = "004310"
    executor = _AcceptingExecutor()
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 8140.0, "best_ask": 8150.0, "best_bid": 8130.0}})
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, run_id="trace-test-e", skill_runner=runner)

    out = execute_from_packet(state)
    execution = out["execution"]
    intent_id = execution["intent_id"]
    assert intent_id

    # Reconstruct purely from intent_id via the canonical, already-existing
    # intent-ownership store -- no separate log correlated by timestamp.
    from libs.supervisor.intent_state_store import SQLiteIntentStateStore

    store = SQLiteIntentStateStore()
    journal = store.list_journal(intent_id)
    assert journal, "no journal entries found for this intent_id -- lineage is broken"

    persisted_execution = None
    for entry in journal:
        if isinstance(entry.get("execution"), dict):
            persisted_execution = entry["execution"]
    assert persisted_execution is not None, "finish_execution never persisted an execution payload for this intent_id"

    # The SAME enrichment fields must be present in the PERSISTED (SQLite)
    # record, not only the in-memory returned dict -- proving the fix closes
    # the timing gap where enrichment happened after finish_execution ran.
    assert persisted_execution.get("intent_id") == intent_id
    assert persisted_execution.get("broker_attempted") is True
    assert persisted_execution.get("executable_price") == pytest.approx(8150.0)
    assert persisted_execution.get("order_notional") is not None
    assert persisted_execution.get("broker_outcome") == "ACCEPTED"
