from libs.read.kiwoom_portfolio_reader import KiwoomPortfolioReader
from libs.read.snapshot_models import PortfolioSnapshot


class StubAccount:
    def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
        class R:
            status_code = 200
            ok = True
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


def test_kiwoom_portfolio_reader_extracts_day_bal_rt_shape():
    class StubAccountDayBal:
        def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
            class R:
                status_code = 200
                payload = {
                    "dbst_bal": "2500000",
                    "day_bal_rt": [
                        {
                            "stk_cd": "A005930",
                            "rmnd_qty": "2",
                            "buy_uv": "71000",
                            "evltv_prft": "+1200",
                        }
                    ],
                }
                raw_text = ""
                ok = True
            return R()

    r = KiwoomPortfolioReader(account=StubAccountDayBal())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert snap.cash == 2500000.0
    assert snap.positions[0].symbol == "005930"
    assert snap.positions[0].qty == 2
    assert snap.positions[0].avg_price == 71000.0
    assert snap.positions[0].unrealized_pnl == 1200.0


def test_kiwoom_portfolio_reader_extracts_kt00018_shape():
    class StubAccountKt00018:
        def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
            class R:
                status_code = 200
                ok = True
                payload = {
                    "prsm_dpst_aset_amt": "3500000",
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "A051910",
                            "rmnd_qty": "3",
                            "pur_pric": "312000",
                            "evltv_prft": "-2400",
                        }
                    ],
                }
                raw_text = ""
            return R()

    r = KiwoomPortfolioReader(account=StubAccountKt00018())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert snap.cash == 3500000.0
    assert snap.positions[0].symbol == "051910"
    assert snap.positions[0].qty == 3
    assert snap.positions[0].avg_price == 312000.0
    assert snap.positions[0].unrealized_pnl == -2400.0


def test_kiwoom_portfolio_reader_drops_invalid_live_like_symbols():
    class StubAccountInvalidSymbol:
        def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
            class R:
                status_code = 200
                ok = True
                payload = {
                    "cash": "1000000",
                    "positions": [
                        {"stk_cd": "A0082N0", "rmnd_qty": "1", "buy_uv": "63200", "evltv_prft": "0"},
                        {"stk_cd": "A005930", "rmnd_qty": "2", "buy_uv": "70000", "evltv_prft": "0"},
                    ],
                }
                raw_text = ""
            return R()

    r = KiwoomPortfolioReader(account=StubAccountInvalidSymbol())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert snap.cash == 1000000.0
    assert [row.symbol for row in snap.positions] == ["005930"]


def test_kiwoom_portfolio_reader_extracts_current_price_when_available():
    class StubAccountCurrentPrice:
        def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
            class R:
                status_code = 200
                ok = True
                payload = {
                    "cash": "10000000",
                    "positions": [
                        {
                            "symbol": "005930",
                            "qty": "10",
                            "avg_price": "70000",
                            "unrealized_pnl": "+12000",
                            "prpr": "71200",
                        },
                    ],
                }
                raw_text = ""
            return R()

    r = KiwoomPortfolioReader(account=StubAccountCurrentPrice())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert snap.positions[0].current_price == 71200.0


def test_kiwoom_portfolio_reader_extracts_account_pnl_ratio_when_available():
    class StubAccountPnlRatio:
        def get_account_balance(self, *, dry_run: bool = False):  # type: ignore
            class R:
                status_code = 200
                ok = True
                payload = {
                    "cash": "10000000",
                    "positions": [
                        {
                            "symbol": "005930",
                            "qty": "1",
                            "avg_price": "210500",
                            "unrealized_pnl": "-6850",
                            "prpr": "205500",
                            "evlu_pfls_rt": "-3.37",
                        },
                    ],
                }
                raw_text = ""
            return R()

    r = KiwoomPortfolioReader(account=StubAccountPnlRatio())  # type: ignore
    snap = r.get_portfolio_snapshot()
    assert round(float(snap.positions[0].account_pnl_ratio or 0.0), 4) == -0.0337
    assert snap.positions[0].account_pnl_ratio_source == "evlu_pfls_rt"
