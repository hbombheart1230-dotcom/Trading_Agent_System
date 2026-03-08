from __future__ import annotations

from graphs.nodes.scan_candidates import scan_candidates


def test_scan_candidates_uses_universe_builder_multi_source():
    state = {
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 1}]},
        "watchlist_symbols": ["BBB"],
        "mock_rank_symbols": ["CCC", "DDD", "EEE"],
        "mock_condition_symbols": ["AAA", "CCC"],
        "policy": {
            "use_universe_builder": True,
            "candidate_k": 4,
        },
    }
    out = scan_candidates(state)
    assert len(out["candidates"]) == 4
    assert out["candidates"][0] == "AAA"
    assert isinstance(out.get("candidate_rows"), list)
    assert out["candidate_rows"][0]["symbol"] == "AAA"
    assert out["candidate_rows"][0]["why"]


def test_scan_candidates_falls_back_to_env_universe(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SYMBOLS", "005930,000660,035420")
    out = scan_candidates({})
    assert out["candidates"] == ["005930", "000660", "035420"]
    assert all(isinstance(x, str) for x in out["candidates"])

