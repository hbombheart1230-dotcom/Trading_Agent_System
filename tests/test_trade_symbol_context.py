from libs.reporting.trade_symbol_context import normalize_trade_payload_symbol_context


def test_normalize_trade_payload_symbol_context_preserves_scanner_top_pick() -> None:
    payload = {
        "action": "BUY",
        "scanner_context": {
            "selected_symbol": "089030",
            "selected_rank": 1,
            "ranked_candidates": [
                {"symbol": "089030", "rank": 1, "score": 1.1, "status": "selected"},
                {"symbol": "122630", "rank": 6, "score": 0.5, "status": "runner_up"},
            ],
            "scanner_selection_trace": {
                "selected_symbol": "089030",
                "ranked_candidates": [
                    {"symbol": "089030", "rank": 1, "score": 1.1, "status": "selected"},
                    {"symbol": "122630", "rank": 6, "score": 0.5, "status": "runner_up"},
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
    assert scanner_context["selected_status"] == "runner_up"
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
    assert "selected_score_total" not in scanner_context
