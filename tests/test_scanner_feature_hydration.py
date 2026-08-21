from __future__ import annotations

import sys
from types import SimpleNamespace

from libs.runtime.scanner_feature_hydration import (
    _resolve_yf_ticker,
    hydrate_scanner_feature_map,
)


def test_yfinance_ticker_strips_quote_prefix() -> None:
    assert _resolve_yf_ticker("$477850") == "477850.KS"


def test_yfinance_ticker_uses_kosdaq_for_foreign_listing_code() -> None:
    assert _resolve_yf_ticker("950260") == "950260.KQ"


def test_hydrate_scanner_feature_map_refreshes_existing_symbol_with_live_quote():
    state = {
        "feature_engine": {
            "by_symbol": {
                "AAA": {
                    "engine_trend_strength": 0.2,
                    "engine_vwap_distance": 0.0,
                }
            }
        },
        "ohlcv_by_symbol": {
            "AAA": [
                {"ts": 100, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
                {"ts": 200, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1100.0},
            ]
        },
        "market_context": {"market_breadth": 0.1, "index_trend": 0.2, "realized_vol": 0.03},
        "now_epoch": 300,
    }

    out, source, errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "AAA"}],
        skill_quotes={"AAA": {"symbol": "AAA", "price": 95.0, "volume": 1200.0}},
        policy={
            "scanner_feature_min_rows": 2,
            "scanner_feature_series_max_rows": 10,
            "scanner_feature_seed_with_yf": False,
        },
        refresh_existing=True,
    )

    assert errors == []
    assert source == "state.ohlcv_by_symbol"
    assert "AAA" in out
    rows = state["ohlcv_by_symbol"]["AAA"]
    assert rows[-1]["close"] == 95.0
    assert rows[-1]["volume"] == 1200.0
    assert state["feature_engine"]["source"] == "scanner_candidate_hydration"


def test_hydration_coalesces_repeated_live_updates_into_one_daily_row():
    day_start = 1_782_259_200
    state = {
        "ohlcv_by_symbol": {
            "005930": [
                {
                    "ts": day_start - 86_400,
                    "open": 300000.0,
                    "high": 305000.0,
                    "low": 295000.0,
                    "close": 302000.0,
                    "volume": 50_000_000.0,
                }
            ]
        },
        "now_epoch": day_start + 300,
    }
    policy = {
        "scanner_feature_min_rows": 1,
        "scanner_feature_series_max_rows": 10,
        "scanner_feature_seed_with_yf": False,
    }

    hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "005930"}],
        skill_quotes={"005930": {"symbol": "005930", "price": 320000.0, "volume": 2_000_000.0}},
        policy=policy,
        refresh_existing=True,
    )
    state["now_epoch"] = day_start + 360
    hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "005930"}],
        skill_quotes={"005930": {"symbol": "005930", "price": 324000.0, "volume": 2_500_000.0}},
        policy=policy,
        refresh_existing=True,
    )

    rows = state["ohlcv_by_symbol"]["005930"]
    assert len(rows) == 2
    assert rows[-1]["open"] == 320000.0
    assert rows[-1]["close"] == 324000.0
    assert rows[-1]["volume"] == 2_500_000.0


def test_hydration_uses_raw_kiwoom_cumulative_volume():
    state = {
        "ohlcv_by_symbol": {
            "000660": [
                {
                    "ts": 1_782_172_800,
                    "open": 2500000.0,
                    "high": 2550000.0,
                    "low": 2450000.0,
                    "close": 2520000.0,
                    "volume": 800_000.0,
                }
            ]
        },
        "now_epoch": 1_782_259_500,
    }

    hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "000660"}],
        skill_quotes={
            "000660": {
                "symbol": "000660",
                "price": 2636000.0,
                "raw": {"cntr_infr": [{"acc_trde_qty": "576711"}]},
            }
        },
        policy={
            "scanner_feature_min_rows": 1,
            "scanner_feature_series_max_rows": 10,
            "scanner_feature_seed_with_yf": False,
        },
        refresh_existing=True,
    )

    assert state["ohlcv_by_symbol"]["000660"][-1]["volume"] == 576711.0


def test_hydrate_scanner_feature_map_keeps_existing_fast_path_without_refresh():
    state = {
        "feature_engine": {
            "by_symbol": {
                "AAA": {
                    "engine_trend_strength": 0.2,
                    "engine_vwap_distance": 0.0,
                }
            }
        },
        "ohlcv_by_symbol": {
            "AAA": [
                {"ts": 100, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
            ]
        },
    }

    out, source, errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "AAA"}],
        skill_quotes={"AAA": {"symbol": "AAA", "price": 95.0}},
        policy={
            "scanner_feature_min_rows": 2,
            "scanner_feature_series_max_rows": 10,
            "scanner_feature_seed_with_yf": False,
        },
    )

    assert errors == []
    assert source == "state.feature_engine.by_symbol"
    assert out["AAA"]["engine_trend_strength"] == 0.2
    rows = state["ohlcv_by_symbol"]["AAA"]
    assert rows[-1]["close"] == 100.0


def test_hydrate_scanner_feature_map_fills_symbols_missing_from_partial_direct_cache():
    state = {
        "scanner_features": {
            "AAA": {
                "engine_trend_strength": 0.2,
                "engine_vwap_distance": 0.0,
            }
        },
        "ohlcv_by_symbol": {
            "BBB": [
                {"ts": 100, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
                {"ts": 200, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1100.0},
            ]
        },
        "now_epoch": 300,
    }

    out, source, errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "AAA"}, {"symbol": "BBB"}],
        skill_quotes={"BBB": {"symbol": "BBB", "price": 102.0, "volume": 1200.0}},
        policy={
            "scanner_feature_min_rows": 2,
            "scanner_feature_series_max_rows": 10,
            "scanner_feature_seed_with_yf": False,
        },
    )

    assert errors == []
    assert source == "scanner_candidate_hydration"
    assert out["AAA"]["engine_trend_strength"] == 0.2
    assert "BBB" in out
    assert state["feature_engine"]["by_symbol"]["AAA"]["engine_trend_strength"] == 0.2


def test_hydrate_scanner_feature_map_caches_yfinance_empty_seed(monkeypatch):
    calls = {"count": 0}

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, *, period, interval):
            calls["count"] += 1
            return SimpleNamespace(empty=True)

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=FakeTicker))

    state = {
        "now_epoch": 1_777_256_000,
        "ohlcv_by_symbol": {},
        "market_context": {},
    }
    policy = {
        "scanner_feature_min_rows": 40,
        "scanner_feature_series_max_rows": 60,
        "scanner_feature_seed_with_yf": True,
        "scanner_feature_seed_negative_cache_sec": 3600,
    }

    hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "209640"}],
        skill_quotes={"209640": {"symbol": "209640", "price": 1000.0}},
        policy=policy,
        refresh_existing=True,
    )
    assert calls["count"] == 1
    assert state["_scanner_feature_seed_negative_cache"]["209640"]["source"] == "yfinance_empty"

    state["now_epoch"] += 60
    _, _, errors = hydrate_scanner_feature_map(
        state=state,
        candidates=[{"symbol": "209640"}],
        skill_quotes={"209640": {"symbol": "209640", "price": 1000.0}},
        policy=policy,
        refresh_existing=True,
    )

    assert calls["count"] == 1
    assert "seed:209640:yfinance_empty_cached" in errors
