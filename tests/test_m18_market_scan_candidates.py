from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_m18_strategist_generates_3_to_5_candidates_without_manual_input(monkeypatch):
    # ensure DRY_RUN forces fallback (no network)
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node({})
    cands = out.get("candidates")
    assert isinstance(cands, list)
    assert 3 <= len(cands) <= 5
    assert all(isinstance(x, dict) and x.get("symbol") for x in cands)


def test_m18_strategist_respects_state_candidate_symbols_injection():
    out = strategist_node({"candidate_symbols": ["111111", "222222", "333333", "444444", "555555", "666666"]})
    cands = out.get("candidates")
    assert [x["symbol"] for x in cands] == ["111111", "222222", "333333", "444444", "555555"]
