"""P0-A -- pending/open-order reconciliation guard on the entry (BUY) path.

Restart-safety scenario under test: BUY dispatched -> broker pending/open ->
runtime crash/restart -> position not yet visible -> a fresh entry intent for
the SAME symbol must not be allowed to dispatch a second BUY while the first
is still unresolved at the broker.

DETERMINISTIC design (2026-09-17 redesign, real-readiness hardening): the
guard consumes `state["open_order_snapshot"]`, populated UNCONDITIONALLY
every tick by `graphs/nodes/build_open_order_snapshot.py` (wired directly
into the canonical tick flow in `libs/runtime/commander/session_context.py`,
BEFORE strategist/scanner/monitor/decision/execution ever run). It no longer
depends on some OTHER node opportunistically having populated
`state["skill_results"]["account.orders"]` this tick -- absence of that
upstream data used to mean "nothing to check, pass"; now absence, staleness,
or a reader error on `open_order_snapshot` all fail CLOSED (UNKNOWN ->
block), per the "KNOWN EMPTY -> proceed / KNOWN PENDING same-symbol-BUY ->
block / UNKNOWN or STALE -> block" principle. See
graphs/nodes/execute_from_packet.py::_evaluate_open_order_reconciliation_guard's
own docstring for the full reasoning, including why this fetch mechanism
(KiwoomOrderFillReader, not the shared skill-runner path) does not repeat the
prior ~29-test regression from an earlier, reverted force-hydration attempt.

Covers both the guard function directly (`_evaluate_open_order_reconciliation_guard`)
and its wiring into the real `execute_from_packet` BUY chain.
"""

from __future__ import annotations

import time

import pytest

from graphs.nodes.execute_from_packet import (
    _evaluate_open_order_reconciliation_guard,
    execute_from_packet,
)


@pytest.fixture(autouse=True)
def _isolate_canonical_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_ROOT", str(tmp_path / "reports"))


@pytest.fixture(autouse=True)
def _reenable_open_order_reconciliation_guard(monkeypatch):
    """This file's whole purpose is testing this guard -- override
    conftest.py's project-wide default-disable (see
    `_disable_open_order_reconciliation_guard_by_default` there). A
    conftest.py autouse fixture of the same (function) scope runs before a
    same-scope autouse fixture defined in the test module itself, so this
    setenv reliably wins for every test in this file."""
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "true")


def _order(action: str = "BUY", symbol: str = "005930") -> dict:
    return {"action": action, "symbol": symbol, "qty": 1, "price": None, "order_type": "market"}


def _snapshot(rows: list, *, reader_ok: bool = True, reader_error: str = "", fetched_epoch: int | None = None) -> dict:
    if fetched_epoch is None:
        fetched_epoch = int(time.time())
    return {
        "rows": rows,
        "_health": {
            "reader_ok": reader_ok,
            "reader_error": reader_error,
            "source": "reader",
            "fetched_epoch": fetched_epoch,
        },
    }


def _row(symbol: str, ord_no: str, *, side: str = "BUY", status: str = "접수", order_qty: int = 10, filled_qty: int = 0) -> dict:
    return {
        "symbol": symbol,
        "ord_no": ord_no,
        "side": side,
        "status": status,
        "order_qty": order_qty,
        "filled_qty": filled_qty,
    }


# ---------------------------------------------------------------------------
# Guard function, direct
# ---------------------------------------------------------------------------


def test_sell_action_bypasses_guard_entirely():
    state: dict = {}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order(action="SELL"))
    assert allowed is True
    assert reason == ""
    assert details["enabled"] is False


def test_guard_disabled_via_env_flag_passes_through(monkeypatch):
    monkeypatch.setenv("OPEN_ORDER_RECONCILIATION_GUARD_ENABLED", "false")
    state: dict = {}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is True
    assert details["skip_reason"] == "guard_disabled"


def test_buy_blocked_when_open_order_snapshot_missing():
    # UNKNOWN: the deterministic per-tick node never ran (or this state was
    # never routed through the real tick flow) -- fail CLOSED, not silently
    # pass as the old opportunistic guard did.
    state: dict = {}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_missing"


