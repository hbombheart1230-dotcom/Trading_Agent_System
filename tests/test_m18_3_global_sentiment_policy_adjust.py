from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_m18_3_global_sentiment_adjusts_policy_risk_off():
    state = {
        "mock_global_sentiment": -1.0,
        "universe": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        "policy": {"max_risk": 0.7, "min_confidence": 0.6, "candidate_k": 5},
    }
    out = strategist_node(state)
    # risk-off => max_risk decreases, min_confidence increases
    assert out["policy"]["max_risk"] < 0.7
    assert out["policy"]["min_confidence"] > 0.6
    assert "global_sentiment" in out["policy"]


def test_m18_3_global_sentiment_adjusts_policy_risk_on():
    state = {
        "mock_global_sentiment": 1.0,
        "universe": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        "policy": {"max_risk": 0.7, "min_confidence": 0.6, "candidate_k": 5},
    }
    out = strategist_node(state)
    # risk-on => max_risk increases, min_confidence decreases
    assert out["policy"]["max_risk"] > 0.7
    assert out["policy"]["min_confidence"] < 0.6
