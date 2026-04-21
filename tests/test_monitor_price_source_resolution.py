from __future__ import annotations

from graphs.nodes.monitor_node import _resolve_price_with_source


def test_monitor_resolves_latest_minute_close_when_quote_snapshot_missing():
    state = {
        "minute_ohlcv_by_symbol": {
            "005930": [
                {"ts": 1774317000, "open": 70000, "high": 70100, "low": 69900, "close": 70050, "volume": 1000},
                {"ts": 1774317060, "open": 70050, "high": 70200, "low": 70000, "close": 70180, "volume": 1200},
            ]
        }
    }

    price, source = _resolve_price_with_source(
        state,
        "005930",
        {"symbol": "005930"},
    )

    assert price == 70180.0
    assert source == "state.minute_ohlcv_by_symbol.close"
