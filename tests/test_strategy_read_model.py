from libs.reporting.strategy_read_model import build_news_symbol_linkage_view


def test_build_news_symbol_linkage_view_connects_targets_hints_and_selected_symbol() -> None:
    out = build_news_symbol_linkage_view(
        strategist_summary={
            "news_query_targets": ["반도체", "코스피", "AI"],
            "candidate_symbols_hint": ["005930", "000660"],
            "candidate_hypotheses": [
                {"symbol": "005930", "hypothesis": "semiconductor leader with strong memory demand"},
                {"symbol": "000660", "hypothesis": "AI server beta candidate"},
            ],
            "news_evidence_ranked": {
                "market_news_ranked": [{"title": "반도체 업종 강세"}],
                "candidate_news_ranked": [
                    {"symbol": "005930", "title": "삼성전자 HBM 기대감 확대"},
                    {"symbol": "000660", "title": "하이닉스 수급 개선"},
                ],
            },
        },
        selected_symbol="005930",
        top_ranked_symbols=["005930", "000660"],
    )

    assert out["selected_symbol"] == "005930"
    assert out["runner_up_symbol"] == "000660"
    assert out["selected_symbol_in_candidate_hints"] is True
    assert out["runner_up_symbol_in_candidate_hints"] is True
    assert out["linkage_strength"] == "strong"
    assert out["market_headlines"] == ["반도체 업종 강세"]
    assert out["selected_symbol_headlines"] == ["삼성전자 HBM 기대감 확대"]
    assert out["runner_up_symbol_headlines"] == ["하이닉스 수급 개선"]
    assert out["selected_vs_runner_up"]["runner_up_symbol"] == "000660"
    assert "Selected 005930 vs runner-up 000660" in out["selected_vs_runner_up"]["comparison_summary"]
    assert out["linked_candidates"][0]["symbol"] == "005930"
    assert "headline_link" in out["linked_candidates"][0]["linkage_flags"]
    assert "candidate_hint" in out["linked_candidates"][0]["linkage_flags"]
