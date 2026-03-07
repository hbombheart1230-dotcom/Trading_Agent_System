from __future__ import annotations

from graphs.nodes.scanner_node import scanner_node


def test_scanner_preserves_universe_candidate_metadata():
    state = {
        "candidates": [
            {
                "symbol": "AAA",
                "why": "held_position+market_rank",
                "sources": ["held_position", "market_rank"],
                "rank_score": 0.7,
                "universe_score": 4.2,
                "source_scores": {"held_position": 4.0, "market_rank": 0.2},
                "source_count": 2,
            },
            {
                "symbol": "BBB",
                "why": "market_rank",
                "sources": ["market_rank"],
                "rank_score": 0.2,
                "universe_score": 1.1,
                "source_scores": {"market_rank": 1.1},
                "source_count": 1,
            },
        ],
        "mock_scan_results": {
            "AAA": {"score": 0.4, "risk_score": 0.2, "confidence": 0.8},
            "BBB": {"score": 0.4, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    rows = {str(r.get("symbol")): r for r in out.get("scan_results", [])}
    assert rows["AAA"]["candidate"]["source_why"] == "held_position+market_rank"
    assert rows["AAA"]["candidate"]["sources"] == ["held_position", "market_rank"]
    assert float(rows["AAA"]["candidate"]["universe_score"]) == 4.2
    assert float(rows["AAA"]["candidate"]["source_scores"]["held_position"]) == 4.0
    assert int(rows["AAA"]["candidate"]["source_count"]) == 2
