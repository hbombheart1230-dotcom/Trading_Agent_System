from __future__ import annotations

from libs.reporting.trade_regeneration_truth import rehydrate_lifecycle_bundle_execution_truth


def test_rehydrate_preserves_order_status_fill_price_for_ka10077_disambiguation(monkeypatch) -> None:
    class _FakeDayPnlReader:
        @classmethod
        def from_env(cls):
            return cls()

        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "018880"
            return {
                "rows": [
                    {
                        "symbol": "018880",
                        "filled_qty": 275,
                        "filled_price": 5435,
                        "buy_price": 5400,
                        "realized_pnl": -10620,
                        "pnl_ratio": -0.0071,
                        "fee": 10000,
                        "tax": 620,
                    },
                    {
                        "symbol": "018880",
                        "filled_qty": 275,
                        "filled_price": 5435,
                        "buy_price": 5410,
                        "realized_pnl": -3746,
                        "pnl_ratio": -0.0025,
                        "fee": 10000,
                        "tax": 621,
                    },
                    {
                        "symbol": "018880",
                        "filled_qty": 100,
                        "filled_price": 5380,
                        "buy_price": 5410,
                        "realized_pnl": -4200,
                        "pnl_ratio": -0.0078,
                        "fee": 900,
                        "tax": 300,
                    },
                ],
                "source": "kiwoom.ka10077",
            }

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    monkeypatch.setattr("libs.read.kiwoom_day_pnl_reader.KiwoomDayPnlReader", _FakeDayPnlReader)

    out = rehydrate_lifecycle_bundle_execution_truth(
        {
            "day": "2026-05-06",
            "trade_id": "TRD_20260506_018880_10",
            "symbol": "018880",
            "trade_lifecycle_status": "closed",
            "entry": {
                "action": "BUY",
                "symbol": "018880",
                "ts": "2026-05-06T04:28:32+00:00",
                "execution_details": {
                    "filled_qty": 275,
                    "filled_price": 5410,
                    "broker_truth_source": "kiwoom.order_status",
                },
            },
            "exit": {
                "action": "SELL",
                "symbol": "018880",
                "ts": "2026-05-06T04:30:17+00:00",
                "execution_details": {
                    "filled_qty": 275,
                    "filled_price": 5435,
                    "broker_truth_source": "kiwoom.order_status",
                },
            },
        }
    )

    details = out["exit_execution_details"]
    assert details["broker_day_authoritative"] is True
    assert details["broker_day_match_mode"] == "symbol_buy_sell_qty_exact"
    assert details["broker_realized_pnl"] == -3746.0
    assert details["broker_fee"] == 10000
    assert details["broker_tax"] == 621
