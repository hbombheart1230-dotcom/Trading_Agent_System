from __future__ import annotations

from graphs.nodes.scanner_node import scanner_node
from libs.strategies.candidates.kiwoom_candidate_provider import (
    build_kiwoom_candidate_rows,
    get_top_volume_stocks,
)


def test_get_top_volume_stocks_uses_env_injection(monkeypatch):
    monkeypatch.setenv("MOCK_TOP_VOLUME_SYMBOLS", "111111,222222,333333")
    rows = get_top_volume_stocks({}, topk=2)
    assert rows == ["111111", "222222"]


def test_build_kiwoom_candidate_rows_aggregates_multi_source_scores():
    state = {
        "mock_top_value_symbols": ["AAA", "BBB", "CCC"],
        "mock_top_volume_symbols": ["BBB", "AAA", "DDD"],
        "mock_top_change_symbols": ["DDD", "AAA"],
        "mock_condition_symbols": ["CCC", "AAA", "EEE"],
    }

    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=5,
        condition_limit=10,
        include_change_rate=True,
    )

    assert meta["candidate_source"] == "kiwoom_market_data"
    assert meta["pool_count"] == 5
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["source_count"] >= 3
    assert "top_value" in rows[0]["sources"]
    assert "condition_search" in rows[0]["sources"]
    assert rows[0]["rank_score"] <= 1.0


def test_scanner_node_uses_kiwoom_candidates_and_theme_filter():
    state = {
        "themes": ["semiconductor"],
        "theme_map": {
            "semiconductor": ["005930"],
        },
        "mock_top_value_symbols": ["005930", "000660"],
        "mock_top_volume_symbols": ["000660", "005930"],
        "mock_top_change_symbols": ["000660"],
        "mock_condition_symbols": ["005930", "000660"],
        "mock_scan_results": {
            "005930": {"score": 0.8, "risk_score": 0.2, "confidence": 0.9},
            "000660": {"score": 0.9, "risk_score": 0.2, "confidence": 0.9},
        },
    }

    out = scanner_node(state)
    rows = out.get("scan_results") or []
    assert [r["symbol"] for r in rows] == ["005930"]
    assert out["top_stock"] == "005930"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert bool(scanner_output.get("theme_filter_applied")) is True


def test_scanner_node_falls_back_to_strategist_candidates_when_kiwoom_pool_empty():
    state = {
        "candidate_source": "kiwoom",
        "strategist_output": {"candidates": ["123456"]},
        "mock_scan_results": {
            "123456": {"score": 0.5, "risk_score": 0.1, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    assert out.get("top_stock") == "123456"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("candidate_source") == "strategist_fallback"
