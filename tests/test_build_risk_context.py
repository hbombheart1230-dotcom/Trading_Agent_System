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
