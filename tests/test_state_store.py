from pathlib import Path
from libs.storage.state_store import StateStore


def test_state_store_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    store = StateStore(str(p))

    s0 = store.load()
    assert s0["last_order_epoch"] == 0

    s1 = {"last_order_epoch": 123, "open_positions": 1, "daily_pnl_ratio": 0.01}
    store.save(s1)

    s2 = store.load()
    assert s2["last_order_epoch"] == 123
    assert s2["open_positions"] == 1
    assert abs(s2["daily_pnl_ratio"] - 0.01) < 1e-9
