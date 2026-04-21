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