def test_buy_blocked_when_snapshot_reader_reports_error():
    state = {"open_order_snapshot": _snapshot([], reader_ok=False, reader_error="broker_timeout")}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_reader_error"
    assert "broker_timeout" in details["reader_error"]


def test_buy_blocked_when_snapshot_missing_timestamp():
    snap = _snapshot([])
    del snap["_health"]["fetched_epoch"]
    state = {"open_order_snapshot": snap}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_missing_timestamp"


def test_buy_blocked_when_snapshot_is_stale(monkeypatch):
    monkeypatch.setenv("OPEN_ORDER_SNAPSHOT_MAX_AGE_SECONDS", "60")
    stale_epoch = int(time.time()) - 999
    state = {"open_order_snapshot": _snapshot([], fetched_epoch=stale_epoch)}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_stale"
    assert details["max_age_seconds"] == 60


def test_buy_blocked_when_snapshot_rows_malformed():
    snap = _snapshot([])
    snap["rows"] = "not-a-list"
    state = {"open_order_snapshot": snap}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is False
    assert reason == "open_order_snapshot_malformed"


def test_buy_allowed_when_no_pending_orders_for_symbol():
    state = {"open_order_snapshot": _snapshot([])}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order())
    assert allowed is True
    assert reason == ""
    assert details["checked_rows"] == 0


def test_buy_allowed_when_pending_order_exists_for_a_different_symbol():
    state = {"open_order_snapshot": _snapshot([_row("000660", "1")])}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order(symbol="005930"))
    assert allowed is True
    assert reason == ""


def test_buy_blocked_when_pending_buy_order_exists_for_same_symbol():
    state = {"open_order_snapshot": _snapshot([_row("005930", "998877")])}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order(symbol="005930"))
    assert allowed is False
    assert reason == "pending_open_order_exists_for_symbol"
    assert details["pending_count"] == 1
    assert details["pending_orders"][0]["ord_no"] == "998877"


def test_buy_allowed_when_same_symbol_pending_order_is_sell_side():
    # A pending SELL for the same symbol (e.g. closing an existing position)
    # must not block a new BUY -- this guard is scoped to same-side (BUY)
    # duplication only, mirroring the existing sell-side guard's own scope.
    state = {"open_order_snapshot": _snapshot([_row("005930", "5", side="SELL")])}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order(symbol="005930"))
    assert allowed is True
    assert reason == ""


def test_buy_allowed_when_same_symbol_order_is_already_filled():
    state = {
        "open_order_snapshot": _snapshot(
            [_row("005930", "1", status="체결완료", order_qty=10, filled_qty=10)]
        )
    }
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, _order(symbol="005930"))
    assert allowed is True
    assert reason == ""


def test_buy_allowed_with_no_symbol_defers_to_symbol_format_guard():
    state = {"open_order_snapshot": _snapshot([])}
    allowed, reason, details = _evaluate_open_order_reconciliation_guard(state, {"action": "BUY", "symbol": ""})
    assert allowed is True
    assert details["skip_reason"] == "no_symbol"


# ---------------------------------------------------------------------------
# Wiring into the real execute_from_packet BUY chain
# ---------------------------------------------------------------------------


def test_execute_from_packet_blocks_buy_via_open_order_reconciliation_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "open_order_snapshot": _snapshot([_row("005930", "998877")]),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "pending_open_order_exists_for_symbol"
    assert out["execution"]["open_order_reconciliation_guard"]["pending_count"] == 1


def test_execute_from_packet_allows_buy_when_no_pending_order_present(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "open_order_snapshot": _snapshot([]),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True


def test_execute_from_packet_blocks_buy_when_open_order_snapshot_absent(tmp_path, monkeypatch):
    # UNKNOWN state (snapshot never populated this tick) must fail CLOSED
    # through the full execute_from_packet chain too, not just the guard
    # function in isolation -- this is the real-readiness behavior change
    # from the old opportunistic guard, which used to allow this case.
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "open_order_snapshot_missing"
