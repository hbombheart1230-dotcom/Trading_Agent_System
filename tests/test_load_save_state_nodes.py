from graphs.nodes.load_state import load_state
from graphs.nodes.save_state import save_state
from libs.core.settings import Settings


def test_load_and_save_state(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "state.json"))

    state = {}
    out = load_state(state)
    assert "persisted_state" in out

    out["persisted_state"]["last_order_epoch"] = 999
    save_state(out)

    out2 = load_state({})
    assert out2["persisted_state"]["last_order_epoch"] == 999
