from libs.execution.order_client import OrderClient
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings


def test_order_dry_run_blocked(monkeypatch):
    monkeypatch.setenv("RISK_MAX_POSITIONS", "1")
    monkeypatch.setenv("RISK_DAILY_LOSS_LIMIT", "0.02")
    s = Settings.from_env(env_path="__missing__.env")

    c = OrderClient(settings=s)
    prepared = PreparedRequest(
        api_id="ORDER",
        method="POST",
        path="/orders",
        headers={},
        query={},
        body={"x": 1},
    )
    dry = c.dry_run_order(
        prepared,
        intent="buy",
        risk_context={"open_positions": 1},
        dry_run_token=True,
    )
    assert dry.allowed is False


def test_order_dry_run_allowed(monkeypatch):
    monkeypatch.setenv("RISK_MAX_POSITIONS", "1")
    monkeypatch.setenv("RISK_DAILY_LOSS_LIMIT", "0.02")
    s = Settings.from_env(env_path="__missing__.env")

    c = OrderClient(settings=s)
    prepared = PreparedRequest(
        api_id="ORDER",
        method="POST",
        path="/orders",
        headers={},
        query={"a": "1"},
        body={"x": 1},
    )
    dry = c.dry_run_order(
        prepared,
        intent="buy",
        risk_context={"open_positions": 0, "daily_pnl_ratio": -0.001, "per_trade_risk_ratio": 0.001},
        dry_run_token=True,
    )
    assert dry.allowed is True
    assert dry.headers.get("Authorization", "").startswith("Bearer")
