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
    assert ps["open_positions"] == 1


def test_build_portfolio_snapshot_preserves_position_current_price():
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=10000000,
            positions=[
                {
                    "symbol": "005930",
                    "qty": 10,
                    "avg_price": 70000,
                    "unrealized_pnl": 12000,
                    "current_price": 71200,
                }
            ],
        )
    }
    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert ps["positions"][0]["current_price"] == 71200.0


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


def test_build_market_snapshot_reuses_last_valid_price_on_reader_error(monkeypatch):
    class BrokenReader:
        def get_market_snapshot(self, symbol):  # type: ignore[no-untyped-def]
            raise RuntimeError("price_api_error")

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("MOCK_PRICE_FALLBACK", "71234")
    state = {
        "symbol": "005930",
        "price_reader": BrokenReader(),
        "market_snapshot": {"symbol": "005930", "price": 73500.0, "ts": 1},
    }

    out = build_market_snapshot(state)
    assert out["market_snapshot"]["price"] == 73500.0
    assert out["market_snapshot_health"]["fallback_source"] == "last_valid_market_price"
    assert out["market_snapshot_health"]["reader_ok"] is False


def test_build_market_snapshot_reuses_persisted_last_market_price(monkeypatch):
    class ZeroPriceReader:
        def get_market_snapshot(self, symbol):  # type: ignore[no-untyped-def]
            from libs.read.snapshot_models import MarketSnapshot

            return MarketSnapshot(symbol=symbol, price=0.0, ts=0)

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("MOCK_PRICE_FALLBACK", "71234")
    state = {
        "symbol": "005930",
        "price_reader": ZeroPriceReader(),
        "persisted_state": {"last_market_price": 73100.0},
    }

    out = build_market_snapshot(state)
    assert out["market_snapshot"]["price"] == 73100.0
    assert out["market_snapshot_health"]["fallback_source"] == "last_valid_market_price"


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


def test_build_portfolio_snapshot_uses_persisted_mock_positions_when_reader_empty(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(cash=2000000, positions=[]),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ]
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert ps["positions"][0]["symbol"] == "005930"
    assert ps["positions"][0]["qty"] == 3
    assert ps["open_positions"] == 1


def test_build_portfolio_snapshot_uses_reader_positions_as_authoritative_in_mock_real_mode(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = {
        "portfolio_reader": MockPortfolioReader(cash=1500000, positions=[]),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ],
            "mock_cash": 1234567.0,
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    health = ps.get("_health", {})
    persisted = out["persisted_state"]

    assert ps["positions"] == []
    assert ps["open_positions"] == 0
    assert ps["cash"] == 1500000
    assert health.get("reader_positions_authoritative") is True
    assert health.get("positions_source") == "reader_positions_authoritative_empty"
    assert health.get("positions_mismatch_detected") is True
    assert health.get("reconciliation_applied") is True
    assert health.get("reconciliation_status") == "reconciled_to_reader"
    assert health.get("cash_source") == "reader_cash_authoritative"
    assert persisted.get("mock_positions") == []
    assert persisted.get("open_positions") == 0
    assert persisted.get("mock_position_desync_reconciled") is True
    assert persisted.get("portfolio_reconcile_reason") == "reader_positions_authoritative"


def test_build_portfolio_snapshot_syncs_reader_current_price_into_persisted_positions_in_mock_real_mode(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=1500000,
            positions=[
                {
                    "symbol": "005930",
                    "qty": 3,
                    "avg_price": 70000.0,
                    "unrealized_pnl": 3600.0,
                    "current_price": 71200.0,
                }
            ],
        ),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ],
            "mock_cash": 1234567.0,
        },
    }

    out = build_portfolio_snapshot(state)
    persisted = out["persisted_state"]

    assert persisted["mock_positions"][0]["symbol"] == "005930"
    assert persisted["mock_positions"][0]["current_price"] == 71200.0


def test_build_portfolio_snapshot_merges_reader_current_price_into_persisted_positions_in_pure_mock_mode(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=2000000,
            positions=[
                {
                    "symbol": "005930",
                    "qty": 3,
                    "avg_price": 70000.0,
                    "unrealized_pnl": 3600.0,
                    "current_price": 71200.0,
                }
            ],
        ),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ],
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    persisted = out["persisted_state"]

    assert ps["positions"][0]["current_price"] == 71200.0
    assert persisted["mock_positions"][0]["current_price"] == 71200.0


def test_build_portfolio_snapshot_drops_invalid_persisted_mock_symbols(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(cash=2000000, positions=[]),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "0082N0", "qty": 1, "avg_price": 0.0, "unrealized_pnl": 0.0},
                {"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ],
            "last_trade_symbol": "A0082N0",
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    persisted = out["persisted_state"]
    assert [row["symbol"] for row in ps["positions"]] == ["005930"]
    assert [row["symbol"] for row in persisted["mock_positions"]] == ["005930"]
    assert persisted.get("last_trade_symbol") in ("", None)


def test_build_portfolio_snapshot_normalizes_reader_position_codes(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=2000000,
            positions=[
                {"symbol": "A005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0},
                {"symbol": "A0082N0", "qty": 1, "avg_price": 63200.0, "unrealized_pnl": 0.0},
            ],
        ),
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert [row["symbol"] for row in ps["positions"]] == ["005930"]
    assert ps["open_positions"] == 1


def test_build_portfolio_snapshot_prefers_reader_positions_over_persisted_when_available(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(
            cash=2000000,
            positions=[
                {"symbol": "051910", "qty": 2, "avg_price": 300000.0, "unrealized_pnl": 0.0},
            ],
        ),
        "persisted_state": {
            "mock_positions": [
                {"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ]
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert ps["positions"][0]["symbol"] == "051910"
    assert ps["positions"][0]["qty"] == 2
    assert ps["open_positions"] == 1
    assert ps.get("_health", {}).get("positions_source") == "reader_positions"


def test_build_portfolio_snapshot_uses_persisted_mock_cash_when_available(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(cash=2000000, positions=[]),
        "persisted_state": {
            "mock_cash": 1234567.0,
            "mock_realized_pnl": 321.0,
            "mock_positions": [],
        },
    }

    out = build_portfolio_snapshot(state)
    ps = out["portfolio_snapshot"]
    assert ps["cash"] == 1234567.0
    assert ps["realized_pnl"] == 321.0


def test_build_portfolio_snapshot_includes_health_metadata(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "portfolio_reader": MockPortfolioReader(cash=2000000, positions=[]),
        "persisted_state": {"mock_positions": []},
    }

    out = build_portfolio_snapshot(state)
    health = out["portfolio_snapshot"].get("_health")
    assert isinstance(health, dict)
    assert health.get("reader_ok") is True
    assert isinstance(out.get("portfolio_snapshot_health"), dict)


def test_build_portfolio_snapshot_marks_reader_error_health_in_mock_mode(monkeypatch):
    class BrokenReader:
        def get_portfolio_snapshot(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("account_api_500")

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {"portfolio_reader": BrokenReader(), "persisted_state": {"mock_positions": []}}

    out = build_portfolio_snapshot(state)
    health = out["portfolio_snapshot"].get("_health")
    assert isinstance(health, dict)
    assert health.get("reader_ok") is False
    assert "account_api_500" in str(health.get("reader_error") or "")
