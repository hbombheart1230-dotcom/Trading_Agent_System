from __future__ import annotations

from typing import Any, Dict


def test_m18_4_news_sentiment_boosts_score_and_affects_selection():
    from graphs.nodes.scanner_node import scanner_node

    state: Dict[str, Any] = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        # Equal base scores; news should make BBB win.
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        "news_sentiment": {"AAA": 0.0, "BBB": 1.0},
        "policy": {
            "weight_news": 0.20,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }

    out = scanner_node(state)
    assert out["selected"]["symbol"] == "BBB"
    # Score must be increased by weight_news * news_sentiment
    assert abs(float(out["selected"]["score"]) - 0.70) < 1e-9


def test_m18_4_global_risk_off_increases_risk_score():
    from graphs.nodes.scanner_node import scanner_node

    state: Dict[str, Any] = {
        "candidates": [{"symbol": "AAA"}],
        "mock_scan_results": {"AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80}},
        "mock_global_sentiment": -1.0,
        "policy": {
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.20,
            "confidence_news_boost": 0.0,
        },
    }

    out = scanner_node(state)
    sel = out["selected"]
    # base 0.10 + 0.20 * max(-(-1),0)=0.20 -> 0.30
    assert abs(float(sel["risk_score"]) - 0.30) < 1e-9
