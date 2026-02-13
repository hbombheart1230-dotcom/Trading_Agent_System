from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_m18_top_picks_intersects_rank_with_condition_when_present():
    state = {
        "policy": {
            "candidate_source": "top_picks",
            "candidate_rank_mode": "value",
            "candidate_rank_topn": 10,
            "candidate_topk": 5,
        },
        # rank order matters
        "mock_rank_symbols": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        # condition filters out BBB and DDD only
        "mock_condition_symbols": ["DDD", "BBB"],
    }

    out = strategist_node(state)
    syms = [x["symbol"] for x in out["candidates"]]
    # should preserve rank order but only include intersection
    assert syms == ["BBB", "DDD"]


def test_m18_top_picks_uses_rank_only_when_condition_empty():
    state = {
        "policy": {
            "candidate_source": "top_picks",
            "candidate_rank_mode": "value",
            "candidate_rank_topn": 10,
            "candidate_topk": 3,
        },
        "mock_rank_symbols": ["AAA", "BBB", "CCC", "DDD"],
        "mock_condition_symbols": [],
    }
    out = strategist_node(state)
    syms = [x["symbol"] for x in out["candidates"]]
    assert syms == ["AAA", "BBB", "CCC"]
