from __future__ import annotations

from pathlib import Path

from scripts.run_broker_trade_reconciliation import load_local_execution_rows, reconcile_rows


def test_load_local_execution_rows_filters_day_and_extracts_order_id(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"run_id":"r1","ts_kst":"2026-03-13T10:00:00+09:00","stage":"execute_from_packet","event":"execution","payload":{"order":{"action":"BUY","symbol":"005930","qty":1},"payload":{"order_id":"001","broker_message":"ok","effective_mode":"mock_broker_http"}}}',
                '{"run_id":"r2","ts_kst":"2026-03-13T10:01:00+09:00","stage":"execute_from_packet","event":"execution","payload":{"order":{"action":"SELL","symbol":"005930","qty":1},"payload":{"effective_mode":"mock_broker_http"}}}',
                '{"run_id":"r3","ts_kst":"2026-03-12T10:00:00+09:00","stage":"execute_from_packet","event":"execution","payload":{"order":{"action":"BUY","symbol":"000660","qty":2},"payload":{"order_id":"002","broker_message":"ok"}}}',
            ]
        ),
        encoding="utf-8",
    )

    rows = load_local_execution_rows(path, day="2026-03-13")
    assert len(rows) == 1
    assert rows[0]["ord_no"] == "001"
    assert rows[0]["symbol"] == "005930"
    assert rows[0]["side"] == "BUY"


def test_reconcile_rows_reports_missing_both_sides() -> None:
    local_rows = [
        {"ord_no": "001", "symbol": "005930", "side": "BUY", "qty": 1},
        {"ord_no": "003", "symbol": "032820", "side": "SELL", "qty": 1},
    ]
    broker_rows = [
        {"ord_no": "001", "symbol": "005930", "side": "BUY", "filled_qty": 1},
        {"ord_no": "002", "symbol": "051910", "side": "BUY", "filled_qty": 2},
    ]

    out = reconcile_rows(local_rows, broker_rows)
    assert out["matched_by_ord_no"] == 1
    assert out["missing_in_local_total"] == 1
    assert out["missing_in_broker_total"] == 1
    assert out["missing_in_local"][0]["ord_no"] == "002"
    assert out["missing_in_broker"][0]["ord_no"] == "003"
