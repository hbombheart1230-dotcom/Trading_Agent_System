from __future__ import annotations

from libs.news.news_pipeline import score_news_sentiment
from libs.news.providers.base import NewsItem


def test_m18_8_simple_scorer_produces_nonzero_scores_from_items():
    state = {}
    policy = {"news_scorer": "simple"}
    items = [
        NewsItem(title="AAA 실적 서프라이즈 급등", url="u1", source="x", published_at="t", symbol="AAA", summary="호재"),
        NewsItem(title="BBB 실적 부진 급락", url="u2", source="x", published_at="t", symbol="BBB", summary="악재"),
    ]
    scores = score_news_sentiment(state=state, policy=policy, items=items, symbols=["AAA", "BBB", "CCC"])
    assert scores["AAA"] > 0.0
    assert scores["BBB"] < 0.0
    assert scores["CCC"] == 0.0


def test_m18_8_mock_news_sentiment_bypasses_scorer():
    state = {"mock_news_sentiment": {"AAA": 0.7}}
    policy = {"news_scorer": "llm"}
    items = []
    scores = score_news_sentiment(state=state, policy=policy, items=items, symbols=["AAA", "BBB"])
    assert scores["AAA"] == 0.7
    assert scores["BBB"] == 0.0
