\
from typing import Any, Dict
from graphs.nodes.strategist_node import strategist_node


def test_m18_5_risk_off_reduces_candidate_count():
    state: Dict[str, Any] = {
        "policy": {
            "candidate_source": "top_picks",
            "candidate_topk": 5,
            "candidate_max_count_risk_off": 3,
            "candidate_risk_off_threshold": -0.5,
        },
        "mock_rank_symbols": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        "mock_condition_symbols": [],
        "mock_global_sentiment": -0.9,
    }
    out = strategist_node(state)
    assert len(out["candidates"]) == 3
