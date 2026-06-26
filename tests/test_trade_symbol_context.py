from libs.reporting.trade_symbol_context import normalize_trade_payload_symbol_context


def test_normalize_trade_payload_symbol_context_preserves_scanner_top_pick() -> None:
    payload = {
        "action": "BUY",
        "scanner_context": {
            "selected_symbol": "089030",
            "selected_rank": 1,
            "ranked_candidates": [
                {"symbol": "089030", "rank": 1, "score": 1.1, "status": "selected"},
                {
                    "symbol": "122630",
                    "rank": 6,
                    "score": 0.5,
                    "score_total": 0.52,
                    "status": "runner_up",
                    "confidence": 0.65,
                    "sources": ["top_volume"],
                    "source_scores": {"top_volume": 1.0},
                    "score_breakdown": {"momentum": 0.2, "risk_penalty": -0.1},
                },
            ],
            "scanner_selection_trace": {
                "selected_symbol": "089030",
                "ranked_candidates": [
                    {"symbol": "089030", "rank": 1, "score": 1.1, "status": "selected"},
                    {
                        "symbol": "122630",
                        "rank": 6,
                        "score": 0.5,
                        "score_total": 0.52,
                        "status": "runner_up",
                        "confidence": 0.65,
                        "sources": ["top_volume"],
                        "source_scores": {"top_volume": 1.0},
                        "score_breakdown": {"momentum": 0.2, "risk_penalty": -0.1},
                    },
                ],
            },
        },
    }

    normalized = normalize_trade_payload_symbol_context(payload, executed_symbol="122630")

    assert normalized["symbol"] == "122630"
    scanner_context = normalized["scanner_context"]
    assert scanner_context["selected_symbol"] == "122630"
    assert scanner_context["scanner_selected_symbol"] == "089030"
    assert scanner_context["selected_rank"] == 6
    assert scanner_context["selected_score"] == 0.5
    assert scanner_context["selected_score_total"] == 0.52
    assert scanner_context["selected_status"] == "runner_up"
    assert scanner_context["selected_sources"] == ["top_volume"]
    assert scanner_context["source_scores"] == {"top_volume": 1.0}
    assert scanner_context["score_breakdown"]["momentum"] == 0.2
    assert scanner_context["confidence"] == 0.65
    assert scanner_context["selected_symbol_score_drivers"] == {
        "momentum": 0.2,
        "risk_penalty": -0.1,
    }
    assert "scanner rank #6" in scanner_context["selection_reason"]
    assert "089030" in scanner_context["selection_reason"]
    assert scanner_context["selection_mismatch"]["status"] == "executed_symbol_differs_from_scanner_selected"
    assert scanner_context["scanner_selection_trace"]["selected_symbol"] == "122630"
    assert scanner_context["scanner_selection_trace"]["scanner_selected_symbol"] == "089030"


def test_normalize_trade_payload_symbol_context_drops_stale_rank_when_candidate_missing() -> None:
    payload = {
        "scanner_context": {
            "selected_symbol": "089030",
            "selected_rank": 1,
            "selected_score_total": 1.1,
            "ranked_candidates": [
                {"symbol": "089030", "rank": 1, "score_total": 1.1},
                {"symbol": "001740", "rank": 2, "score_total": 1.0},
            ],
        }
    }

    normalized = normalize_trade_payload_symbol_context(payload, executed_symbol="122630")

    scanner_context = normalized["scanner_context"]
    assert scanner_context["selected_symbol"] == "122630"
    assert scanner_context["scanner_selected_symbol"] == "089030"
    assert scanner_context["scanner_selected_rank"] == 1
    assert scanner_context["scanner_selected_score_total"] == 1.1
    assert "selected_rank" not in scanner_context
    assert "selected_score" not in scanner_context
    assert "selected_score_total" not in scanner_context
    assert "selected_sources" not in scanner_context
    assert scanner_context["selection_reason"] == (
        "executed symbol 122630; scanner candidate metrics unavailable"
    )


def test_normalize_uses_score_total_when_candidate_has_no_score() -> None:
    normalized = normalize_trade_payload_symbol_context(
        {
            "scanner_context": {
                "selected_symbol": "000660",
                "selected_score": 1.01,
                "selected_sources": ["top_value"],
                "score_breakdown": {"momentum": 0.4},
                "ranked_candidates": [
                    {"symbol": "000660", "rank": 1, "score_total": 1.01},
                    {
                        "symbol": "005930",
                        "rank": 2,
                        "score_total": 0.79,
                        "confidence": 0.62,
                    },
                ],
                "scanner_selection_trace": {
                    "selected_symbol": "000660",
                    "selected_rank": 1,
                    "selected_symbol_score_drivers": {"momentum": 0.4},
                },
            }
        },
        executed_symbol="005930",
    )

    scanner = normalized["scanner_context"]
    assert scanner["selected_rank"] == 2
    assert scanner["selected_score"] == 0.79
    assert scanner["selected_score_total"] == 0.79
    assert scanner["confidence"] == 0.62
    assert "selected_sources" not in scanner
    assert "score_breakdown" not in scanner
    assert scanner["selected_symbol_score_drivers"] == {}
    assert scanner["scanner_selection_trace"]["selected_rank"] == 2
    assert scanner["scanner_selection_trace"]["selected_symbol_score_drivers"] == {}


def test_normalize_reanchors_stale_selection_sentence_and_selected_candidate() -> None:
    normalized = normalize_trade_payload_symbol_context(
        {
            "scanner_context": {
                "selected_symbol": "005930",
                "selected_rank": 2,
                "selected_score": 0.79,
                "confidence": 0.62,
                "selection_reason": "final selected symbol 000660 ranked #1 with score 1.015",
                "selected_candidate": {
                    "symbol": "000660",
                    "rank": 1,
                    "score_total": 1.015,
                },
                "ranked_candidates": [
                    {"symbol": "000660", "rank": 1, "score_total": 1.015},
                    {"symbol": "005930", "rank": 2, "score_total": 0.79, "confidence": 0.62},
                ],
            }
        },
        executed_symbol="005930",
    )

    scanner = normalized["scanner_context"]
    assert scanner["scanner_selected_symbol"] == "000660"
    assert scanner["scanner_selected_candidate"]["symbol"] == "000660"
    assert scanner["selected_candidate"]["symbol"] == "005930"
    assert "000660 was not executed" in scanner["selection_reason"]
