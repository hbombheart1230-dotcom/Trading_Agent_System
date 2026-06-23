from pathlib import Path
from libs.storage.state_store import StateStore


def test_state_store_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    store = StateStore(str(p))

    s0 = store.load()
    assert s0["last_order_epoch"] == 0
    assert s0["mock_cash"] == 0.0

    s1 = {"last_order_epoch": 123, "open_positions": 1, "daily_pnl_ratio": 0.01}
    store.save(s1)

    s2 = store.load()
    assert s2["last_order_epoch"] == 123
    assert s2["open_positions"] == 1
    assert abs(s2["daily_pnl_ratio"] - 0.01) < 1e-9
    assert s2["mock_realized_pnl"] == 0.0


def test_state_store_does_not_overwrite_newer_broker_truth_with_stale_positions(tmp_path: Path):
    p = tmp_path / "state.json"
    store = StateStore(str(p))
    store.save(
        {
            "mock_positions": [],
            "open_positions": 0,
            "broker_truth_position_reconciliation": {
                "authoritative": True,
                "generated_at": "2026-06-17T07:03:27+00:00",
                "position_count": 0,
                "symbols": [],
            },
        }
    )

    store.save(
        {
            "mock_positions": [{"symbol": "005930", "qty": 8}],
            "open_positions": 1,
            "broker_truth_position_reconciliation": {
                "authoritative": True,
                "generated_at": "2026-06-17T06:26:04+00:00",
                "position_count": 1,
                "symbols": ["005930"],
            },
        }
    )

    state = store.load()
    assert state["open_positions"] == 0
    assert state["mock_positions"] == []
    assert state["broker_truth_position_reconciliation"]["generated_at"] == "2026-06-17T07:03:27+00:00"
