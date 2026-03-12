from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node
from libs.strategies.universe_builder import build_candidate_universe


def test_universe_builder_merges_multi_sources_and_ranks_topk():
    state = {
        "portfolio_snapshot": {"positions": [{"symbol": "005930", "qty": 16}]},
        "watchlist_symbols": ["000660"],
        "theme_symbols": ["068270"],
        "mock_rank_symbols": ["035420", "000660", "051910"],
        "mock_condition_symbols": ["035420", "005930"],
        "mock_liquidity_symbols": ["051910", "035420"],
    }
    policy = {
        "candidate_rank_topn": 10,
        "universe_require_condition": False,
    }

    out = build_candidate_universe(state=state, policy=policy, topk=5)

    assert len(out) == 5
    assert out[0]["symbol"] == "005930"  # held + condition => highest precedence
    assert any("held_position" in row["sources"] for row in out if row["symbol"] == "005930")
    assert any("market_rank" in row["sources"] for row in out if row["symbol"] == "035420")
    assert all(isinstance(row.get("source_scores"), dict) for row in out)
    assert all(int(row.get("source_count") or 0) == len(list(row.get("sources") or [])) for row in out)
    assert all(isinstance(row.get("why"), str) and row["why"] for row in out)


def test_strategist_uses_universe_builder_without_breaking_candidate_contract(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    state = {
        "portfolio_snapshot": {"positions": [{"symbol": "AAA", "qty": 1}]},
        "watchlist_symbols": ["EEE"],
        "mock_rank_symbols": ["BBB", "CCC", "DDD"],
        "policy": {
            "candidate_k": 3,
            "candidate_topk": 3,
            "use_universe_builder": True,
            "use_global_sentiment": False,
            "use_news_analysis": False,
        },
    }

    out = strategist_node(state)
    cands = out.get("candidates") or []
    assert len(cands) == 3
    assert cands[0]["symbol"] == "AAA"
    assert isinstance(out.get("universe_candidates"), list)
    assert out["universe_candidates"][0]["symbol"] == "AAA"
    assert all("symbol" in c and "why" in c for c in cands)
    assert isinstance(cands[0].get("source_scores"), dict)
    assert int(cands[0].get("source_count") or 0) >= 1


def test_universe_builder_supports_sector_filter_and_source_weights():
    state = {
        "sector_filter": ["semiconductor"],
        "sector_map": {
            "semiconductor": ["AAA", "BBB"],
            "bio": ["CCC"],
        },
        "mock_condition_symbols": ["AAA"],
        "mock_rank_symbols": ["BBB", "DDD"],
    }
    policy = {
        "candidate_source": "market_rank",
        "candidate_rank_topn": 10,
        "candidate_source_weights": {
            "sector": 5.0,
            "condition": 2.0,
            "market_rank": 1.0,
        },
    }

    out = build_candidate_universe(state=state, policy=policy, topk=4)
    rows = {str(r.get("symbol")): r for r in out}
    assert "AAA" in rows
    assert "BBB" in rows
    assert "CCC" not in rows  # excluded by sector_filter
    assert "sector" in rows["AAA"]["sources"]
    assert float(rows["AAA"]["source_scores"]["sector"]) == 5.0


def test_universe_builder_backfills_when_watchlist_is_smaller_than_topk(monkeypatch):
    monkeypatch.setenv("FALLBACK_CANDIDATE_SYMBOLS", "444444,555555,666666,777777,888888,999999")
    state = {
        "watchlist_symbols": ["111111", "222222", "333333"],
    }
    policy = {
        "universe_require_condition": False,
    }

    out = build_candidate_universe(state=state, policy=policy, topk=8)
    symbols = [str(r.get("symbol") or "") for r in out]
    assert len(out) == 8
    assert symbols[:3] == ["111111", "222222", "333333"]
    assert any("fallback" in list(r.get("sources") or []) for r in out[3:])
