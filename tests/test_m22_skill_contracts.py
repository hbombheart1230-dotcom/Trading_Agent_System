from __future__ import annotations

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION,
    extract_account_orders_rows,
    extract_market_quotes,
    extract_minute_ohlcv_by_symbol,
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


def test_m22_contract_extract_minute_ohlcv_from_state_minute_root():
    state = {
        "minute_ohlcv_by_symbol": {
            "A005930": [
                {"ts": 1710000000, "open": 70000, "high": 70100, "low": 69900, "close": 70050, "volume": 1200},
                {"ts": 1710000060, "open": 70050, "high": 70200, "low": 70040, "close": 70180, "volume": 1800},
            ]
        }
    }
    rows_by_symbol, meta = extract_minute_ohlcv_by_symbol(state)
    assert meta["contract_version"] == CONTRACT_VERSION
    assert meta["present"] is True
    assert meta["used"] is True
    assert meta["errors"] == []
    assert meta["source"] == "state.minute_ohlcv_by_symbol"
    assert "005930" in rows_by_symbol
    assert len(rows_by_symbol["005930"]) == 2


def test_m22_contract_extract_minute_ohlcv_from_skill_ready_data():
    state = {
        "skill_results": {
            "market.minute_ohlcv": {
                "result": {
                    "action": "ready",
                    "data": {
                        "symbol": "A005930",
                        "rows": [
                            {"ts": 1710000000, "open": 70000, "high": 70100, "low": 69900, "close": 70050, "volume": 1200},
                            {"ts": 1710000060, "open": 70050, "high": 70200, "low": 70040, "close": 70180, "volume": 1800},
                        ],
                    },
                }
            }
        }
    }
    rows_by_symbol, meta = extract_minute_ohlcv_by_symbol(state)
    assert meta["present"] is True
    assert meta["used"] is True
    assert meta["source"] == "skill.minute_ohlcv"
    assert len(rows_by_symbol["005930"]) == 2
