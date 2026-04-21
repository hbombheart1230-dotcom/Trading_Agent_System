from graphs.nodes.build_risk_context import build_risk_context


def test_build_risk_context_basic():
    state = {
        "snapshots": {
            "portfolio": {
                "cash": 10000000,
                "positions": [
                    {"symbol": "005930", "qty": 10, "unrealized_pnl": 12000},
                    {"symbol": "000660", "qty": 0, "unrealized_pnl": 0},
                ],
            }
        },
        "persisted_state": {"last_order_epoch": 100},
    }

    out = build_risk_context(state)
    rc = out["risk_context"]

    assert rc["open_positions"] == 1
    assert abs(rc["daily_pnl_ratio"] - 0.0012) < 1e-6
    assert rc["last_order_epoch"] == 100


def test_build_risk_context_prefers_broker_cash_truth_for_sizing():
    class FakeCashReader:
        def get_deposit_snapshot(self):  # type: ignore[no-untyped-def]
            return {
                "deposit": 8000000,
                "withdrawable_cash": 7600000,
                "orderable_amount": 7500000,
                "source": "kiwoom.kt00001",
            }

    state = {
        "snapshots": {
            "portfolio": {
                "cash": 10000000,
                "positions": [
                    {"symbol": "005930", "qty": 10, "unrealized_pnl": 12000},
                ],
            }
        },
        "persisted_state": {"last_order_epoch": 100},
        "kiwoom_orderable_cash_reader": FakeCashReader(),
    }

    out = build_risk_context(state)
    rc = out["risk_context"]

    assert rc["broker_deposit"] == 8000000.0
    assert rc["broker_withdrawable_cash"] == 7600000.0
    assert rc["broker_orderable_amount"] == 7500000.0
    assert rc["capital_available_for_sizing"] == 7500000.0
    assert rc["cash_truth_source"] == "kiwoom.kt00001"
    assert rc["cash_truth_available"] is True
    assert rc["daily_pnl_ratio_denominator_source"] == "broker_deposit"
    assert abs(rc["daily_pnl_ratio"] - 0.0015) < 1e-6
