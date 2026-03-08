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

