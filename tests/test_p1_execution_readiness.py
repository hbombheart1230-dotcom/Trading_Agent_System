"""P1 -- execution readiness authority (READY-1..READY-12).

Covers three layers:
  1. The pure decision rule (libs/execution/execution_readiness.py) --
     fast, input-combination coverage.
  2. The per-tick evidence-gathering node
     (graphs/nodes/build_execution_readiness.py), including the explicit
     recovery_required clearing semantics.
  3. The enforcement guard wired into execute_from_packet.py
     (_evaluate_execution_readiness_guard).

Does NOT rely on conftest.py's project-wide
`_disable_execution_readiness_gate_by_default` fixture -- explicitly
re-enables the gate itself, the same way tests/test_p0a_open_order_
reconciliation_guard.py does for its own guard.
"""

from __future__ import annotations

import time

import pytest

from graphs.nodes.build_execution_readiness import build_execution_readiness
from graphs.nodes.execute_from_packet import _evaluate_execution_readiness_guard, execute_from_packet
from libs.execution.execution_readiness import evaluate_execution_readiness, validate_execution_config


@pytest.fixture(autouse=True)
def _reenable_execution_readiness_gate(monkeypatch):
    monkeypatch.setenv("EXECUTION_READINESS_GATE_ENABLED", "true")


@pytest.fixture(autouse=True)
def _isolate_canonical_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))


class _StubBrokerExecutor:
    """Never touches the network -- explicitly injected via state["executor"]
    (execute_from_packet.py's own supported override:
    `executor = state.get("executor") or get_executor()`). EXECUTION_MODE=real
    is required for this test file's scenarios (the readiness gate only
    applies in real mode), but that alone would otherwise route through
    RealExecutor's real HTTP/token-issuance path -- this stub is the "Hard
    Safety Rule"-compliant way to reach a genuine ADMITTED verdict without
    ever attempting a real or even a sandbox broker call."""

    def execute(self, request):  # type: ignore[no-untyped-def]
        class _Result:
            payload = {
                "api_ok": True,
                "broker_code": "0000",
                "broker_message": "accepted",
                "order_id": "STUB-1",
                "filled_qty": 0,
                "filled_price": None,
            }

        return _Result()


class _FakeClaimStore:
    def __init__(self, claims=None, raise_exc=None):
        self._claims = claims or []
        self._raise_exc = raise_exc

    def list_active_physical_claims(self, *, limit=200):
        if self._raise_exc is not None:
            raise self._raise_exc
        return list(self._claims)


def _healthy_portfolio_snapshot():
    return {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}


def _healthy_open_order_snapshot(rows=None):
    return {
        "rows": rows if rows is not None else [],
        "_health": {"reader_ok": True, "fetched_epoch": int(time.time())},
    }


def _healthy_ownership(recovery_required: bool = False):
    return {
        "instance_id": "abc123",
        "generation": 1,
        "recovery_required": recovery_required,
        "acquired_at": time.time(),
    }


def _healthy_state(*, recovery_required=False, orphan_claims=None, open_order_rows=None):
    return {
        "runtime_ownership": _healthy_ownership(recovery_required=recovery_required),
        "portfolio_snapshot": _healthy_portfolio_snapshot(),
        "open_order_snapshot": _healthy_open_order_snapshot(rows=open_order_rows),
        "intent_state_store": _FakeClaimStore(claims=orphan_claims),
    }


# ---------------------------------------------------------------------------
# Pure decision rule
# ---------------------------------------------------------------------------


def test_ready1_all_inputs_healthy_is_ready():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=1,
        recovery_required=False, step5c_available=True, orphan_claim_count=0,
        portfolio_reconciled=True, open_orders_reconciled=True, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is True
    assert readiness.reasons == []


def test_ready2_recovery_required_blocks():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=2,
        recovery_required=True, step5c_available=True, orphan_claim_count=0,
        portfolio_reconciled=True, open_orders_reconciled=True, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "recovery_required" in readiness.reasons


def test_ready3_step5d_orphan_blocks_all():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=1,
        recovery_required=False, step5c_available=True, orphan_claim_count=1,
        portfolio_reconciled=True, open_orders_reconciled=True, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "unresolved_step5d_orphan_claim" in readiness.reasons


