"""2026-09-03 daily audit (P1-A) -- executable quote acquisition fix.

Root cause: graphs/nodes/scanner_node.py's one-time market.quote hydration
fan-out is capped at candidate_k (default 5) symbols from Scanner's own
composite ranking. A symbol later chosen via a different selection
mechanism (e.g. opening_rank1_controlled_probe's intrinsic-rank1
authority, or any controlled-lane symbol outside that top-K set) never
gets its quote fetched during that one pass, so every later
`_extract_upper_limit_quote_snapshot` lookup for it comes back empty --
this is exactly what happened to 004310 (Hyundai Pharm) at today's
09:00:07 KST opening tick: `quote_snapshot: {}`, `broker_outcome:
NOT_SENT`, `reason: opening_alpha_executable_price_unavailable`.

Fix: `graphs/nodes/execute_from_packet.py::_refresh_executable_quote_if_missing`
attempts ONE live, synchronous market.quote re-fetch for the order's own
symbol -- a pure market-data READ, never a broker mutation -- only when
the pre-hydrated snapshot has nothing usable. It never falls back to a
stale/Scanner-cached price, and never widens any guard threshold; it only
gives the EXISTING guards (controlled-lane / opening-alpha price
integrity) a chance to see a real quote before concluding one is
unavailable.

These tests exercise the guard via the `controlled_mock_lane` path (the
existing, simplest executable-price gate in execute_from_packet.py,
proven by the pre-existing
tests/test_execute_from_packet.py::test_q10_controlled_lane_missing_target_quote_is_not_sent)
plus one direct unit test of the refresh helper itself for T7's Step5B
mutation-boundary invariant.
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
    """Test double for CompositeSkillRunner -- never touches a real broker
    or network. Records every call for T7's physical-call-count assertions."""

    def __init__(
        self,
        *,
        quote_by_symbol: Optional[Dict[str, Dict[str, Any]]] = None,
        raise_exc: Optional[Exception] = None,
        wrong_symbol_row: Optional[Dict[str, Any]] = None,
    ):
        self.quote_by_symbol = dict(quote_by_symbol or {})
        self.raise_exc = raise_exc
        self.wrong_symbol_row = wrong_symbol_row
        self.calls: List[Dict[str, Any]] = []

    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> _FakeSkillRunResult:
        self.calls.append({"run_id": run_id, "skill": skill, "args": dict(args)})
        if self.raise_exc is not None:
            raise self.raise_exc
        if skill != "market.quote":
            return _FakeSkillRunResult(action="error", skill=skill, meta={"error_type": "unsupported_skill"})
        if self.wrong_symbol_row is not None:
            return _FakeSkillRunResult(action="ready", skill=skill, data=dict(self.wrong_symbol_row))
        symbol = str(args.get("symbol") or "")
        row = self.quote_by_symbol.get(symbol)
        if row is None:
            return _FakeSkillRunResult(action="error", skill=skill, meta={"error_type": "quote_not_available"})
        return _FakeSkillRunResult(action="ready", skill=skill, data=dict(row))


class _NeverCalledExecutor:
    """Broker mutation double -- raises if ever invoked. Used to prove
    T2/T3/T6/T7's "broker calls = 0" invariant (the guard is expected to
    block BEFORE dispatch in those scenarios)."""

    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        raise AssertionError("broker API must not be called")


class _AcceptingExecutor:
    """Broker mutation double for the "guard passes, execution proceeds
    normally" scenarios (T1/T4/T5) -- records call count and always
    returns a normal ExecutionResult, matching how mock-mode execution
    behaves once the price-integrity guard is satisfied."""

    def __init__(self):
        self.calls = 0

    def execute(self, request):
        from libs.core.api_response import ApiResponse
        from libs.execution.executors.base import ExecutionResult

        self.calls += 1
        return ExecutionResult(
            response=ApiResponse(status_code=200, ok=True, payload={"mode": "mock"}, error_code=None, error_message=None, raw_text=""),
            meta={"executor": "mock"},
        )


def _catalog_path(tmp_path) -> str:
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    return str(cat)


def _controlled_lane_state(tmp_path, *, symbol: str, executor, skill_runner=None) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": "p1a-quote-refresh-test",
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


# --- T1: valid fresh ask already present -- normal pipeline proceeds, no refresh --


def test_t1_valid_fresh_quote_already_present_skips_refresh(tmp_path, monkeypatch):
    symbol = "004310"
    executor = _AcceptingExecutor()
    runner = _FakeSkillRunner()  # would return an error if ever called -- proves refresh is skipped
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=runner)

    def _fake_extract(_state, _symbol):
        return {
            "symbol": symbol, "quote_present": True, "source": "skill.market.quote",
            "current_price": 8140.0, "best_ask": 8150.0, "best_bid": 8130.0,
            "change_pct": 0.0, "raw_row_present": True, "observed_at": "2026-09-03T00:00:07+00:00",
            "observed_epoch": 1788393607,
        }

    monkeypatch.setattr(efp, "_extract_upper_limit_quote_snapshot", _fake_extract)
    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is True
    assert runner.calls == []  # no refresh attempted -- already valid
    assert executor.calls == 1  # normal pipeline proceeded to dispatch, unaffected by the new refresh path


