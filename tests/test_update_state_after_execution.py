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


def test_update_state_handles_allowed_schema_real(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {"last_order_epoch": 10},
        "execution": {"allowed": True, "payload": {"mode": "real"}, "reason": "Allowed"},
    }
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_execution_ok"] is True
    assert out["persisted_state"]["last_order_epoch"] == 1234


def test_update_state_handles_allowed_schema_mock_without_order_sent(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {"last_order_epoch": 10},
        "execution": {"allowed": True, "payload": {"mode": "mock"}, "reason": "Allowed"},
    }
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_execution_ok"] is True
    assert out["persisted_state"]["last_order_epoch"] == 10


def test_update_state_mock_buy_updates_mock_positions(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": []},
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 2, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_order_epoch"] == 10
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["symbol"] == "005930"
    assert ps["mock_positions"][0]["qty"] == 2
    assert ps["mock_positions"][0]["avg_price"] == 70000.0
    assert ps["mock_cash"] == 1860000.0
    assert ps["mock_realized_pnl"] == 0.0
    assert ps["last_trade_side"] == "BUY"
    assert ps["last_trade_epoch"] == 1234


def test_update_state_mock_sell_closes_position(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "last_order_epoch": 10,
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "mock_cash": 1860000.0,
            "mock_realized_pnl": 0.0,
        },
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "SELL", "symbol": "005930", "qty": 2, "price": 70200},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["open_positions"] == 0
    assert ps["mock_positions"] == []
    assert ps["mock_cash"] == 2000400.0
    assert ps["mock_realized_pnl"] == 400.0
    assert ps["last_trade_side"] == "SELL"
    assert ps["last_trade_epoch"] == 1234


def test_update_state_real_mode_still_updates_mock_ledger_when_kiwoom_mode_mock(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": [], "mock_cash": 2000000.0},
        "execution": {
            "allowed": True,
            "payload": {"mode": "real"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_order_epoch"] == 1234
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["symbol"] == "005930"
    assert ps["mock_positions"][0]["qty"] == 1


def test_update_state_does_not_apply_fill_when_broker_rejected(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": [], "mock_cash": 2000000.0},
        "execution": {
            "allowed": True,
            "payload": {"mode": "real", "api_ok": True, "broker_code": "20"},
            "reason": "broker_rejected:20",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_execution_ok"] is False
    assert ps["last_order_epoch"] == 10
    assert ps.get("mock_positions") == []
    assert ps.get("mock_cash") == 2000000.0
