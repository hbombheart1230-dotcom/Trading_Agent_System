from graphs.nodes.build_market_snapshot import build_market_snapshot
from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
from libs.read.price_reader import MockPriceReader
from libs.read.portfolio_reader import MockPortfolioReader


def test_build_market_snapshot_with_mock_prices():
    state = {
        "symbol": "005930",
        "price_reader": MockPriceReader(prices={"005930": 71200}),
    }
    out = build_market_snapshot(state)
    assert out["market_snapshot"]["symbol"] == "005930"
    assert out["market_snapshot"]["price"] == 71200


def test_build_portfolio_snapshot_with_mock_portfolio():
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=10000000,
            positions=[{"symbol": "005930", "qty": 10, "avg_price": 70000, "unrealized_pnl": 12000}],
        )
    }
    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert ps["cash"] == 10000000
    assert ps["positions"][0]["symbol"] == "005930"
    assert ps["positions"][0]["qty"] == 10


def test_build_market_snapshot_falls_back_when_mock_reader_returns_non_positive(monkeypatch):
    class ZeroPriceReader:
        def get_market_snapshot(self, symbol):  # type: ignore[no-untyped-def]
            from libs.read.snapshot_models import MarketSnapshot

            return MarketSnapshot(symbol=symbol, price=0.0, ts=0)

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("MOCK_PRICE_FALLBACK", "71234")
    state = {"symbol": "005930", "price_reader": ZeroPriceReader()}

    out = build_market_snapshot(state)
    assert out["market_snapshot"]["price"] == 71234.0


def test_build_portfolio_snapshot_falls_back_when_mock_reader_returns_zero_cash(monkeypatch):
    class ZeroCashReader:
        def get_portfolio_snapshot(self):  # type: ignore[no-untyped-def]
            from libs.read.snapshot_models import PortfolioSnapshot

            return PortfolioSnapshot(cash=0.0, positions=[])

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("MOCK_CASH_FALLBACK", "2500000")
    state = {"portfolio_reader": ZeroCashReader()}

    out = build_portfolio_snapshot(state)
    assert out["portfolio_snapshot"]["cash"] == 2500000.0
