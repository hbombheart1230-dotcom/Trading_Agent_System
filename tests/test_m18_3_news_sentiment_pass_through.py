from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_m18_3_news_sentiment_is_attached_for_candidates():
    state = {
        "universe": ["AAA", "BBB", "CCC"],
        "mock_news_sentiment": {"AAA": 0.7, "BBB": -0.2},
        "policy": {"candidate_k": 3, "use_news_analysis": True, "use_global_sentiment": False},
    }
    out = strategist_node(state)
    assert "news_sentiment" in out
    assert out["news_sentiment"]["AAA"] == 0.7
    assert out["news_sentiment"]["BBB"] == -0.2
    # missing defaults to 0.0
    assert out["news_sentiment"]["CCC"] == 0.0
