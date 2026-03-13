from __future__ import annotations

import math

from libs.market.global_sentiment import compute_global_sentiment, compute_global_sentiment_signal


def test_compute_global_sentiment_returns_nan_when_source_unavailable(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: None)
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
        dxy_ret = -0.002
        tnx_delta = -0.03

    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: _Inputs())
    sig = compute_global_sentiment_signal(state={}, policy={})

    assert sig["status"] == "ok"
    assert abs(float((sig.get("components") or {}).get("sp500_ret") or 0.0) - 0.011) < 1e-12
    assert abs(float((sig.get("components") or {}).get("nasdaq_ret") or 0.0) - 0.018) < 1e-12
    assert abs(float((sig.get("components") or {}).get("dow_ret") or 0.0) - 0.007) < 1e-12
    assert abs(float((sig.get("index_moves") or {}).get("sp500_pct") or 0.0) - 1.1) < 1e-9
    assert abs(float((sig.get("index_moves") or {}).get("nasdaq_pct") or 0.0) - 1.8) < 1e-9
    assert abs(float((sig.get("index_moves") or {}).get("dow_pct") or 0.0) - 0.7) < 1e-9
