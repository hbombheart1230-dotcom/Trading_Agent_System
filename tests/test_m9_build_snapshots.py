from graphs.nodes.build_snapshots import build_snapshots
from libs.read.price_reader import MockPriceReader
from libs.read.portfolio_reader import MockPortfolioReader


def test_build_snapshots_aggregates():
    state = {
        "symbol": "005930",
        "price_reader": MockPriceReader(prices={"005930": 71200}),
        "portfolio_reader": MockPortfolioReader(
            cash=10000000,
            positions=[{"symbol": "005930", "qty": 10, "avg_price": 70000, "unrealized_pnl": 12000}],
        ),
    }
    out = build_snapshots(state)
    assert out["snapshots"]["market"]["price"] == 71200
    assert out["snapshots"]["portfolio"]["cash"] == 10000000
    assert out["snapshots"]["portfolio"]["positions"][0]["qty"] == 10
