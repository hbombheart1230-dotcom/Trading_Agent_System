from __future__ import annotations

from graphs.trading_graph import run_trading_graph


def test_m17_candidates_to_selected_top1_by_score():
    # Arrange: strategist will pick first 5 from universe
    state = {
        "universe": ["AAA", "BBB", "CCC", "DDD", "EEE"],
        # Make BBB the best by score
        "mock_scan_results": {
            "AAA": {"score": 0.1, "risk_score": 0.2, "confidence": 0.9},
            "BBB": {"score": 0.9, "risk_score": 0.3, "confidence": 0.8},
            "CCC": {"score": 0.2, "risk_score": 0.1, "confidence": 0.7},
            "DDD": {"score": 0.3, "risk_score": 0.5, "confidence": 0.6},
            "EEE": {"score": 0.4, "risk_score": 0.4, "confidence": 0.5},
        },
        "policy": {"min_confidence": 0.0, "max_risk": 1.0, "max_scan_retries": 0},
    }

    # Act
    out = run_trading_graph(state)

    # Assert
    assert "candidates" in out
    assert len(out["candidates"]) == 5
    assert out["selected"]["symbol"] == "BBB"
    assert isinstance(out.get("scan_results"), list) and len(out["scan_results"]) == 5
    assert out["risk"]["risk_score"] == 0.3
    assert out["risk"]["confidence"] == 0.8
