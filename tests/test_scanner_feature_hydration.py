from __future__ import annotations

from libs.runtime.scanner_feature_hydration import hydrate_scanner_feature_map


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
        skill_quotes={"AAA": {"symbol": "AAA", "price": 95.0}},
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
    assert state["feature_engine"]["source"] == "scanner_candidate_hydration"


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
