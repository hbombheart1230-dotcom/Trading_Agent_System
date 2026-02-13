from __future__ import annotations

import os
from libs.market.global_sentiment import compute_global_sentiment


def test_m18_9_global_sentiment_uses_mock_when_present(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    s = compute_global_sentiment(state={"mock_global_sentiment": -0.8}, policy={})
    assert s == -0.8


def test_m18_9_global_sentiment_neutral_in_dry_run_when_no_mock(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    s = compute_global_sentiment(state={}, policy={})
    assert s == 0.0
