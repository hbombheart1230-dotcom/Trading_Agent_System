\
from typing import Any, Dict
from graphs.nodes.strategist_node import strategist_node


def test_m18_5_strategist_reranks_candidates_by_news_sentiment():
    state: Dict[str, Any] = {
        "policy": {
            "candidate_source": "top_picks",
            "candidate_topk": 5,
            "candidate_news_weight": 1.0,   # strong
            "candidate_global_weight": 0.0,
        },
        "mock_rank_symbols": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        "mock_condition_symbols": [],
        "mock_news_sentiment": {"EEE": 0.9, "AAA": -0.2},
    }
    out = strategist_node(state)
    assert out["candidates"][0]["symbol"] == "EEE"