def test_ready4_ownership_invalid_blocks():
    readiness = evaluate_execution_readiness(
        ownership_valid=False, runtime_instance_id=None, ownership_generation=None,
        recovery_required=False, step5c_available=True, orphan_claim_count=0,
        portfolio_reconciled=True, open_orders_reconciled=True, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "ownership_unavailable_or_unverified" in readiness.reasons


def test_ready5_portfolio_reconciliation_failure_blocks():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=1,
        recovery_required=False, step5c_available=True, orphan_claim_count=0,
        portfolio_reconciled=False, open_orders_reconciled=True, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "portfolio_reconciliation_invalid" in readiness.reasons


def test_ready6_open_order_unknown_blocks():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=1,
        recovery_required=False, step5c_available=True, orphan_claim_count=None,
        portfolio_reconciled=True, open_orders_reconciled=False, config_valid=True,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "open_order_reconciliation_invalid" in readiness.reasons
    assert "orphan_claim_status_unknown" in readiness.reasons


def test_ready8_config_invalid_blocks():
    readiness = evaluate_execution_readiness(
        ownership_valid=True, runtime_instance_id="i1", ownership_generation=1,
        recovery_required=False, step5c_available=True, orphan_claim_count=0,
        portfolio_reconciled=True, open_orders_reconciled=True, config_valid=False,
        execution_enabled=True,
    )
    assert readiness.ready is False
    assert "execution_config_invalid" in readiness.reasons


def test_validate_execution_config_accepts_typical_values(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "real")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("ALLOW_REAL_EXECUTION", "true")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930,000660")
    monkeypatch.setenv("MAX_ORDER_QTY", "10")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    ok, reasons = validate_execution_config()
    assert ok is True
    assert reasons == []


def test_validate_execution_config_rejects_non_numeric_limit(monkeypatch):
    monkeypatch.setenv("MAX_ORDER_QTY", "not-a-number")
    ok, reasons = validate_execution_config()
    assert ok is False
    assert any("max_order_qty_not_numeric" in r for r in reasons)


# ---------------------------------------------------------------------------
# Node: build_execution_readiness (evidence gathering + recovery clearing)
# ---------------------------------------------------------------------------


def test_node_healthy_state_is_ready():
    state = _healthy_state()
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is True


def test_node_missing_ownership_blocks():
    state = _healthy_state()
    del state["runtime_ownership"]
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is False
    assert "ownership_unavailable_or_unverified" in out["execution_readiness"]["reasons"]


def test_node_step5c_unreachable_blocks():
    state = _healthy_state()
    state["intent_state_store"] = _FakeClaimStore(raise_exc=RuntimeError("db locked"))
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is False
    assert "step5c_state_unavailable" in out["execution_readiness"]["reasons"]
    assert "orphan_claim_status_unknown" in out["execution_readiness"]["reasons"]


def test_node_open_order_stale_blocks():
    state = _healthy_state()
    stale_snapshot = _healthy_open_order_snapshot()
    stale_snapshot["_health"]["fetched_epoch"] = int(time.time()) - 99999
    state["open_order_snapshot"] = stale_snapshot
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is False
    assert "open_order_reconciliation_invalid" in out["execution_readiness"]["reasons"]


def test_ready9_recovery_clears_only_when_all_evidence_healthy():
    state = _healthy_state(recovery_required=True)
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is True
    assert out["execution_readiness"]["recovery_required"] is False
    assert out["runtime_ownership"]["recovery_required"] is False


def test_recovery_not_cleared_while_orphan_unresolved():
    state = _healthy_state(recovery_required=True, orphan_claims=[{"physical_order_key": "x"}])
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is False
    assert out["execution_readiness"]["recovery_required"] is True
    # The flag itself is untouched -- a later tick, once the orphan is
    # manually resolved, gets another chance to clear it.
    assert out["runtime_ownership"]["recovery_required"] is True


def test_recovery_not_cleared_by_mere_tick_when_portfolio_unhealthy():
    state = _healthy_state(recovery_required=True)
    state["portfolio_snapshot"]["_health"]["reader_ok"] = False
    out = build_execution_readiness(state)
    assert out["execution_readiness"]["ready"] is False
    assert out["runtime_ownership"]["recovery_required"] is True


# ---------------------------------------------------------------------------
# Guard: _evaluate_execution_readiness_guard direct
# ---------------------------------------------------------------------------


def _order(action: str = "BUY", symbol: str = "005930") -> dict:
    return {"action": action, "symbol": symbol, "qty": 1, "price": 70000, "order_type": "limit"}


def test_guard_mock_mode_bypasses_entirely(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state: dict = {}
    allowed, reason, details = _evaluate_execution_readiness_guard(state, _order())
    assert allowed is True
    assert details["enabled"] is False
    assert details["reason"] == "execution_mode_not_real"


def test_guard_cancel_action_bypasses(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state: dict = {}
    allowed, reason, details = _evaluate_execution_readiness_guard(state, _order(action="CANCEL"))
    assert allowed is True
    assert details["enabled"] is False


def test_guard_real_mode_missing_readiness_blocks(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state: dict = {}
    allowed, reason, details = _evaluate_execution_readiness_guard(state, _order())
    assert allowed is False
    assert reason == "execution_readiness_missing"


def test_ready11_stale_takeover_first_tick_blocks_via_guard(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = _healthy_state(recovery_required=True)
    state = build_execution_readiness(state)
    # This tick's OTHER evidence happens to also be fine, so recovery
    # clears immediately in this synthetic case -- to specifically prove
    # "stale takeover's first tick cannot dispatch," construct the more
    # realistic case where at least one other input is not yet confirmed
    # (e.g. Step5C not yet reachable this instant).
    state2 = _healthy_state(recovery_required=True)
    state2["intent_state_store"] = _FakeClaimStore(raise_exc=RuntimeError("not ready yet"))
    state2 = build_execution_readiness(state2)
    allowed, reason, details = _evaluate_execution_readiness_guard(state2, _order())
    assert allowed is False
    assert reason == "execution_not_ready"
    assert details["recovery_required"] is True


def test_ready10_different_fingerprint_order_during_orphan_blocked(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = _healthy_state(orphan_claims=[{"physical_order_key": "unrelated-order-key"}])
    state = build_execution_readiness(state)
    # A completely different symbol/qty/price than whatever the orphan
    # claim was for -- Step5C's own exact-fingerprint CAS would not have
    # blocked this; the readiness gate does, because ANY unresolved orphan
    # blocks ALL new physical execution.
    allowed, reason, details = _evaluate_execution_readiness_guard(
        state, {"action": "SELL", "symbol": "000660", "qty": 999, "price": 12345, "order_type": "limit"}
    )
    assert allowed is False
    assert reason == "execution_not_ready"
    assert "unresolved_step5d_orphan_claim" in details["reasons"]


# ---------------------------------------------------------------------------
# Wiring into the real execute_from_packet BUY/SELL chain
# ---------------------------------------------------------------------------


def _catalog(tmp_path):
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    return str(cat)


def test_execute_from_packet_allows_buy_when_fully_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = _healthy_state()
    state = build_execution_readiness(state)
    state["executor"] = _StubBrokerExecutor()
    state["catalog_path"] = _catalog(tmp_path)
    state["decision_packet"] = {
        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
        "risk": {"open_positions": 0},
        "exec_context": {},
    }
    out = execute_from_packet(state)
    assert out["execution"]["reason"] != "execution_not_ready"
    assert out["execution"]["reason"] != "execution_readiness_missing"


def test_execute_from_packet_blocks_buy_when_not_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state: dict = {
        "catalog_path": _catalog(tmp_path),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }
    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "execution_readiness_missing"


def test_ready12_normal_runtime_without_recovery_issue_unchanged(tmp_path, monkeypatch):
    # Baseline sanity: fully healthy, no recovery flag at all -- behaves
    # exactly like a normal running instance always has.
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = _healthy_state(recovery_required=False)
    state = build_execution_readiness(state)
    assert state["execution_readiness"]["ready"] is True
    state["executor"] = _StubBrokerExecutor()
    state["catalog_path"] = _catalog(tmp_path)
    state["decision_packet"] = {
        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
        "risk": {"open_positions": 0},
        "exec_context": {},
    }
    out = execute_from_packet(state)
    assert out["execution"]["reason"] not in ("execution_not_ready", "execution_readiness_missing")
