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
    assert broker_day_pnl.get("pnl_ratio") == 0.0028
    assert broker_day_pnl.get("fee") == 12
    assert broker_day_pnl.get("tax") == 8


def test_attach_broker_day_pnl_uses_kiwoom_truth_for_mock_broker_execution() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "005930"
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 10,
                        "filled_price": 295500,
                        "buy_price": 291975,
                        "realized_pnl": -14306,
                        "pnl_ratio": -0.0049,
                        "fee": 20550,
                        "tax": 5909,
                    }
                ],
                "source": "kiwoom.ka10077",
            }

    out = attach_broker_day_pnl(
        {
            "executor": {
                "broker_env": "mock",
                "effective_mode": "mock_broker_http",
                "order_request_summary": {"action": "SELL", "symbol": "005930"},
            }
        },
        context={
            "trade_day": "2026-05-14",
            "action": "SELL",
            "symbol": "005930",
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
            "execution_details": {"filled_qty": 10, "filled_price": 295500.0},
        },
    )

    execution_context = out.get("execution_context") or {}
    broker_day_pnl = execution_context.get("broker_day_pnl") or {}
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("source") == "kiwoom.ka10077"
    assert broker_day_pnl.get("pnl_ratio") == -0.0049
    assert broker_day_pnl.get("realized_pnl") == -14306.0


