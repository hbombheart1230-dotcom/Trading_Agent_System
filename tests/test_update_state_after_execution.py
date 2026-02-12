import time
from graphs.nodes.update_state_after_execution import update_state_after_execution


def test_update_state_does_not_touch_last_order_on_blocked():
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": False, "blocked": True, "reason": "cooldown"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 10
    assert out["persisted_state"]["last_execution_ok"] is False


def test_update_state_updates_last_order_on_ok_real(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": True, "dry_run": False, "reason": "sent"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 1234
    assert out["persisted_state"]["last_execution_ok"] is True


def test_update_state_does_not_update_last_order_on_ok_dry_run(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": True, "dry_run": True, "reason": "dry-run"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 10
