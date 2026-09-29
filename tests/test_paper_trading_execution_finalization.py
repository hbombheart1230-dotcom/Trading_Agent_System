"""Paper Trading Execution Finalization (2026-09-17).

Canonical terminology fixed by this phase:
  Mock Execution -- EXECUTION_MODE=mock -> MockExecutor, no broker network.
  Paper Trading  -- EXECUTION_MODE=real, KIWOOM_MODE=mock -> RealExecutor,
                    Kiwoom's own sandbox server.
  Live Trading   -- EXECUTION_MODE=real, KIWOOM_MODE=real -> RealExecutor,
                    a real Kiwoom account.

Covers the exact matrix (PAPER-1..4) plus runtime-survival proof: an
EXECUTION_ENABLED=false denial is a deterministic, expected policy
rejection (Step5B's own NOT_SENT classification) -- it must never crash
the live loop, and must never be weakened into a broad
`except Exception: continue` either (genuinely unexpected exceptions must
keep propagating, unchanged).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

import graphs.nodes.build_portfolio_snapshot as build_portfolio_snapshot_mod
import graphs.nodes.decision_node as decision_node_mod
import graphs.nodes.monitor_node as monitor_node_mod
import graphs.nodes.scanner_node as scanner_node_mod
import graphs.nodes.strategist_node as strategist_node_mod
from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings
from libs.execution.executors.base import ExecutionDisabledError
from libs.execution.executors.real_executor import RealExecutor
from libs.runtime.live_loop_runner import run_live_loop

KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reenable_gates(monkeypatch):
    monkeypatch.setenv("EXECUTION_READINESS_GATE_ENABLED", "true")
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "true")


@pytest.fixture(autouse=True)
def _isolate_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))


class _DummyResp:
    def __init__(self, status_code: int = 200, text: str = "{}"):
        self.status_code = status_code
        self.text = text


class _DummyHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, path, headers=None, params=None, json_body=None, dry_run=False):
        self.calls.append({"method": method, "path": path, "dry_run": dry_run})
        return "https://mockapi.kiwoom.com" + path, _DummyResp(200, '{"ok":true}')


def _mk_req(symbol: str = "005930") -> PreparedRequest:
    return PreparedRequest(api_id="ORDER_SUBMIT", method="POST", path="/api/dostk/ordr",
                            headers={}, query={}, body={"stk_cd": symbol, "ord_qty": "1"})


def _mk_non_mutation_req() -> PreparedRequest:
    # Deliberately NOT a mutation-shaped (BUY/SELL/CANCEL/MODIFY) api_id --
    # RealExecutor.execute() routes those through a separate
    # _execute_mutation() broker-safety path (Step5B) with its own transport
    # semantics; PAPER-2 only needs to prove EXECUTION_ENABLED=true reaches
    # the HTTP layer at all, which the plain (non-mutation) path already
    # demonstrates directly and simply, matching this repo's own existing
    # RealExecutor unit-test convention (test_real_executor_mock_mode_allowed.py).
    return PreparedRequest(api_id="X", method="POST", path="/orders", headers={}, query={}, body={"b": 2})


# ---------------------------------------------------------------------------
# PAPER-1..4: unit-level matrix, direct RealExecutor
# ---------------------------------------------------------------------------


def test_paper1_paper_mode_disabled_zero_dispatch(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mk_req(), auth_token="t")
    assert http.calls == []


def test_paper2_paper_mode_enabled_broker_path_reachable(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.delenv("ALLOW_REAL_EXECUTION", raising=False)
    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)
    out = ex.execute(_mk_non_mutation_req(), auth_token="t")
    assert out.meta.get("executor") == "real"
    assert len(http.calls) == 1
    assert http.calls[0]["dry_run"] is False


def test_paper3_live_mode_disabled_zero_dispatch(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)
    with pytest.raises(ExecutionDisabledError):
        ex.execute(_mk_req(), auth_token="t")
    assert http.calls == []


def test_paper4_live_mode_enabled_but_not_allow_real_zero_dispatch(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("ALLOW_REAL_EXECUTION", "false")
    http = _DummyHttp()
    ex = RealExecutor(settings=Settings.from_env(env_path="__missing__.env"), http=http)
    with pytest.raises(ExecutionDisabledError) as exc:
        ex.execute(_mk_req(), auth_token="t")
    assert "REAL_EXECUTION_NOT_ALLOWED" in str(exc.value)
    assert http.calls == []


# ---------------------------------------------------------------------------
# Runtime survival: integrated chain, tick N blocked -> tick N+1 executes
# ---------------------------------------------------------------------------


def _fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
    return state


def _fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["selected"] = {"symbol": "005930"}
    return state


def _make_fake_monitor(side: str):
    def _fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = [{"symbol": "005930", "side": side, "qty": 1, "price": 70000, "thesis": "paper-survival"}]
        return state
    return _fake_monitor


def _fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
    state["decision"] = "approve"
    return state


class _StubOpenOrderReader:
    def get_open_orders_now(self, **kw):
        return []


class _StubClaimStore:
    def list_active_physical_claims(self, *, limit=200):
        return []


def _run_one_tick(monkeypatch, tmp_path, *, side: str, tick_no: int) -> Dict[str, Any]:
    cat = tmp_path / "api_catalog.jsonl"
    if not cat.exists():
        cat.write_text(
            '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
            encoding="utf-8",
        )
    monkeypatch.setattr(build_portfolio_snapshot_mod, "build_portfolio_snapshot", _fake_build_portfolio_snapshot)
    monkeypatch.setattr(strategist_node_mod, "strategist_node", _fake_strategist)
    monkeypatch.setattr(scanner_node_mod, "scanner_node", _fake_scanner)
    monkeypatch.setattr(monitor_node_mod, "monitor_node", _make_fake_monitor(side))
    monkeypatch.setattr(decision_node_mod, "decision_node", _fake_decision)

    state = {
        "runtime_phase": "session",
        "catalog_path": str(cat),
        "runtime_ownership": {"instance_id": f"survival-{tick_no}", "generation": 1, "recovery_required": False},
        "open_order_reader": _StubOpenOrderReader(),
        "intent_state_store": _StubClaimStore(),
        "recent_buy_guard_path": str(tmp_path / f"recent_buy_guard_{tick_no}.json"),
        "recent_sell_guard_path": str(tmp_path / f"recent_sell_guard_{tick_no}.json"),
    }
    return _run_integrated_chain(state, execute_fn=execute_from_packet)


def test_execution_disabled_buy_blocked_then_next_tick_executes(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    out1 = _run_one_tick(monkeypatch, tmp_path, side="BUY", tick_no=1)
    execution1 = out1.get("execution") or {}
    assert execution1.get("allowed") is False
    assert execution1.get("broker_outcome") == "NOT_SENT"
    assert "EXECUTION_DISABLED" in execution1.get("reason", "")

    # Runtime did not crash -- a SECOND, independent tick runs normally and
    # reaches the exact same deterministic outcome again, proving the
    # process (not just this one call) survives.
    out2 = _run_one_tick(monkeypatch, tmp_path, side="BUY", tick_no=2)
    execution2 = out2.get("execution") or {}
    assert execution2.get("allowed") is False
    assert execution2.get("broker_outcome") == "NOT_SENT"


def test_execution_disabled_sell_blocked_then_next_tick_executes(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    out1 = _run_one_tick(monkeypatch, tmp_path, side="SELL", tick_no=1)
    execution1 = out1.get("execution") or {}
    assert execution1.get("allowed") is False
    assert execution1.get("broker_outcome") == "NOT_SENT"

    out2 = _run_one_tick(monkeypatch, tmp_path, side="SELL", tick_no=2)
    execution2 = out2.get("execution") or {}
    assert execution2.get("allowed") is False
    assert execution2.get("broker_outcome") == "NOT_SENT"


def test_unexpected_exception_still_raises_not_swallowed(monkeypatch, tmp_path):
    """Section 5's own hard requirement: this fix must NOT become a broad
    `except Exception: continue`. A genuinely unexpected exception (not
    ExecutionDisabledError) from the executor must still propagate."""
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    class _RaisingExecutor:
        def __init__(self):
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            raise RuntimeError("genuinely unexpected internal failure")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    executor = _RaisingExecutor()
    state = {
        "catalog_path": str(cat),
        "executor": executor,
        "open_order_snapshot": {
            "rows": [],
            "_health": {"reader_ok": True, "fetched_epoch": int(time.time())},
        },
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }
    with pytest.raises(RuntimeError):
        execute_from_packet(state)
    assert executor.calls == 1


def test_execution_disabled_survives_many_ticks_via_run_live_loop(monkeypatch, tmp_path):
    """Section 7/9: EXECUTION_ENABLED=false must remain stable across many
    ticks, driven through the real run_live_loop mechanics (not just direct
    function calls) -- 40 ticks here (scaled down from "hundreds" to keep
    this test fast; the exception-handling boundary itself is the same
    single code path exercised identically on every tick, so 40 consecutive
    successes is already conclusive that it is not a fluke)."""
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_ENABLED", "false")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    tick_count = {"n": 0}
    blocked_count = {"n": 0}

    def fake_run_once(state, dt=None):
        tick_count["n"] += 1
        exec_state = {
            "catalog_path": str(cat),
            "decision_packet": {
                "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
                "risk": {"open_positions": 0},
                "exec_context": {},
            },
        }
        out = execute_from_packet(exec_state)
        if out["execution"]["allowed"] is False and out["execution"]["broker_outcome"] == "NOT_SENT":
            blocked_count["n"] += 1
        return state

    from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore

    rc = run_live_loop(
        {"symbol": "005930", "m13_tick_pipeline": "integrated_chain"},
        once=False,
        sleep_sec=1,
        session_hard_gate=False,
        lock_path=tmp_path / "m13.lock",
        lock_stale_sec=30,
        now_fn=lambda: datetime(2026, 4, 20, 9, 5, tzinfo=KST),
        run_once_fn=fake_run_once,
        sleep_fn=lambda _: None,
        ownership_store=SQLiteRuntimeOwnershipStore(str(tmp_path / "runtime_ownership.db")),
        shutdown_flag=_TickCountShutdownFlag(tick_count, max_ticks=40),
    )

    assert rc == 0
    assert tick_count["n"] == 40
    assert blocked_count["n"] == 40


class _TickCountShutdownFlag:
    """Mimics ShutdownRequested's interface, but `requested` is a pure
    function of an externally-mutated tick counter (incremented by
    fake_run_once itself) rather than an internal call-counter -- robust
    against exactly how many times run_live_loop happens to poll
    `.requested` per iteration (top-of-loop, post-tick, and once per sleep
    step all read the same underlying value, no parity assumptions
    needed). Stops the loop the instant the Nth tick has actually run."""

    def __init__(self, tick_count: Dict[str, int], max_ticks: int):
        self._tick_count = tick_count
        self.max_ticks = max_ticks
        self.signal_name = "TEST_LIMIT"

    @property
    def requested(self) -> bool:
        return self._tick_count["n"] >= self.max_ticks

    def request(self, signal_name: str) -> None:
        pass
