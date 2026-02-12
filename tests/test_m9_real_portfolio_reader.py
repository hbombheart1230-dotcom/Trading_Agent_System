from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader
from libs.read.snapshot_models import PortfolioSnapshot


class StubAccount:
    def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
        class R:
            status_code = 200
            payload = {
                "cash": "10000000",
                "positions": [
                    {"symbol": "005930", "qty": "10", "avg_price": "70000", "unrealized_pnl": "+12000"},
                ],
            }
            raw_text = ""
        return R()


def test_kiwoom_portfolio_reader_extracts():
    r = KiwoomPortfolioReader(account=StubAccount())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert isinstance(snap, PortfolioSnapshot)
    assert snap.cash == 10000000.0
    assert snap.positions[0].symbol == "005930"
    assert snap.positions[0].qty == 10
    assert snap.positions[0].avg_price == 70000.0
