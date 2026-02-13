from __future__ import annotations

from typing import Dict, Any

from libs.news.news_pipeline import collect_news_items, score_news_sentiment_simple


def test_m18_6_collect_news_items_uses_state_mock():
    state: Dict[str, Any] = {
        "mock_news_items": {
            "AAA": [{"title": "AAA good news"}],
            "BBB": [{"title": "BBB bad news"}],
        }
    }
    items = collect_news_items(["AAA", "BBB", "CCC"], state=state, policy={"news_provider": "naver"})
    assert set(items.keys()) == {"AAA", "BBB", "CCC"}
    assert len(items["AAA"]) == 1
    assert len(items["BBB"]) == 1
    assert len(items["CCC"]) == 0


def test_m18_6_score_news_sentiment_simple_uses_mock_scores_and_defaults():
    state: Dict[str, Any] = {"mock_news_sentiment": {"AAA": 0.7, "BBB": -0.2}}
    items_by_symbol = {"AAA": [], "BBB": [], "CCC": []}
    scores = score_news_sentiment_simple(items_by_symbol, state=state, policy={})
    assert scores["AAA"] == 0.7
    assert scores["BBB"] == -0.2
    assert scores["CCC"] == 0.0
