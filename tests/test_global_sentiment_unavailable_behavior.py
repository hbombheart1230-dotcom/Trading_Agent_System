from __future__ import annotations

import math

from libs.market.global_sentiment import compute_global_sentiment, compute_global_sentiment_signal


def test_compute_global_sentiment_returns_nan_when_source_unavailable(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: None)
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: None)
    value = compute_global_sentiment(state={}, policy={})
    assert math.isnan(float(value))


def test_global_sentiment_signal_includes_timestamp_alias(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    sig = compute_global_sentiment_signal(state={}, policy={})
    assert "ts" in sig
    assert "timestamp" in sig
    assert int(sig["timestamp"]) == int(sig["ts"])


def test_global_sentiment_signal_exposes_index_move_breakdown(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class _Inputs:
        sp500_ret = 0.011
        nasdaq_ret = 0.018
        dow_ret = 0.007
        vix_ret = 0.12
        vix_level = 27.5
        dxy_ret = -0.002
        tnx_delta = -0.03

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _Inputs())
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: None)
    sig = compute_global_sentiment_signal(state={}, policy={})

    assert sig["status"] == "ok"
    assert abs(float((sig.get("components") or {}).get("sp500_ret") or 0.0) - 0.011) < 1e-12
    assert abs(float((sig.get("components") or {}).get("nasdaq_ret") or 0.0) - 0.018) < 1e-12
    assert abs(float((sig.get("components") or {}).get("dow_ret") or 0.0) - 0.007) < 1e-12
    assert abs(float((sig.get("components") or {}).get("vix_ret") or 0.0) - 0.12) < 1e-12
    assert abs(float((sig.get("components") or {}).get("vix_level") or 0.0) - 27.5) < 1e-12
    assert abs(float((sig.get("index_moves") or {}).get("sp500_pct") or 0.0) - 1.1) < 1e-9
    assert abs(float((sig.get("index_moves") or {}).get("nasdaq_pct") or 0.0) - 1.8) < 1e-9
    assert abs(float((sig.get("index_moves") or {}).get("dow_pct") or 0.0) - 0.7) < 1e-9
    assert abs(float((sig.get("macro_moves") or {}).get("vix_pct") or 0.0) - 12.0) < 1e-9
    assert abs(float((sig.get("macro_moves") or {}).get("vix_level") or 0.0) - 27.5) < 1e-9
    fear = sig.get("fear_index") or {}
    assert fear.get("ticker") == "^VIX"
    assert abs(float(fear.get("level") or 0.0) - 27.5) < 1e-9
    assert float(fear.get("level_pressure") or 0.0) > 0.0


def test_global_sentiment_vix_pressure_makes_signal_more_defensive(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class _LowFear:
        sp500_ret = 0.01
        nasdaq_ret = 0.01
        dow_ret = 0.01
        vix_ret = -0.02
        vix_level = 15.0
        dxy_ret = 0.0
        tnx_delta = 0.0

    class _HighFear:
        sp500_ret = 0.01
        nasdaq_ret = 0.01
        dow_ret = 0.01
        vix_ret = 0.20
        vix_level = 32.0
        dxy_ret = 0.0
        tnx_delta = 0.0

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _LowFear())
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: None)
    low_fear = compute_global_sentiment_signal(state={}, policy={})
    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _HighFear())
    high_fear = compute_global_sentiment_signal(state={}, policy={})

    assert high_fear["status"] == "ok"
    assert low_fear["status"] == "ok"
    assert float(high_fear.get("score") or 0.0) < float(low_fear.get("score") or 0.0)


