"""Real-Docker-Readiness-Audit Section 3C -- genuine end-to-end coverage of
the P0-A deterministic open-order reconciliation guard through the ACTUAL
production call graph: `graphs.commander_runtime._run_integrated_chain`
(Strategist -> Scanner -> Monitor -> decision_node -> Supervisor ->
execute_from_packet), with the REAL `graphs.nodes.build_open_order_snapshot`
node and the REAL `execute_from_packet` guard chain both genuinely active.

This file does NOT rely on conftest.py's project-wide
`_disable_open_order_reconciliation_guard_by_default` fixture -- it
explicitly re-enables the guard itself, the same way
tests/test_p0a_open_order_reconciliation_guard.py and
tests/test_p0_crash_matrix.py do. Turning the guard OFF to force a pass is
exactly what this file exists to make impossible to do by accident.

Only the network boundary is stubbed (`state["open_order_reader"]` /
`state["portfolio_reader"]`, the officially supported test-injection hooks
each node already exposes) and `EXECUTION_MODE=mock` (so `get_executor()`
resolves to the real, network-free MockExecutor) -- no order is ever placed
against a real or even a fake HTTP endpoint. Strategist/Scanner/Monitor/
decision_node are faked only to make the scenario deterministic (matching
this repo's own established `_run_integrated_chain(..., execute_fn=...)`
test convention, e.g. tests/test_m21_commander_runtime_entry.py); they are
NOT the thing under test. `build_open_order_snapshot` and
`_evaluate_open_order_reconciliation_guard` are never mocked -- both run
for real.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

import graphs.nodes.build_portfolio_snapshot as build_portfolio_snapshot_mod
import graphs.nodes.decision_node as decision_node_mod
import graphs.nodes.monitor_node as monitor_node_mod
import graphs.nodes.scanner_node as scanner_node_mod
import graphs.nodes.strategist_node as strategist_node_mod
from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.execute_from_packet import execute_from_packet


@pytest.fixture(autouse=True)
def _reenable_open_order_reconciliation_guard(monkeypatch):
    """Overrides conftest.py's project-wide default-disable -- this file's
    whole purpose is proving the guard blocks/allows correctly when
    genuinely wired into the real tick flow."""
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "true")


@pytest.fixture(autouse=True)
def _isolate_canonical_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("KIWOOM_MODE", "mock")


class _StubOpenOrderReader:
    """Stubs only the broker network boundary
    (KiwoomOrderFillReader.get_open_orders_now) -- the officially supported
    override hook build_open_order_snapshot.py already exposes via
    state["open_order_reader"]. Everything else in the node
    (health-dict construction, rows shape, fetched_epoch) is real."""

    def __init__(self, rows: List[Dict[str, Any]] | None = None, raise_exc: Exception | None = None):
        self._rows = rows if rows is not None else []
        self._raise_exc = raise_exc

    def get_open_orders_now(self, **kwargs):
        if self._raise_exc is not None:
            raise self._raise_exc
        return list(self._rows)


def _fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    state["portfolio_snapshot"] = {
        "cash": 1_000_000.0,
        "positions": [],
        "_health": {"reader_ok": True, "reader_error": "", "source": "stub"},
    }
    return state


def _fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
    return state


def _fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["selected"] = {"symbol": "005930"}
    return state


def _fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
    state["intents"] = [
        {"symbol": "005930", "side": "BUY", "qty": 1, "price": 70000, "thesis": "audit-e2e"}
    ]
    return state


def _fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
    state["decision"] = "approve"
    return state


def _run(monkeypatch, tmp_path, *, open_order_reader) -> Dict[str, Any]:
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(build_portfolio_snapshot_mod, "build_portfolio_snapshot", _fake_build_portfolio_snapshot)
    monkeypatch.setattr(strategist_node_mod, "strategist_node", _fake_strategist)
    monkeypatch.setattr(scanner_node_mod, "scanner_node", _fake_scanner)
    monkeypatch.setattr(monitor_node_mod, "monitor_node", _fake_monitor)
    monkeypatch.setattr(decision_node_mod, "decision_node", _fake_decision)

    state = {
        "runtime_phase": "session",
        "catalog_path": str(cat),
        "open_order_reader": open_order_reader,
        "recent_buy_guard_path": str(tmp_path / "recent_buy_guard.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell_guard.json"),
    }
    return _run_integrated_chain(state, execute_fn=execute_from_packet)


def test_e2e_fresh_known_empty_snapshot_allows_buy_admission(monkeypatch, tmp_path):
    out = _run(monkeypatch, tmp_path, open_order_reader=_StubOpenOrderReader(rows=[]))

    # The REAL node ran and the REAL guard evaluated it -- not skipped.
    assert isinstance(out.get("open_order_snapshot"), dict)
    assert out["open_order_snapshot"]["_health"]["reader_ok"] is True

    execution = out.get("execution") or {}
    guard_details = execution.get("open_order_reconciliation_guard")
    # KNOWN EMPTY -> the open-order guard itself did not block (it may
    # still be blocked further down the chain by an unrelated guard, but
    # this guard's own verdict must be a pass, not a block).
    assert guard_details is None or execution.get("reason") != "pending_open_order_exists_for_symbol"
    assert execution.get("reason") not in (
        "open_order_snapshot_missing",
        "open_order_snapshot_reader_error",
        "open_order_snapshot_stale",
        "open_order_snapshot_malformed",
    )


def test_e2e_fresh_pending_buy_blocks_admission(monkeypatch, tmp_path):
    pending_row = {
        "symbol": "005930",
        "ord_no": "AUDIT-PENDING-1",
        "side": "BUY",
        "status": "접수",
        "order_qty": 10,
        "filled_qty": 0,
    }
    out = _run(monkeypatch, tmp_path, open_order_reader=_StubOpenOrderReader(rows=[pending_row]))

    execution = out.get("execution") or {}
    assert execution.get("allowed") is False
    assert execution.get("reason") == "pending_open_order_exists_for_symbol"
    assert execution["open_order_reconciliation_guard"]["pending_count"] == 1


def test_e2e_unknown_reader_error_blocks_admission(monkeypatch, tmp_path):
    out = _run(
        monkeypatch,
        tmp_path,
        open_order_reader=_StubOpenOrderReader(raise_exc=RuntimeError("simulated broker outage")),
    )

    execution = out.get("execution") or {}
    assert execution.get("allowed") is False
    assert execution.get("reason") == "open_order_snapshot_reader_error"
    assert "simulated broker outage" in out["open_order_snapshot"]["_health"]["reader_error"]
