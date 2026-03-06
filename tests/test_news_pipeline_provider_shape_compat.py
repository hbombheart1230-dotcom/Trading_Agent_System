from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node
from libs.news.news_pipeline import collect_news_items, score_news_sentiment
from libs.news.providers.base import NewsItem as ProviderNewsItem


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

    out = collect_news_items(["AAA", "BBB"], state={}, policy={"news_provider": "naver"})
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

    out = collect_news_items(["AAA", "BBB", "CCC"], state={}, policy={"news_provider": "naver"})
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
