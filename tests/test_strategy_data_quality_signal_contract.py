from __future__ import annotations

from libs.market.global_sentiment import compute_global_sentiment_signal
import math

from libs.news.news_pipeline import score_news_sentiment, score_news_sentiment_signal
from libs.news.models import NewsItem


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


def test_news_sentiment_legacy_mode_can_preserve_unavailable_as_nan(monkeypatch):
    class _BoomScorer:
        def score(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr("libs.news.news_pipeline.get_scorer", lambda _name: _BoomScorer())
    out = score_news_sentiment(
        {"AAA": []},
        state={},
        policy={"news_scorer": "simple"},
        preserve_unavailable_nan=True,
    )
    assert math.isnan(float(out["AAA"]))


def test_news_sentiment_signal_applies_freshness_decay(monkeypatch):
    class _ConstScorer:
        def score(self, items_by_symbol, **kwargs):
            return {"AAA": 0.8}

    monkeypatch.setattr("libs.news.news_pipeline.get_scorer", lambda _name: _ConstScorer())
    monkeypatch.setattr("libs.news.news_pipeline.time.time", lambda: 1_800_000_000)

    rows = {
        "AAA": [
            NewsItem(
                title="Old headline",
                url="https://example.com/old",
                source="naver",
                published_at="2026-01-01T00:00:00+00:00",
                symbol="AAA",
                summary="",
            )
        ]
    }
    signal_map = score_news_sentiment_signal(rows, state={}, policy={"news_scorer": "simple"})
    sig = signal_map["AAA"]
    assert sig["status"] == "ok"
    assert float(sig["raw_score"]) == 0.8
    assert float(sig["freshness_weight"]) < 1.0
    assert float(sig["score"]) < 0.8
    assert "freshness_decay" in str(sig["reason"])


def test_news_sentiment_signal_applies_duplicate_headline_decay(monkeypatch):
    class _ConstScorer:
        def score(self, items_by_symbol, **kwargs):
            return {"AAA": 0.9}

    monkeypatch.setattr("libs.news.news_pipeline.get_scorer", lambda _name: _ConstScorer())
    monkeypatch.setattr("libs.news.news_pipeline.time.time", lambda: 1_800_000_000)

    rows = {
        "AAA": [
            NewsItem(title="Same title", url="https://example.com/1", source="naver", published_at="2026-03-16T01:00:00+00:00", symbol="AAA", summary=""),
            NewsItem(title="Same title", url="https://example.com/2", source="naver", published_at="2026-03-16T01:05:00+00:00", symbol="AAA", summary=""),
            NewsItem(title="Same title", url="https://example.com/3", source="naver", published_at="2026-03-16T01:10:00+00:00", symbol="AAA", summary=""),
        ]
    }
    signal_map = score_news_sentiment_signal(rows, state={}, policy={"news_scorer": "simple"})
    sig = signal_map["AAA"]
    assert sig["status"] == "ok"
    assert int(sig["headline_count"]) == 3
    assert int(sig["distinct_headline_count"]) == 1
    assert float(sig["duplicate_weight"]) < 1.0
    assert float(sig["score"]) < 0.9
    assert "duplicate_headline_decay" in str(sig["reason"])
