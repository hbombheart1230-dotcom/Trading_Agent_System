from __future__ import annotations

from libs.reporting.kiwoom_day_trade_truth import attach_broker_day_pnl


def test_attach_broker_day_pnl_matches_exact_symbol_qty_and_price() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "005930"
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 2,
                        "filled_price": 70100,
                        "buy_price": 69900,
                        "realized_pnl": 400,
                        "pnl_ratio": 0.0028,
                        "fee": 12,
                        "tax": 8,
                    }
                ],
                "source": "kiwoom.ka10077",
            }

    out = attach_broker_day_pnl(
        {
            "execution": {
                "action": "SELL",
                "symbol": "005930",
                "qty": 2,
                "ts": "2026-04-20T06:10:00+00:00",
            }
        },
        context={
            "trade_day": "2026-04-20",
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
            "execution_context": {
                "broker_order_status": {
                    "side": "SELL",
                    "symbol": "005930",
                    "filled_qty": 2,
                    "filled_price": 70100,
                }
            },
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_qty_price_exact"
    assert broker_day_pnl.get("realized_pnl") == 400.0
    assert broker_day_pnl.get("fee") == 12
    assert broker_day_pnl.get("tax") == 8


def test_attach_broker_day_pnl_falls_back_to_account_profit_rows_when_detail_empty() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "005930"
            return {"rows": [], "source": "kiwoom.ka10077"}

        def get_account_profit_rate_rows(self):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "today_sell_pnl": 320.0,
                        "today_fee": 14,
                        "today_tax": 9,
                    }
                ],
                "source": "kiwoom.ka10085",
            }

    out = attach_broker_day_pnl(
        {
            "execution": {
                "action": "SELL",
                "symbol": "005930",
                "qty": 1,
                "ts": "2026-04-20T06:10:00+00:00",
            }
        },
        context={
            "trade_day": "2026-04-20",
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
            "execution_context": {
                "broker_order_status": {
                    "side": "SELL",
                    "symbol": "005930",
                    "filled_qty": 1,
                    "filled_price": 70100,
                }
            },
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_account_profit_row"
    assert broker_day_pnl.get("source") == "kiwoom.ka10085"
    assert broker_day_pnl.get("realized_pnl") == 320.0
    assert broker_day_pnl.get("fee") == 14
    assert broker_day_pnl.get("tax") == 9


def test_attach_broker_day_pnl_does_not_reuse_non_order_status_fill_for_exact_price_match() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "047040",
                        "filled_qty": 1,
                        "filled_price": 33950,
                        "buy_price": 33950,
                        "realized_pnl": -286.0,
                        "pnl_ratio": -0.0084,
                        "fee": 220,
                        "tax": 66,
                    },
                    {
                        "symbol": "047040",
                        "filled_qty": 1,
                        "filled_price": 33900,
                        "buy_price": 33900,
                        "realized_pnl": -286.0,
                        "pnl_ratio": -0.0084,
                        "fee": 220,
                        "tax": 66,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 33900,
                "broker_truth_source": "kiwoom.ka10077",
            }
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "047040",
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 33900,
                "broker_truth_source": "kiwoom.ka10077",
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is False
    assert broker_day_pnl.get("match_mode") == "ambiguous_symbol_rows"


def test_attach_broker_day_pnl_uses_entry_broker_fill_to_disambiguate_same_symbol_rows() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 217750,
                        "realized_pnl": -1706.0,
                        "pnl_ratio": -0.0078,
                        "fee": 1520,
                        "tax": 436,
                    },
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 218000,
                        "realized_pnl": -1956.0,
                        "pnl_ratio": -0.0090,
                        "fee": 1520,
                        "tax": 436,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "005930",
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_buy_sell_qty_exact"
    assert broker_day_pnl.get("realized_pnl") == -1956.0


def test_attach_broker_day_pnl_uses_monitor_context_buy_estimate_for_repeated_symbol_rows() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 217750,
                        "realized_pnl": -1706.0,
                        "pnl_ratio": -0.0078,
                        "fee": 1520,
                        "tax": 436,
                    },
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 218000,
                        "realized_pnl": -1956.0,
                        "pnl_ratio": -0.0090,
                        "fee": 1520,
                        "tax": 436,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            }
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "005930",
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
            "monitor_context": {
                "current_price": 218000,
                "account_pnl_ratio": 0.0,
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_qty_price_estimated_buy_anchor"
    assert broker_day_pnl.get("buy_price") == 218000.0
    assert broker_day_pnl.get("estimated_buy_price") == 218000.0


def test_attach_broker_day_pnl_uses_monitor_average_price_anchor_for_repeated_symbol_rows() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 217750,
                        "realized_pnl": -1706.0,
                        "pnl_ratio": -0.0078,
                        "fee": 1520,
                        "tax": 436,
                    },
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218000,
                        "buy_price": 218000,
                        "realized_pnl": -1956.0,
                        "pnl_ratio": -0.0090,
                        "fee": 1520,
                        "tax": 436,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            }
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "005930",
            "execution_details": {
                "filled_qty": 1,
                "filled_price": 218000,
                "broker_truth_source": "kiwoom.order_status",
            },
            "monitor_context": {
                "current_price": 218000,
                "average_price": 217750,
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_qty_price_monitor_buy_anchor"
    assert broker_day_pnl.get("buy_price") == 217750.0
    assert broker_day_pnl.get("monitor_buy_anchor_source") == "position_average_price"
    assert broker_day_pnl.get("monitor_buy_anchor_price") == 217750.0