def test_global_sentiment_signal_exposes_korea_index_context(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class _Inputs:
        sp500_ret = 0.0
        nasdaq_ret = 0.0
        dow_ret = 0.0
        vix_ret = 0.0
        vix_level = 18.0
        dxy_ret = 0.0
        tnx_delta = 0.0

    korea_packet = {
        "status": "ok",
        "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {"current": 3100.12, "previous_close": 3080.0, "change_pct": 0.65, "rising": 450, "falling": 320, "unchanged": 60},
            "KOSDAQ": {"current": 850.55, "previous_close": 842.0, "change_pct": 1.02, "rising": 690, "falling": 410, "unchanged": 80},
        },
    }

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _Inputs())
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: korea_packet)

    sig = compute_global_sentiment_signal(state={}, policy={})

    assert sig["status"] == "ok"
    assert sig["source"] == "yfinance+kiwoom.ka20009"
    assert abs(float((sig.get("index_moves") or {}).get("kospi_pct") or 0.0) - 0.65) < 1e-9
    assert abs(float((sig.get("index_moves") or {}).get("kosdaq_pct") or 0.0) - 1.02) < 1e-9
    assert (sig.get("korea_indices") or {}).get("indices", {}).get("KOSPI", {}).get("previous_close") == 3080.0


def test_global_sentiment_signal_logs_korea_index_sanity(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class _Inputs:
        sp500_ret = 0.0
        nasdaq_ret = 0.0
        dow_ret = 0.0
        vix_ret = 0.0
        vix_level = 18.0
        dxy_ret = 0.0
        tnx_delta = 0.0

    korea_packet = {
        "status": "ok",
        "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {
                "current": 6795.82,
                "previous_close": 7475.94,
                "change_pct": -9.1,
                "open": 7412.03,
                "high": 7529.07,
                "low": 6789.62,
            },
        },
    }

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _Inputs())
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: korea_packet)

    sig = compute_global_sentiment_signal(state={}, policy={})
    sanity = sig.get("korea_index_sanity") or {}

    assert sanity["status"] == "warning"
    assert sanity["extreme_move_requires_confirmation"] is True


def test_global_sentiment_signal_exposes_extended_macro_indicator_slots(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")

    class _Inputs:
        sp500_ret = 0.01
        nasdaq_ret = 0.02
        dow_ret = 0.005
        vix_ret = -0.03
        vix_level = 16.0
        dxy_ret = 0.002
        tnx_delta = 0.01

    korea_packet = {
        "status": "ok",
        "source": "kiwoom.ka20009",
        "indices": {
            "KOSPI": {"current": 3100.0, "previous_close": 3090.0, "change_pct": 0.32},
            "KOSDAQ": {"current": 850.0, "previous_close": 845.0, "change_pct": 0.59},
        },
    }

    def _fake_pair(ticker):
        values = {
            "^IRX": (50.0, 50.4),
            "^TNX": (45.0, 45.2),
            "DX-Y.NYB": (100.0, 100.5),
            "KRW=X": (1370.0, 1380.0),
            "EURUSD=X": (1.08, 1.09),
            "CNY=X": (7.20, 7.22),
            "JPY=X": (156.0, 157.0),
            "^GSPC": (5000.0, 5050.0),
            "^IXIC": (16000.0, 16200.0),
        }
        return values.get(ticker)

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _Inputs())
    monkeypatch.setattr("libs.market.global_sentiment._fetch_korea_index_inputs", lambda _state, _policy: korea_packet)
    monkeypatch.setattr("libs.market.global_sentiment._fetch_last2_closes_yfinance", _fake_pair)

    sig = compute_global_sentiment_signal(
        state={
            "macro_indicator_overrides": {
                "kr_3y_yield": {
                    "source": "test_override",
                    "current_yield_pct": 2.91,
                    "delta": -0.01,
                    "asof": "2026-05-28",
                }
            }
        },
        policy={"korea_bond_yield_provider_enabled": False},
    )
    indicators = (sig.get("macro_indicators") or {}).get("indicators") or {}

    for key in (
        "kr_3y_yield",
        "kr_10y_yield",
        "us_2y_yield",
        "us_10y_yield",
        "usdkrw",
        "dxy",
        "eurusd",
        "usdcny",
        "usdjpy",
        "kospi",
        "sp500",
        "nasdaq",
    ):
        assert key in indicators

    assert indicators["kr_3y_yield"]["status"] == "ok"
    assert indicators["kr_3y_yield"]["source"] == "test_override"
    assert indicators["kr_10y_yield"]["status"] == "unavailable"
    assert indicators["usdkrw"]["status"] == "ok"
    assert abs(float(indicators["usdkrw"]["change_pct"]) - 0.729927) < 1e-4
    assert indicators["us_2y_yield"]["source_note"].startswith("default_yfinance_proxy")
