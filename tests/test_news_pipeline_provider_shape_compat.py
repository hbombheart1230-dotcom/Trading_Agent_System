from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node
from libs.news.news_pipeline import _fetch_yfinance_news_items, _resolve_yf_ticker, collect_news_items, score_news_sentiment
from libs.news.providers.base import NewsItem as ProviderNewsItem


def test_news_yfinance_ticker_uses_kosdaq_for_foreign_listing_code() -> None:
    assert _resolve_yf_ticker("950260", {}) == "950260.KQ"


def test_collect_news_items_accepts_mapping_provider_shape(monkeypatch):
    class DictProvider:
        def fetch(self, symbols, *, state=None, policy=None):
            return {
                str(s): [
                    ProviderNewsItem(
                        title=f"{s} headline",
                        symbol=str(s),
                        source="provider",
                    )
                ]
                for s in symbols
            }

    monkeypatch.setattr("libs.news.news_pipeline.get_provider", lambda _name: DictProvider())

    out = collect_news_items(
        ["AAA", "BBB"],
        state={},
        policy={"news_provider": "naver", "news_yf_fallback_enabled": False},
    )
    assert set(out.keys()) == {"AAA", "BBB"}
    assert len(out["AAA"]) == 1
    assert out["AAA"][0].symbol == "AAA"
    assert out["AAA"][0].title == "AAA headline"


def test_collect_news_items_accepts_flat_provider_shape(monkeypatch):
    class FlatProvider:
        def fetch(self, symbols, *, state=None, policy=None):
            return [
                ProviderNewsItem(title="A1", symbol="AAA"),
                {"title": "B1", "symbol": "BBB", "source": "provider"},
            ]

    monkeypatch.setattr("libs.news.news_pipeline.get_provider", lambda _name: FlatProvider())

    out = collect_news_items(
        ["AAA", "BBB", "CCC"],
        state={},
        policy={"news_provider": "naver", "news_yf_fallback_enabled": False},
    )
    assert len(out["AAA"]) == 1
    assert len(out["BBB"]) == 1
    assert len(out["CCC"]) == 0


def test_score_news_sentiment_normalizes_provider_newsitem_shape():
    items_by_symbol = {
        "AAA": [ProviderNewsItem(title="neutral", symbol="AAA")],
        "BBB": [],
    }
    scores = score_news_sentiment(items_by_symbol, state={}, policy={"news_scorer": "simple"})
    assert set(scores.keys()) == {"AAA", "BBB"}
    assert isinstance(scores["AAA"], float)
    assert isinstance(scores["BBB"], float)


def test_strategist_node_news_analysis_path_does_not_raise_with_mock_items():
    state = {
        "universe": ["AAA", "BBB"],
        "mock_news_items": {
            "AAA": [{"title": "AAA headline", "summary": "neutral"}],
            "BBB": [{"title": "BBB headline", "summary": "neutral"}],
        },
        "policy": {
            "candidate_k": 2,
            "use_news_analysis": True,
            "use_global_sentiment": False,
        },
    }
    out = strategist_node(state)
    assert "news_sentiment" in out
    assert set(out["news_sentiment"].keys()) == {"AAA", "BBB"}


def test_collect_news_items_uses_yfinance_fallback_when_provider_empty(monkeypatch):
    class EmptyProvider:
        def fetch(self, symbols, *, state=None, policy=None):
            return {str(s): [] for s in symbols}

    monkeypatch.setattr("libs.news.news_pipeline.get_provider", lambda _name: EmptyProvider())
    monkeypatch.setattr(
        "libs.news.news_pipeline._fetch_yfinance_news_items",
        lambda sym, _policy: [ProviderNewsItem(title=f"{sym} yf", symbol=str(sym), source="yfinance")],
    )

    out = collect_news_items(
        ["AAA", "BBB"],
        state={},
        policy={"news_provider": "naver", "news_yf_fallback_enabled": True},
    )
    assert len(out["AAA"]) == 1
    assert out["AAA"][0].source == "yfinance"
    assert len(out["BBB"]) == 1
    assert out["BBB"][0].title == "BBB yf"


def test_collect_news_items_skips_yfinance_fallback_when_disabled(monkeypatch):
    class EmptyProvider:
        def fetch(self, symbols, *, state=None, policy=None):
            return {str(s): [] for s in symbols}

    monkeypatch.setattr("libs.news.news_pipeline.get_provider", lambda _name: EmptyProvider())
    monkeypatch.setattr(
        "libs.news.news_pipeline._fetch_yfinance_news_items",
        lambda sym, _policy: [ProviderNewsItem(title=f"{sym} yf", symbol=str(sym), source="yfinance")],
    )

    out = collect_news_items(
        ["AAA"],
        state={},
        policy={"news_provider": "naver", "news_yf_fallback_enabled": False},
    )
    assert out["AAA"] == []


def test_fetch_yfinance_news_items_parses_nested_content_shape(monkeypatch):
    import sys

    class _FakeTicker:
        def __init__(self, _ticker):
            self._ticker = _ticker

        @property
        def news(self):
            return [
                {
                    "id": "abc",
                    "content": {
                        "title": "Nested title",
                        "summary": "Nested summary",
                        "pubDate": "2026-03-12T03:37:07Z",
                        "provider": {"displayName": "Reuters"},
                        "canonicalUrl": {"url": "https://example.com/news"},
                    },
                }
            ]

    class _FakeYF:
        @staticmethod
        def Ticker(ticker):
            return _FakeTicker(ticker)

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)
    items = _fetch_yfinance_news_items("005930", policy={})
    assert len(items) == 1
    assert items[0].title == "Nested title"
    assert items[0].source == "Reuters"
    assert items[0].url == "https://example.com/news"
