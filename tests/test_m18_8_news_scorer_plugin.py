from __future__ import annotations

from libs.news.news_pipeline import score_news_sentiment
from libs.news.providers.base import NewsItem


def test_m18_8_simple_scorer_produces_nonzero_scores_from_items():
    state = {}
    policy = {"news_scorer": "simple"}
    items = [
        NewsItem(
            title="AAA earnings beats estimate and stock surge",
            url="u1",
            source="x",
            published_at="t",
            symbol="AAA",
            summary="record high profit guidance",
        ),
        NewsItem(
            title="BBB earnings miss and shares plunge",
            url="u2",
            source="x",
            published_at="t",
            symbol="BBB",
            summary="loss risk downgrade",
        ),
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


def test_m18_8_simple_scorer_handles_html_and_korean_keywords():
    state = {}
    policy = {"news_scorer": "simple"}
    items = [
        NewsItem(
            title="<b>삼성</b> 실적 개선 기대에 급등",
            url="u1",
            source="x",
            published_at="t",
            symbol="AAA",
            summary="호재",
        ),
    ]
    scores = score_news_sentiment(state=state, policy=policy, items=items, symbols=["AAA"])
    assert scores["AAA"] > 0.0
