from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from libs.strategies.candidates.kiwoom_candidate_provider import (
    get_condition_candidates,
    get_sector_candidates,
    get_top_gainers,
    get_top_trading_value_stocks,
    get_top_volume_stocks,
    get_watchlist_candidates,
)


def test_candidate_retrieval_normalization_and_dedup():
    state = {
        "mock_top_value_symbols": ["005930", "005930", "000660"],
        "mock_top_volume_symbols": ["000660", "005930", "000660"],
        "mock_top_change_symbols": ["035420", "035420", "005930"],
        "mock_condition_symbols": ["005930", "035420", "005930"],
        "themes": ["semiconductor"],
        "theme_map": {"semiconductor": ["005930", "000660", "005930"]},
        "watchlist_symbols": ["005930", "068270"],
    }

    assert get_top_trading_value_stocks(state, topk=5) == ["005930", "000660"]
    assert get_top_volume_stocks(state, topk=5) == ["000660", "005930"]
    assert get_top_gainers(state, topk=5) == ["035420", "005930"]
    assert get_condition_candidates(state, limit=5) == ["005930", "035420"]
    sector_rows = get_sector_candidates(state, themes=["semiconductor"], limit=10)
    assert set(sector_rows) == {"005930", "000660"}
    assert get_watchlist_candidates(state, limit=10) == ["005930", "068270"]


def test_scanner_candidate_pool_reduction_by_liquidity_filters():
    state = {
        "mock_top_value_symbols": ["AAA", "BBB"],
        "mock_top_volume_symbols": ["AAA", "BBB"],
        "mock_top_change_symbols": ["AAA", "BBB"],
        "mock_condition_symbols": ["AAA", "BBB"],
        "skill_data": {
            "market.quote": {
                "data": [
                    {"symbol": "AAA", "price": 100, "volume": 1_000_000, "value": 5_000_000_000},
                    {"symbol": "BBB", "price": 100, "volume": 100, "value": 10_000},
                ]
            }
        },
        "mock_scan_results": {
            "AAA": {"score": 0.1, "risk_score": 0.2, "confidence": 0.8},
            "BBB": {"score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        },
        "policy": {
            "min_trading_value": 1_000_000,
            "min_volume": 1_000,
        },
    }

    out = scanner_node(state)
    pool = out.get("scanner_candidate_pool") or {}
    assert int(pool.get("candidate_pool_before_filter") or 0) >= 2
    assert int(pool.get("candidate_pool_after_filter") or 0) == 1
    assert out.get("top_stock") == "AAA"


def test_scanner_practical_score_breakdown_and_top_stock():
    state = {
        "mock_top_value_symbols": ["AAA", "BBB"],
        "mock_top_volume_symbols": ["AAA", "BBB"],
        "mock_top_change_symbols": ["AAA", "BBB"],
        "mock_condition_symbols": ["AAA", "BBB"],
        "mock_scan_results": {
            "AAA": {"score": 0.0, "risk_score": 0.2, "confidence": 0.7},
            "BBB": {"score": 0.0, "risk_score": 0.2, "confidence": 0.7},
        },
        "scanner_features": {
            "AAA": {
                "return20": 0.08,
                "ma20_gap": 0.03,
                "trend_strength": 0.8,
                "volume_spike20": 2.2,
                "volatility20": 0.02,
                "gap_pct": 0.01,
                "signal_score": 0.7,
                "regime": "trend",
            },
            "BBB": {
                "return20": -0.02,
                "ma20_gap": -0.01,
                "trend_strength": -0.2,
                "volume_spike20": 0.9,
                "volatility20": 0.06,
                "gap_pct": 0.07,
                "signal_score": -0.2,
                "regime": "high_volatility",
            },
        },
        "skill_data": {
            "market.quote": {
                "data": [
                    {"symbol": "AAA", "price": 100, "change_pct": 2.1, "volume": 900_000, "value": 4_000_000_000},
                    {"symbol": "BBB", "price": 100, "change_pct": -0.4, "volume": 350_000, "value": 1_000_000_000},
                ]
            }
        },
    }

    out = scanner_node(state)
    assert out.get("top_stock") == "AAA"
    ranked = out.get("ranked_candidates") or []
    assert len(ranked) >= 2
    assert ranked[0]["symbol"] == "AAA"
    assert ranked[0]["score_total"] >= ranked[1]["score_total"]
    breakdown = ranked[0].get("score_breakdown") or {}
    assert "trading_value" in breakdown
    assert "momentum" in breakdown
    assert "trend" in breakdown
    assert "volume_surge" in breakdown
    assert "risk_penalty" in breakdown


def test_scanner_theme_boost_works_when_theme_filter_disabled():
    state = {
        "themes": ["semiconductor"],
        "theme_map": {"semiconductor": ["AAA"]},
        "mock_top_value_symbols": ["AAA", "BBB"],
        "mock_top_volume_symbols": ["AAA", "BBB"],
        "mock_top_change_symbols": ["AAA", "BBB"],
        "mock_condition_symbols": ["AAA", "BBB"],
        "mock_scan_results": {
            "AAA": {"score": 0.0, "risk_score": 0.2, "confidence": 0.7},
            "BBB": {"score": 0.0, "risk_score": 0.2, "confidence": 0.7},
        },
        "policy": {
            "enable_theme_filter": False,
            "score_weight_theme_boost": 0.50,
            "score_weight_momentum": 0.0,
            "score_weight_trend": 0.0,
            "score_weight_volume_surge": 0.0,
            "score_weight_intraday_strength": 0.0,
            "score_weight_sentiment": 0.0,
            "score_weight_trading_value": 0.0,
        },
    }

    out = scanner_node(state)
    rows = out.get("scan_results") or []
    assert len(rows) == 2
    assert out.get("top_stock") == "AAA"
    assert (out.get("scanner_output") or {}).get("theme_filter_applied") is False


def test_scanner_monitor_boundary_contract_compatibility():
    scanned = scanner_node(
        {
            "mock_top_value_symbols": ["AAA", "BBB"],
            "mock_top_volume_symbols": ["AAA", "BBB"],
            "mock_condition_symbols": ["AAA", "BBB"],
            "mock_scan_results": {
                "AAA": {"score": 0.8, "risk_score": 0.2, "confidence": 0.8},
                "BBB": {"score": 0.3, "risk_score": 0.3, "confidence": 0.7},
            },
        }
    )
    top = str(scanned.get("top_stock") or "")
    assert top == "AAA"

    monitor_state = {
        "plan": {"thesis": "boundary-check"},
        "selected": scanned.get("selected"),
        "policy": {"use_exit_policy": False},
    }
    mout = monitor_node(monitor_state)
    intents = mout.get("intents") or []
    assert len(intents) == 1
    assert intents[0]["symbol"] == top
