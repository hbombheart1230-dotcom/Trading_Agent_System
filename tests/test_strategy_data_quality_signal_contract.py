from __future__ import annotations

from libs.market.global_sentiment import compute_global_sentiment_signal
from libs.news.news_pipeline import score_news_sentiment_signal


def test_global_sentiment_signal_reports_unavailable_on_fetch_failure(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr("libs.market.global_sentiment._fetch_inputs", lambda _policy: None)

    signal = compute_global_sentiment_signal(state={}, policy={})
    assert signal["status"] == "unavailable"
    assert signal["source"] == "yfinance"
    assert signal["reason"] == "fetch_failed"
    assert float(signal["score"]) == 0.0


def test_news_sentiment_signal_reports_mock_and_missing_symbol_fallback():
    signal_map = score_news_sentiment_signal(
        {"AAA": [], "BBB": []},
        state={"mock_news_sentiment": {"AAA": 0.7}},
        policy={},
    )
    assert signal_map["AAA"]["status"] == "ok"
    assert abs(float(signal_map["AAA"]["score"]) - 0.7) < 1e-12
    assert signal_map["BBB"]["status"] == "fallback"
    assert signal_map["BBB"]["reason"] == "mock_missing_symbol_default"


def test_news_sentiment_signal_reports_unavailable_on_scorer_exception(monkeypatch):
    class _BoomScorer:
        def score(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("libs.news.news_pipeline.get_scorer", lambda _name: _BoomScorer())

    signal_map = score_news_sentiment_signal(
        {"AAA": []},
        state={},
        policy={"news_scorer": "simple"},
    )
    assert signal_map["AAA"]["status"] == "unavailable"
    assert signal_map["AAA"]["source"] == "scorer:simple"
    assert str(signal_map["AAA"]["reason"]).startswith("scorer_error:")
