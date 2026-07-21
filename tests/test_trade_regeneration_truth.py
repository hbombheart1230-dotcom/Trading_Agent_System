from __future__ import annotations

from libs.reporting.trade_regeneration_truth import (
    merge_post_exit_shadow_recap,
    rehydrate_lifecycle_bundle_execution_truth,
)


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


def test_rehydrate_refreshes_kiwoom_day_truth_for_mock_execution(monkeypatch) -> None:
    class _FakeDayPnlReader:
        @classmethod
        def from_env(cls):
            return cls()

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

        def get_account_profit_rate_rows(self):
            return {"rows": [], "source": "kiwoom.ka10085"}

    monkeypatch.setattr("libs.read.kiwoom_day_pnl_reader.KiwoomDayPnlReader", _FakeDayPnlReader)

    out = rehydrate_lifecycle_bundle_execution_truth(
        {
            "day": "2026-05-14",
            "trade_id": "TRD_20260514_005930_02",
            "symbol": "005930",
            "trade_lifecycle_status": "closed",
            "entry": {
                "action": "BUY",
                "symbol": "005930",
                "ts": "2026-05-14T00:16:59+00:00",
                "execution_details": {
                    "filled_qty": 10,
                    "filled_price": 291975,
                    "broker_env": "mock",
                    "execution_mode": "mock_broker_http",
                },
            },
            "exit": {
                "action": "SELL",
                "symbol": "005930",
                "ts": "2026-05-14T00:29:39+00:00",
                "execution_details": {
                    "filled_qty": 10,
                    "filled_price": 295500,
                    "broker_env": "mock",
                    "execution_mode": "mock_broker_http",
                    "broker_realized_pnl": 8791.0,
                    "broker_realized_pnl_pct": 0.003,
                    "broker_fee": 20550,
                    "broker_tax": 5909,
                    "pnl_truth_source": "kiwoom.ka10077",
                    "broker_day_truth_source": "kiwoom.ka10077",
                    "broker_day_authoritative": True,
                },
            },
        }
    )

    details = out["exit_execution_details"]
    assert details["broker_env"] == "mock"
    assert details.get("broker_realized_pnl") == -14306.0
    assert details.get("broker_realized_pnl_pct") == -0.0049
    assert details.get("broker_fee") == 20550
    assert details.get("broker_tax") == 5909
    assert details.get("pnl_truth_source") == "kiwoom.ka10077"
    assert details.get("broker_day_truth_source") == "kiwoom.ka10077"
    assert details["broker_day_authoritative"] is True


def test_rehydrate_preserves_authoritative_order_pair_truth(monkeypatch) -> None:
    class _UnexpectedDayPnlReader:
        @classmethod
        def from_env(cls):
            raise AssertionError("order-pair truth must not be replaced by symbol-day aggregate truth")

    monkeypatch.setattr("libs.read.kiwoom_day_pnl_reader.KiwoomDayPnlReader", _UnexpectedDayPnlReader)

    order_pair = {
        "filled_qty": 1000,
        "filled_price": 2701.0,
        "broker_realized_pnl": -38274.0,
        "broker_realized_pnl_pct": -0.014097237569060773,
        "broker_fee": 24274,
        "broker_tax": 0,
        "broker_buy_price": 2715.0,
        "broker_day_truth_source": "kiwoom.order_pair_snapshot",
        "broker_day_match_mode": "entry_order_id_next_same_symbol_qty_sell",
        "pnl_truth_source": "kiwoom.order_pair_snapshot",
        "broker_day_authoritative": True,
    }
    out = rehydrate_lifecycle_bundle_execution_truth(
        {
            "day": "2026-07-16",
            "trade_id": "TRD_20260716_001790_04",
            "symbol": "001790",
            "trade_lifecycle_status": "closed",
            "entry": {
                "action": "BUY",
                "symbol": "001790",
                "execution_details": {"filled_qty": 1000, "filled_price": 2715.0},
            },
            "exit": {
                "action": "SELL",
                "symbol": "001790",
                "execution_details": dict(order_pair),
            },
        }
    )

    assert out["exit_execution_details"] == order_pair
    assert out["execution_details"] == order_pair


def test_merge_post_exit_shadow_recap_preserves_observed_closeout_data() -> None:
    pending = {
        "symbol": "001790",
        "price_observation_status": "pending",
        "checkpoints": {"+5m": {"status": "pending"}, "EOD": {"status": "pending"}},
    }
    observed = {
        "symbol": "001790",
        "price_observation_status": "observed",
        "checkpoints": {
            "+5m": {"status": "observed", "price": 2755.0},
            "EOD": {"status": "observed", "price": 2730.0},
        },
    }

    out = merge_post_exit_shadow_recap(
        {"post_exit_shadow": pending, "fact_payload": {"trade": {"symbol": "001790"}}},
        {"post_exit_shadow": observed},
    )

    assert out["post_exit_shadow"] == observed
    assert out["fact_payload"]["post_exit_shadow"] == observed
    assert out["fact_payload"]["trade"]["post_exit_shadow"] == observed
