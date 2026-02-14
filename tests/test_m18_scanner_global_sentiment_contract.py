from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node
from graphs.nodes.scanner_node import scanner_node


def test_scanner_consumes_global_sentiment_emitted_by_strategist():
    state = {
        "mock_global_sentiment": 1.0,
        "universe": ["AAA"],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        "policy": {
            "candidate_k": 1,
            "weight_news": 0.0,
            "weight_global": 0.20,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }

    out = strategist_node(state)
    # Verify scanner can consume strategist output without mock fallback.
    out.pop("mock_global_sentiment", None)
    out = scanner_node(out)

    assert out["selected"]["symbol"] == "AAA"
    assert abs(float(out["selected"]["score"]) - 0.70) < 1e-9
