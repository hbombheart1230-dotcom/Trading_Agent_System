from __future__ import annotations

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION,
    extract_account_orders_rows,
    extract_market_quotes,
    extract_order_status,
)


def test_m22_contract_extract_market_quote_from_ready_result_data():
    state = {
        "skill_results": {
            "market.quote": {
                "result": {
                    "action": "ready",
                    "data": {"symbol": "A005930", "cur": 70000},
                }
            }
        }
    }
    quotes, meta = extract_market_quotes(state)
    assert meta["contract_version"] == CONTRACT_VERSION
    assert meta["present"] is True
    assert meta["used"] is True
    assert meta["errors"] == []
    assert quotes["005930"]["symbol"] == "005930"
    assert quotes["005930"]["price"] == 70000


def test_m22_contract_extract_account_orders_rows_from_data_wrapper():
    state = {
        "skill_results": {
            "account.orders": {
                "data": {
                    "rows": [
                        {"symbol": "A005930", "order_id": "ord-1"},
                        {"symbol": "000660", "order_id": "ord-2"},
                    ]
                }
            }
        }
    }
    rows, meta = extract_account_orders_rows(state)
    assert meta["contract_version"] == CONTRACT_VERSION
    assert meta["present"] is True
    assert meta["used"] is True
    assert meta["errors"] == []
    assert len(rows) == 2


def test_m22_contract_extract_order_status_reports_contract_violation():
    state = {
        "skill_results": {
            "order.status": "not-a-dict",
        }
    }
    summary, meta = extract_order_status(state)
    assert summary is None
    assert meta["contract_version"] == CONTRACT_VERSION
    assert meta["present"] is True
    assert meta["used"] is False
    assert "order.status:contract_violation" in meta["errors"]