def test_attach_broker_day_pnl_keeps_ratio_scaled_kiwoom_return_rate() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "178320",
                        "filled_qty": 1,
                        "filled_price": 56700,
                        "buy_price": 56800,
                        "realized_pnl": -593,
                        "pnl_ratio": -0.0104,
                        "fee": 380,
                        "tax": 113,
                    }
                ],
                "source": "kiwoom.ka10077",
            }

    out = attach_broker_day_pnl(
        {
            "execution": {
                "action": "SELL",
                "symbol": "178320",
                "qty": 1,
                "ts": "2026-04-29T06:20:40+00:00",
            }
        },
        context={
            "trade_day": "2026-04-29",
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
            "execution_context": {
                "broker_order_status": {
                    "side": "SELL",
                    "symbol": "178320",
                    "filled_qty": 1,
                    "filled_price": 56700,
                }
            },
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("pnl_ratio") == -0.0104


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
    assert broker_day_pnl.get("row_count") == 2


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


def test_attach_broker_day_pnl_aggregates_split_rows_before_qty_fallback() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "006910"
            return {
                "rows": [
                    {
                        "symbol": "006910",
                        "filled_qty": 10,
                        "filled_price": 14690,
                        "buy_price": 14735,
                        "realized_pnl": -1763,
                        "pnl_ratio": -0.012,
                        "fee": 1020,
                        "tax": 293,
                    },
                    {
                        "symbol": "006910",
                        "filled_qty": 1,
                        "filled_price": 14790,
                        "buy_price": 14780,
                        "realized_pnl": -119,
                        "pnl_ratio": -0.008,
                        "fee": 102,
                        "tax": 29,
                    },
                    {
                        "symbol": "006910",
                        "filled_qty": 9,
                        "filled_price": 14790,
                        "buy_price": 14780,
                        "realized_pnl": -1096,
                        "pnl_ratio": -0.008,
                        "fee": 918,
                        "tax": 266,
                    },
                    {
                        "symbol": "006910",
                        "filled_qty": 10,
                        "filled_price": 14360,
                        "buy_price": 14370,
                        "realized_pnl": -1387,
                        "pnl_ratio": -0.0097,
                        "fee": 1000,
                        "tax": 287,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 10,
                "filled_price": 14790,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 10,
                "filled_price": 14780,
                "broker_truth_source": "kiwoom.order_status",
            },
        },
        context={
            "trade_day": "2026-05-04",
            "action": "SELL",
            "symbol": "006910",
            "execution_details": {
                "filled_qty": 10,
                "filled_price": 14790,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 10,
                "filled_price": 14780,
                "broker_truth_source": "kiwoom.order_status",
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_split_buy_sell_qty_exact"
    assert broker_day_pnl.get("source_row_count") == 2
    assert broker_day_pnl.get("filled_qty") == 10
    assert broker_day_pnl.get("filled_price") == 14790.0
    assert broker_day_pnl.get("buy_price") == 14780.0
    assert broker_day_pnl.get("realized_pnl") == -1215.0
    assert broker_day_pnl.get("fee") == 1020
    assert broker_day_pnl.get("tax") == 295


def test_attach_broker_day_pnl_aggregates_split_rows_by_weighted_sell_average() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "018880",
                        "filled_qty": 80,
                        "filled_price": 5440,
                        "buy_price": 5410,
                        "realized_pnl": -1499,
                        "pnl_ratio": -0.35,
                        "fee": 3030,
                        "tax": 869,
                    },
                    {
                        "symbol": "018880",
                        "filled_qty": 50,
                        "filled_price": 5440,
                        "buy_price": 5410,
                        "realized_pnl": -934,
                        "pnl_ratio": -0.35,
                        "fee": 1890,
                        "tax": 544,
                    },
                    {
                        "symbol": "018880",
                        "filled_qty": 145,
                        "filled_price": 5430,
                        "buy_price": 5410,
                        "realized_pnl": -4164,
                        "pnl_ratio": -0.53,
                        "fee": 5490,
                        "tax": 1574,
                    },
                    {
                        "symbol": "018880",
                        "filled_qty": 100,
                        "filled_price": 5400,
                        "buy_price": 5410,
                        "realized_pnl": -5737,
                        "pnl_ratio": -1.08,
                        "fee": 3700,
                        "tax": 1057,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    out = attach_broker_day_pnl(
        {
            "execution_details": {
                "filled_qty": 275,
                "filled_price": 5435,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 275,
                "filled_price": 5410,
                "broker_truth_source": "kiwoom.order_status",
            },
        },
        context={
            "trade_day": "2026-05-06",
            "action": "SELL",
            "symbol": "018880",
            "execution_details": {
                "filled_qty": 275,
                "filled_price": 5435,
                "broker_truth_source": "kiwoom.order_status",
            },
            "entry_execution_details": {
                "filled_qty": 275,
                "filled_price": 5410,
                "broker_truth_source": "kiwoom.order_status",
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_split_buy_weighted_sell_qty_exact"
    assert broker_day_pnl.get("filled_qty") == 275
    assert broker_day_pnl.get("filled_price") == 5435.0
    assert broker_day_pnl.get("buy_price") == 5410.0
    assert broker_day_pnl.get("realized_pnl") == -6597.0
    assert broker_day_pnl.get("fee") == 10410
    assert broker_day_pnl.get("tax") == 2987


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


def test_attach_broker_day_pnl_uses_buy_anchor_when_sell_price_unavailable_for_repeated_symbol_rows() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218100,
                        "buy_price": 217750,
                        "realized_pnl": 350.0,
                        "pnl_ratio": 0.0016,
                        "fee": 1520,
                        "tax": 436,
                    },
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218300,
                        "buy_price": 218000,
                        "realized_pnl": 300.0,
                        "pnl_ratio": 0.0014,
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
                "broker_truth_source": "kiwoom.order_status",
            }
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "005930",
            "execution_details": {
                "filled_qty": 1,
                "broker_truth_source": "kiwoom.order_status",
            },
            "monitor_context": {
                "average_price": 217750,
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is True
    assert broker_day_pnl.get("match_mode") == "symbol_qty_monitor_buy_anchor"
    assert broker_day_pnl.get("filled_price") == 218100.0
    assert broker_day_pnl.get("buy_price") == 217750.0


def test_attach_broker_day_pnl_keeps_repeated_symbol_rows_ambiguous_when_buy_anchor_margin_is_thin() -> None:
    class _FakeReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218100,
                        "buy_price": 217750,
                        "realized_pnl": 350.0,
                        "pnl_ratio": 0.0016,
                        "fee": 1520,
                        "tax": 436,
                    },
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 218300,
                        "buy_price": 217810,
                        "realized_pnl": 490.0,
                        "pnl_ratio": 0.0022,
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
                "broker_truth_source": "kiwoom.order_status",
            }
        },
        context={
            "trade_day": "2026-04-21",
            "action": "SELL",
            "symbol": "005930",
            "execution_details": {
                "filled_qty": 1,
                "broker_truth_source": "kiwoom.order_status",
            },
            "monitor_context": {
                "average_price": 217780,
            },
            "broker_day_pnl_reader": _FakeReader(),
            "broker_day_truth_lookup_enabled": True,
        },
    )

    broker_day_pnl = ((out.get("execution_context") or {}).get("broker_day_pnl") or {})
    assert broker_day_pnl.get("authoritative") is False
    assert broker_day_pnl.get("match_mode") == "ambiguous_symbol_rows"
    assert broker_day_pnl.get("row_count") == 2
