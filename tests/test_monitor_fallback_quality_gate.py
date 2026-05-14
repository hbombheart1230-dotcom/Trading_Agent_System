from graphs.nodes.monitor_node import _classify_vwap_reclaim_pullback_candidate


def test_rank4_theme_unconfirmed_fallback_without_liquidity_edge_is_blocked():
    out = _classify_vwap_reclaim_pullback_candidate(
        candidate_row={
            "symbol": "005930",
            "rank": 4,
            "theme_match": False,
            "score_breakdown": {
                "momentum": 0.22,
                "trend": 0.16,
                "theme_boost": 0.0,
                "trading_value": 0.0,
                "volume_surge": 0.0,
            },
            "source_scores": {"strategist_backfill": 0.2},
        },
        selected_rank=4,
        fallback_used=True,
        entry_info={
            "metrics": {"volume_ratio": 0.6},
            "condition_scores": {"entry_quality_score": 0.70},
        },
    )

    assert out["subtype"] == "weak_fallback_pullback"
    assert out["fallback_qualified"] is False
    assert out["fallback_rejection_reason"] == "theme_unconfirmed_fallback_without_liquidity_edge"


def test_rank4_fallback_with_theme_match_is_allowed():
    out = _classify_vwap_reclaim_pullback_candidate(
        candidate_row={
            "symbol": "123456",
            "rank": 5,
            "theme_match": True,
            "score_breakdown": {"theme_boost": 0.06, "trading_value": 0.0},
        },
        selected_rank=5,
        fallback_used=True,
        entry_info={"metrics": {"volume_ratio": 0.5}},
    )

    assert out["subtype"] == "theme_confirmed_pullback"
    assert out["fallback_qualified"] is True


def test_rank4_fallback_with_trading_value_edge_is_allowed():
    out = _classify_vwap_reclaim_pullback_candidate(
        candidate_row={
            "symbol": "123456",
            "rank": 4,
            "theme_match": False,
            "score_breakdown": {"theme_boost": 0.0, "trading_value": 0.24},
        },
        selected_rank=4,
        fallback_used=True,
        entry_info={"metrics": {"volume_ratio": 0.5}},
    )

    assert out["subtype"] in {"liquidity_confirmed_pullback", "market_representative_pullback"}
    assert out["fallback_qualified"] is True


def test_rank4_fallback_with_volume_and_chart_fit_is_allowed_without_theme():
    out = _classify_vwap_reclaim_pullback_candidate(
        candidate_row={
            "symbol": "123456",
            "rank": 6,
            "theme_match": False,
            "score_breakdown": {"theme_boost": 0.0, "trading_value": 0.0},
        },
        selected_rank=6,
        fallback_used=True,
        entry_info={
            "metrics": {"volume_ratio": 1.2, "volume_ok": True},
            "condition_scores": {"entry_quality_score": 0.80},
        },
    )

    assert out["subtype"] in {"vwap_reclaim_setup", "liquidity_confirmed_pullback"}
    assert out["fallback_qualified"] is True


def test_rank1_theme_unconfirmed_candidate_is_classified_but_not_blocked():
    out = _classify_vwap_reclaim_pullback_candidate(
        candidate_row={
            "symbol": "123456",
            "rank": 1,
            "theme_match": False,
            "score_breakdown": {"theme_boost": 0.0, "trading_value": 0.0},
        },
        selected_rank=1,
        fallback_used=False,
        entry_info={},
    )

    assert out["subtype"] == "vwap_reclaim_setup"
    assert out["fallback_qualified"] is True
