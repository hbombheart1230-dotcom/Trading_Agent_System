import time
from libs.core.settings import Settings
from libs.risk.supervisor import Supervisor


def make_settings(monkeypatch):
    monkeypatch.setenv("RISK_DAILY_LOSS_LIMIT", "0.02")
    monkeypatch.setenv("RISK_PER_TRADE_LOSS_LIMIT", "0.005")
    monkeypatch.setenv("RISK_MAX_POSITIONS", "1")
    monkeypatch.setenv("RISK_ORDER_COOLDOWN_SEC", "60")
    return Settings.from_env(env_path="__missing__.env")


def test_daily_loss_blocks(monkeypatch):
    s = make_settings(monkeypatch)
    sup = Supervisor(s)
    res = sup.allow("buy", {"daily_pnl_ratio": -0.03})
    assert res.allow is False
    assert "Daily loss" in res.reason


def test_max_positions_blocks(monkeypatch):
    s = make_settings(monkeypatch)
    sup = Supervisor(s)
    res = sup.allow("buy", {"open_positions": 1})
    assert res.allow is False
    assert "Max positions" in res.reason


def test_cooldown_blocks(monkeypatch):
    s = make_settings(monkeypatch)
    sup = Supervisor(s)
    now = int(time.time())
    res = sup.allow("buy", {"last_order_epoch": now - 10, "now_epoch": now})
    assert res.allow is False
    assert "cooldown" in res.reason.lower()


def test_allow_ok(monkeypatch):
    s = make_settings(monkeypatch)
    sup = Supervisor(s)
    res = sup.allow("buy", {"daily_pnl_ratio": -0.001, "open_positions": 0, "per_trade_risk_ratio": 0.001})
    assert res.allow is True
