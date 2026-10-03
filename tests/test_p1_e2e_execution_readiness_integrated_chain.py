"""P1 -- genuine end-to-end coverage of the execution readiness authority
through the ACTUAL production call graph: `graphs.commander_runtime.
_run_integrated_chain` (Strategist -> Scanner -> Monitor -> decision_node
-> Supervisor -> execute_from_packet), with the REAL
`graphs.nodes.build_execution_readiness` node and the REAL
`_evaluate_execution_readiness_guard` both genuinely active.

Does NOT rely on conftest.py's project-wide
`_disable_execution_readiness_gate_by_default` fixture -- explicitly
re-enables the gate itself. Mirrors
tests/test_p0a_e2e_open_order_guard_integrated_chain.py's own approach and
reasoning exactly.
"""

from __future__ import annotations

import time
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
def _reenable_execution_readiness_gate(monkeypatch):
    monkeypatch.setenv("EXECUTION_READINESS_GATE_ENABLED", "true")


@pytest.fixture(autouse=True)
def _reenable_open_order_reconciliation_guard(monkeypatch):
    # This E2E path also passes through the P0-A guard -- keep it genuinely
    # active too, rather than accidentally relying on it being disabled.
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "true")


@pytest.fixture(autouse=True)
def _isolate_canonical_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))
    monkeypatch.setenv("EXECUTION_MODE", "real")


class _StubBrokerExecutor:
    """Never touches the network -- injected via state["executor"], the
    same officially-supported override execute_from_packet.py already
    resolves before falling back to get_executor(). EXECUTION_MODE=real is
    required here (the readiness gate only applies in real mode); this
    stub is what keeps that real-mode requirement from ever reaching
    RealExecutor's genuine HTTP/token-issuance path."""

    def execute(self, request):  # type: ignore[no-untyped-def]
        class _Result:
            payload = {
                "api_ok": True,
                "broker_code": "0000",
                "broker_message": "accepted",
                "order_id": "E2E-STUB-1",
                "filled_qty": 0,
                "filled_price": None,
            }

        return _Result()


class _StubOpenOrderReader:
    def __init__(self, rows: List[Dict[str, Any]] | None = None):
        self._rows = rows if rows is not None else []

    def get_open_orders_now(self, **kwargs):
        return list(self._rows)


class _StubClaimStore:
    def __init__(self, claims: List[Dict[str, Any]] | None = None):
        self._claims = claims if claims is not None else []

    def list_active_physical_claims(self, *, limit=200):
        return list(self._claims)


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


def _run(monkeypatch, tmp_path, *, runtime_ownership, open_order_reader, intent_state_store):
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
        "runtime_ownership": runtime_ownership,
        "open_order_reader": open_order_reader,
        "intent_state_store": intent_state_store,
        "executor": _StubBrokerExecutor(),
        "recent_buy_guard_path": str(tmp_path / "recent_buy_guard.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell_guard.json"),
    }
    return _run_integrated_chain(state, execute_fn=execute_from_packet)


def test_e2e_fully_ready_allows_buy_admission(monkeypatch, tmp_path):
    out = _run(
        monkeypatch, tmp_path,
        runtime_ownership={"instance_id": "e2e-1", "generation": 1, "recovery_required": False},
        open_order_reader=_StubOpenOrderReader(rows=[]),
        intent_state_store=_StubClaimStore(claims=[]),
    )

    assert isinstance(out.get("execution_readiness"), dict)
    assert out["execution_readiness"]["ready"] is True

    execution = out.get("execution") or {}
    assert execution.get("reason") not in ("execution_not_ready", "execution_readiness_missing")


def test_e2e_recovery_required_blocks_first_tick_admission(monkeypatch, tmp_path):
    out = _run(
        monkeypatch, tmp_path,
        runtime_ownership={"instance_id": "e2e-2", "generation": 2, "recovery_required": True},
        open_order_reader=_StubOpenOrderReader(rows=[]),
        # Step5C not yet reachable this instant -- realistic first-tick-
        # after-takeover uncertainty -- guarantees recovery cannot silently
        # self-clear in this same test.
        intent_state_store=_StubClaimStore(claims=[{"physical_order_key": "irrelevant"}]),
    )

    execution = out.get("execution") or {}
    assert execution.get("allowed") is False
    assert execution.get("reason") == "execution_not_ready"
    reasons = execution["execution_readiness_guard"]["reasons"]
    assert "recovery_required" in reasons
    assert "unresolved_step5d_orphan_claim" in reasons


def test_e2e_step5d_orphan_blocks_even_a_different_symbol_order(monkeypatch, tmp_path):
    out = _run(
        monkeypatch, tmp_path,
        runtime_ownership={"instance_id": "e2e-3", "generation": 1, "recovery_required": False},
        open_order_reader=_StubOpenOrderReader(rows=[]),
        # Orphan claim for a completely different symbol/shape than the
        # monitor's own BUY 005930 intent -- Step5C's own exact-fingerprint
        # CAS would not catch this; the readiness gate must.
        intent_state_store=_StubClaimStore(claims=[{"physical_order_key": "000660-SELL-orphan"}]),
    )

    execution = out.get("execution") or {}
    assert execution.get("allowed") is False
    assert execution.get("reason") == "execution_not_ready"
    assert "unresolved_step5d_orphan_claim" in execution["execution_readiness_guard"]["reasons"]
