from graphs.nodes.scanner_node import scanner_node


def test_scanner_filters_non_live_symbol_names_when_enforced(monkeypatch):
    monkeypatch.setenv("SCANNER_AUTO_SKILL_HYDRATION", "false")

    state = {
        "run_id": "run-live-symbol-filter",
        "candidates": [{"symbol": "SK"}, {"symbol": "000660"}],
        "mock_scan_results": {
            "SK": {"score": 9.0, "risk_score": 0.0, "confidence": 0.99},
            "000660": {"score": 1.0, "risk_score": 0.1, "confidence": 0.80},
        },
        "policy": {
            "enforce_live_equity_symbols": True,
            "enable_practical_scoring": False,
        },
    }

    out = scanner_node(state)

    assert out["selected"]["symbol"] == "000660"
    assert out["scanner_output"]["top_stock"] == "000660"
    pool = out["scanner_candidate_pool"]
    assert pool["live_equity_symbol_excluded_count"] == 1
    assert pool["live_equity_symbol_excluded_symbols"] == ["SK"]
