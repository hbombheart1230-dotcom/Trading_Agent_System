import pytest
from graphs.nodes.scanner_node import scanner_node

def _mock_state_for_scanner(
    open_position_count=0,
    last_trade_symbol="",
    scanner_policy=None,
    mock_scan_results=None,
):
    return {
        "run_id": "test_run",
        "commander_decision": {
            "scanner_policy": scanner_policy or {}
        },
        "persisted_state": {
            "last_trade_symbol": last_trade_symbol
        },
        "portfolio_snapshot": {
            "positions": [{"symbol": "dummy", "qty": 10}] if open_position_count > 0 else []
        },
        "mock_scan_results": mock_scan_results or {},
        "candidates": list(mock_scan_results.keys()) if mock_scan_results else [],
        "policy": {},
    }

def test_same_symbol_penalty_applied():
    scanner_policy = {
        "avoid_recent_symbol": True,
        "recent_symbol_penalty": 0.05,
        "reentry_score_gap_threshold": 0.03,
        "allow_same_symbol_reentry": True
    }
    mock_results = {
        "AAPL": {"score": 0.80, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "MSFT": {"score": 0.78, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        last_trade_symbol="AAPL",
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)
    
    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("reentry_penalty_applied") is True
    assert scanner_output.get("reentry_penalty_value") == 0.05
    
    # AAPL was 0.80, MSFT 0.78. Gap is 0.02 <= 0.03.
    # AAPL gets penalty 0.05 -> 0.75.
    # MSFT should now be top-1 with 0.78.
    assert result.get("selected", {}).get("symbol") == "MSFT"
    assert scanner_output.get("score_adjustment_trace")

def test_gap_threshold_exceeded():
    scanner_policy = {
        "avoid_recent_symbol": True,
        "recent_symbol_penalty": 0.05,
        "reentry_score_gap_threshold": 0.01,
        "allow_same_symbol_reentry": True
    }
    mock_results = {
        "AAPL": {"score": 0.80, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "MSFT": {"score": 0.75, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        last_trade_symbol="AAPL",
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)
    
    scanner_output = result.get("scanner_output", {})
    # Gap is 0.05 > 0.01, penalty not applied
    assert scanner_output.get("reentry_penalty_applied") is False
    assert result.get("selected", {}).get("symbol") == "AAPL"

def test_diversification_tie_break():
    scanner_policy = {
        "diversification_bias": 0.03,
        "reentry_score_gap_threshold": 0.02,
    }
    mock_results = {
        "AAPL": {"score": 0.80, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "MSFT": {"score": 0.79, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        last_trade_symbol="AAPL",
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)
    
    scanner_output = result.get("scanner_output", {})
    # AAPL 0.80, MSFT 0.79. Gap 0.01 <= 0.02. MSFT gets bonus 0.03 -> 0.82
    assert scanner_output.get("diversification_applied") is True
    assert scanner_output.get("diversification_bonus_value") == 0.03
    assert result.get("selected", {}).get("symbol") == "MSFT"

def test_regression_safety():
    scanner_policy = {}
    mock_results = {
        "AAPL": {"score": 0.80, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "MSFT": {"score": 0.78, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        last_trade_symbol="AAPL",
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)
    
    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("reentry_penalty_applied") is False
    assert scanner_output.get("diversification_applied") is False
    assert scanner_output.get("entry_bias_cap_applied") is False
    assert scanner_output.get("ranking_before_policy") == scanner_output.get("ranking_after_policy")
    assert result.get("selected", {}).get("symbol") == "AAPL"

def test_entry_bias_cap_applied():
    scanner_policy = {
        "entry_bias_cap": 0.05
    }
    mock_results = {
        "AAPL": {"score": 0.80, "confidence": 0.9, "risk_score": 0.1},
        "MSFT": {"score": 0.75, "confidence": 0.8, "risk_score": 0.2},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)
    
    scanner_output = result.get("scanner_output", {})
    assert "entry_bias_cap_applied" in scanner_output
    assert "applied_scanner_policy" in scanner_output
    assert scanner_output["applied_scanner_policy"]["entry_bias_cap"] == 0.05