# --- T2: missing quote, no runner available -- NOT_SENT, broker calls = 0 --
# (matches the pre-existing, still-green
#  tests/test_execute_from_packet.py::test_q10_controlled_lane_missing_target_quote_is_not_sent
#  -- this variant re-confirms the SAME invariant survives the new refresh
#  code path when no skill_runner is even present in state, i.e. refresh
#  cannot be attempted at all.)


def test_t2_missing_quote_no_runner_available_is_not_sent(tmp_path):
    symbol = "004310"
    executor = _NeverCalledExecutor()
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=None)

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "controlled_lane_executable_quote_missing"
    assert out["execution"]["controlled_lane_execution_price_guard"]["broker_api_called"] is False
    assert executor.calls == 0


# --- T3: wrong-symbol quote -- NOT_SENT, broker calls = 0 --


def test_t3_refresh_returns_wrong_symbol_quote_is_not_sent(tmp_path):
    symbol = "004310"
    executor = _NeverCalledExecutor()
    runner = _FakeSkillRunner(wrong_symbol_row={"symbol": "000660", "price": 250000.0, "best_ask": 250100.0})
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=runner)

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "controlled_lane_executable_quote_missing"
    assert out["execution"]["controlled_lane_execution_price_guard"]["broker_api_called"] is False
    assert executor.calls == 0
    assert len(runner.calls) == 1  # refresh was attempted exactly once
    assert runner.calls[0]["args"]["symbol"] == symbol  # requested the RIGHT symbol
    assert out["execution"]["controlled_lane_execution_price_guard"]["executable_price"] is None  # wrong-symbol row never used


# --- T4: an already-valid (if stale) quote is never overwritten by the refresh path --


def test_t4_existing_quote_not_replaced_regardless_of_age(tmp_path, monkeypatch):
    symbol = "004310"
    executor = _AcceptingExecutor()
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 9999.0, "best_ask": 9999.0}})
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=runner)

    stale_epoch = 1  # deliberately ancient -- the guard as it exists today has no TTL check;
    # this test proves the NEW refresh logic does not change that: it must
    # never fire (and never substitute a different price) when the
    # pre-hydrated snapshot already reports a usable price, however old.
    def _fake_extract(_state, _symbol):
        return {
            "symbol": symbol, "quote_present": True, "source": "skill.market.quote",
            "current_price": 8000.0, "best_ask": 8010.0, "best_bid": 7990.0,
            "change_pct": 0.0, "raw_row_present": True, "observed_at": None,
            "observed_epoch": stale_epoch,
        }

    monkeypatch.setattr(efp, "_extract_upper_limit_quote_snapshot", _fake_extract)
    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is True
    assert runner.calls == []  # refresh never triggered -- pre-existing (stale-or-not) value wins unchanged
    assert executor.calls == 1  # normal pipeline proceeded to dispatch, unaffected by the new refresh path


# --- T5: initial quote missing, refresh succeeds -- fresh price used, provenance recorded --


def test_t5_refresh_success_uses_fresh_price_with_provenance(tmp_path):
    symbol = "004310"
    executor = _AcceptingExecutor()  # the guard now passes, so normal dispatch proceeds
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 8140.0, "best_ask": 8150.0, "best_bid": 8130.0}})
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=runner)

    out = execute_from_packet(state)

    assert len(runner.calls) == 1
    assert runner.calls[0]["args"]["symbol"] == symbol
    # The controlled-lane guard now sees a valid quote and lets the order through the
    # price-integrity check (it may still be blocked/allowed further downstream by
    # unrelated mock-broker guards -- what matters here is it is NOT blocked by
    # controlled_lane_executable_quote_missing/symbol_mismatch).
    reason = str(out["execution"].get("reason") or "")
    assert reason not in ("controlled_lane_executable_quote_missing", "controlled_lane_executable_quote_symbol_mismatch")
    price_guard = out["execution"].get("controlled_lane_execution_price_guard")
    if price_guard is not None:
        assert price_guard["executable_price"] == pytest.approx(8150.0)


# --- T6: initial quote missing, refresh itself fails -- NOT_SENT, no Scanner-cached fallback, broker calls = 0 --


def test_t6_refresh_failure_is_not_sent_no_fallback_to_cached_price(tmp_path):
    symbol = "004310"
    executor = _NeverCalledExecutor()
    runner = _FakeSkillRunner(raise_exc=RuntimeError("kiwoom quote endpoint timeout"))
    state = _controlled_lane_state(tmp_path, symbol=symbol, executor=executor, skill_runner=runner)
    # Simulate a Scanner-cached price sitting elsewhere in state/order -- it must
    # never be used as a substitute executable price.
    state["decision_packet"]["intent"]["meta"]["scanner_cached_price"] = 8140.0

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "controlled_lane_executable_quote_missing"
    assert out["execution"]["controlled_lane_execution_price_guard"]["executable_price"] is None
    assert out["execution"]["controlled_lane_execution_price_guard"]["broker_api_called"] is False
    assert executor.calls == 0
    assert len(runner.calls) == 1  # refresh was attempted, and its failure was not masked


