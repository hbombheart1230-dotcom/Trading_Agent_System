from __future__ import annotations

from libs.reporting.trade_execution_snapshot import (
    build_execution_details,
    build_execution_snapshot,
    merge_execution_snapshot_candidates,
    normalize_execution_row,
    score_execution_snapshot,
)


def test_normalize_execution_row_extracts_core_fields() -> None:
    snapshot = normalize_execution_row(
        {
            "order": {"action": "buy", "symbol": "000660", "qty": 2},
            "payload": {"response_payload": {"ord_no": "A123", "return_msg": "filled"}},
        },
        run_id="run-1",
        ts="2026-04-16T01:00:00+00:00",
    )

    assert snapshot["action"] == "BUY"
    assert snapshot["symbol"] == "000660"
    assert snapshot["qty"] == 2
    assert snapshot["order_id"] == "A123"
    assert snapshot["fill_status"] == "filled"
    assert snapshot["run_id"] == "run-1"


def test_merge_execution_snapshot_candidates_recovers_sparse_fields() -> None:
    merged = merge_execution_snapshot_candidates(
        [
            {"action": "BUY", "symbol": "005930", "qty": 1},
            {"broker_result": {"ord_no": "ORD-77", "status": "filled", "avg_price": 71100.0}},
        ],
        run_id="run-2",
        ts="2026-04-16T01:03:00+00:00",
    )

    assert merged["action"] == "BUY"
    assert merged["symbol"] == "005930"
    assert merged["order_id"] == "ORD-77"
    assert merged["filled_price"] == 71100.0
    assert merged["degraded_but_usable"] is True
    assert score_execution_snapshot(merged) > 0


def test_build_execution_snapshot_marks_truly_thin_case_not_usable() -> None:
    merged = build_execution_snapshot(candidates=[{"status": "ok"}])
    assert merged["degraded_but_usable"] is False
    assert merged["quality_score"] >= 0


def test_build_execution_details_keeps_contract_and_additive_fields() -> None:
    details = build_execution_details(
        {
            "execution": {"action": "BUY", "qty": 10},
            "executor": {"broker_message": "Order accepted ord_no=B49080X123 successfully."},
            "monitor": {"current_price": 45000.0},
        },
        context={"execution_context": {"summary": "Trade executed"}},
    )

    for key in ("order_status", "order_id", "execution_mode", "broker_env", "filled_qty", "avg_price"):
        assert key in details
    assert details["order_id"] == "B49080X123"
    assert details["filled_qty"] == 10
    assert details["avg_price"] == 45000.0
    assert "quality_score" in details