# --- T7: Step5B invariant -- the refresh is a market-data read, never a broker mutation ---


def test_t7_refresh_helper_never_calls_a_mutation_api_and_broker_calls_stay_zero(tmp_path):
    """Direct unit test of the helper: confirms it only ever calls the
    'market.quote' skill (never kt10000/kt10001/kt10002/kt10003 or any
    other mutation-classified api_id), matching Step5B's untouched
    at-most-one-physical-broker-submission contract."""
    symbol = "004310"
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 8140.0, "best_ask": 8150.0}})
    state: Dict[str, Any] = {"run_id": "t7-direct", "skill_runner": runner}
    empty_snapshot = {"symbol": symbol, "quote_present": False, "best_ask": 0.0, "current_price": 0.0}

    refreshed, meta = efp._refresh_executable_quote_if_missing(state, symbol, empty_snapshot)

    assert meta["used"] is True
    assert refreshed["best_ask"] == pytest.approx(8150.0)
    assert len(runner.calls) == 1
    assert runner.calls[0]["skill"] == "market.quote"  # never a mutation skill (order.place / order.cancel)


# --- 2026-09-04: same upstream gap, second call site (order_limit_guard's --
# own price resolution). Reproduces today's real incident: Q10_INDEX's
# KODEX 200 (069500) signal was correctly identified and attempted twice
# (09:05, 09:10), but both were BROKER_REJECTED with reason
# order_notional_price_missing -- _resolve_order_price_for_notional_with_source
# found no price anywhere (order/meta/state rows/market.quote cache) because
# 069500, like 004310 the day before, was never in scanner_node.py's
# hydration fan-out. Fixed by extracting the P1-A refresh core into
# `_ensure_live_market_quote` and calling it from this second site too. ---


def test_order_limit_guard_blocks_on_missing_price_when_no_runner_available(tmp_path, monkeypatch):
    """Matches the pre-existing, still-green
    tests/test_execute_from_packet.py::test_execute_from_packet_blocks_buy_when_notional_guard_price_missing
    -- confirms this exact scenario (no skill_runner in state at all) is
    completely unaffected by the fix: still fails closed exactly as before."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    state = {
        "catalog_path": _catalog_path(tmp_path),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "069500", "qty": 1, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_price_missing"


def test_order_limit_guard_reproduces_and_closes_todays_kodex200_incident(tmp_path, monkeypatch):
    """Reproduces 2026-09-04's actual Q10_INDEX/KODEX 200 (069500)
    BROKER_REJECTED incident exactly (qty/order shape matches the real
    controlled-lane submission), then confirms the fix: with a live
    skill_runner available, the guard now finds a real quote via one
    market.quote re-fetch instead of blocking."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "50000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    symbol = "069500"
    runner = _FakeSkillRunner(quote_by_symbol={symbol: {"symbol": symbol, "price": 35870.0, "best_ask": 35880.0, "best_bid": 35860.0}})
    state = {
        "run_id": "kodex200-2026-09-04",
        "catalog_path": _catalog_path(tmp_path),
        "skill_runner": runner,
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": symbol, "qty": 10, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)

    assert len(runner.calls) == 1
    assert runner.calls[0]["skill"] == "market.quote"
    assert runner.calls[0]["args"]["symbol"] == symbol
    assert out["execution"]["reason"] != "order_notional_price_missing"
    guard = out["execution"].get("order_limit_guard") or {}
    if guard:
        assert guard.get("price_evaluable", True) is not False
        if guard.get("price") is not None:
            assert "live_refresh" in str(guard.get("price_source") or "")


def test_order_limit_guard_refresh_failure_still_blocks_no_fallback(tmp_path, monkeypatch):
    """If the live refresh itself fails (e.g. transient error), the guard
    must still fail closed -- never fall back to a stale/cached price."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    symbol = "069500"
    runner = _FakeSkillRunner(raise_exc=RuntimeError("kiwoom quote endpoint timeout"))
    state = {
        "run_id": "kodex200-refresh-fail",
        "catalog_path": _catalog_path(tmp_path),
        "skill_runner": runner,
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": symbol, "qty": 1, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_price_missing"
    assert len(runner.calls) == 1  # refresh was attempted, and its failure was not masked


def test_ensure_live_market_quote_wrong_symbol_never_used():
    """Direct unit test: the shared helper rejects a wrong-symbol response
    defensively, same invariant as the original T3."""
    symbol = "069500"
    runner = _FakeSkillRunner(wrong_symbol_row={"symbol": "005930", "price": 70000.0})
    state: Dict[str, Any] = {"run_id": "wrong-symbol-direct", "skill_runner": runner}

    meta = efp._ensure_live_market_quote(state, symbol)

    assert meta["used"] is False
    assert meta["reason"] == "quote_symbol_mismatch"
    assert "market.quote" not in (state.get("skill_results") or {})
