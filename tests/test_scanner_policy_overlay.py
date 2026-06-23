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


def _neutral_scanner_features(*symbols):
    return {
        symbol: {
            "return20": 0.0,
            "ma20_gap": 0.0,
            "ma60_gap": 0.0,
            "ma120_gap": 0.0,
            "trend_strength": 0.0,
            "adx14": 0.0,
            "volume_spike20": 1.0,
            "vwap_distance": 0.0,
            "cross_section_rank": 0.0,
            "volatility20": 0.0,
            "signal_score": 0.0,
        }
        for symbol in symbols
    }


def _flat_candidate_metrics(*symbols):
    return {
        symbol: {"change_pct": 0.0, "volume": 1.0, "trading_value": 1.0}
        for symbol in symbols
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
    assert result.get("selected", {}).get("symbol") in {"AAPL", "MSFT"}

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
    assert scanner_output.get("diversification_applied") is False
    assert result.get("selected", {}).get("symbol") in {"AAPL", "MSFT"}

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


def test_market_representative_guard_promotes_confirmed_runner_up_when_top_value_only(tmp_path):
    scanner_policy = {
        "market_representative_guard": {
            "enabled": True,
            "symbols": ["005930", "000660"],
            "penalty": 0.04,
            "near_tie_gap": 0.06,
            "top_value_dominance_min": 0.55,
            "weak_confirmation_max": 1,
            "strong_confirmation_min": 2,
        }
    }
    mock_results = {
        "005930": {"score": 0.81, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "042700": {"score": 0.78, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    state["reports_root"] = str(tmp_path / "reports")
    state["scanner_features"] = _neutral_scanner_features("005930", "042700")
    state["mock_candidate_metrics"] = _flat_candidate_metrics("005930", "042700")
    state["candidates"] = [
        {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 2.0}},
        {"symbol": "042700", "sources": ["sector_theme", "top_volume"], "source_scores": {"sector_theme": 1.8, "top_volume": 1.2}},
    ]

    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("market_representative_guard_applied") is True
    assert scanner_output.get("market_representative_guard_symbol") == "005930"
    assert scanner_output.get("market_representative_guard_penalty") == 0.04
    assert result.get("selected", {}).get("symbol") == "042700"
    assert any("market_representative_guard 005930" in item for item in scanner_output.get("score_adjustment_trace") or [])


def test_market_representative_guard_keeps_market_leader_when_confirmation_is_strong(tmp_path):
    scanner_policy = {
        "market_representative_guard": {
            "enabled": True,
            "symbols": ["005930", "000660"],
            "penalty": 0.04,
            "near_tie_gap": 0.06,
            "top_value_dominance_min": 0.55,
            "weak_confirmation_max": 1,
            "strong_confirmation_min": 2,
            "bypass_when_strong_confirmation": True,
        }
    }
    mock_results = {
        "005930": {"score": 0.81, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "042700": {"score": 0.78, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy=scanner_policy,
        mock_scan_results=mock_results,
    )
    state["reports_root"] = str(tmp_path / "reports")
    state["scanner_features"] = _neutral_scanner_features("005930", "042700")
    state["mock_candidate_metrics"] = _flat_candidate_metrics("005930", "042700")
    state["candidates"] = [
        {
            "symbol": "005930",
            "sources": ["top_value", "sector_theme", "top_volume"],
            "source_scores": {"top_value": 2.0, "sector_theme": 1.5, "top_volume": 1.2},
        },
        {"symbol": "042700", "sources": ["sector_theme"], "source_scores": {"sector_theme": 1.8}},
    ]

    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("market_representative_guard_applied") is False
    assert scanner_output.get("market_representative_guard_reason") == "strong_confirmation"
    assert result.get("selected", {}).get("symbol") == "005930"


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


def test_scanner_excludes_mock_broker_restricted_symbol_before_ranking():
    mock_results = {
        "AAA": {"score": 0.90, "confidence": 0.9, "risk_score": 0.1, "compatibility_bias": 0.0},
        "BBB": {"score": 0.70, "confidence": 0.8, "risk_score": 0.2, "compatibility_bias": 0.0},
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy={},
        mock_scan_results=mock_results,
    )
    state["persisted_state"]["mock_broker_restricted_symbols"] = {
        "AAA": {
            "symbol": "AAA",
            "broker_code": "20",
            "broker_message": "RC4007 restricted symbol",
            "reason": "broker_rejected:20",
            "detected_date": "2026-04-24",
        }
    }

    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    assert result.get("selected", {}).get("symbol") == "BBB"
    assert scanner_output.get("mock_broker_restricted_filter_applied") is True
    assert scanner_output.get("excluded_candidate_count_by_mock_broker_restricted") == 1
    assert scanner_output.get("excluded_candidates_by_mock_broker_restricted")[0]["symbol"] == "AAA"


def test_blocker_family_concentration_promotes_alternative_family():
    mock_results = {
        "AAA": {
            "score": 0.90,
            "confidence": 0.9,
            "risk_score": 0.1,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "BBB": {
            "score": 0.89,
            "confidence": 0.85,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "CCC": {
            "score": 0.88,
            "confidence": 0.84,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "DDD": {
            "score": 0.87,
            "confidence": 0.83,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "volume_insufficient",
                "dominant_block_reason": "volume_insufficient",
                "compatibility_bias": 0.0,
            },
        },
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy={},
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    ranked_top3 = list(result.get("ranked_candidates") or [])[:3]

    assert scanner_output.get("blocker_family_concentration_applied") is True
    assert scanner_output.get("selection_vetoed") is False
    assert any((row or {}).get("symbol") == "DDD" for row in ranked_top3)


def test_blocker_family_concentration_does_not_null_selection_without_alternative_by_default():
    mock_results = {
        "AAA": {
            "score": 0.90,
            "confidence": 0.9,
            "risk_score": 0.1,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "BBB": {
            "score": 0.89,
            "confidence": 0.85,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "CCC": {
            "score": 0.88,
            "confidence": 0.84,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy={},
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("blocker_family_concentration_applied") is True
    assert scanner_output.get("selection_vetoed") is True
    assert scanner_output.get("selection_veto_enforced") is False
    assert scanner_output.get("selection_veto_reason") == "blocker_family_concentration_no_alternative"
    assert "selection_veto_observed_not_enforced" in list(scanner_output.get("score_adjustment_trace") or [])
    assert result.get("selected", {}).get("symbol") == "AAA"
    assert result.get("top_stock") == "AAA"


def test_blocker_family_concentration_can_still_enforce_null_selection_when_configured():
    mock_results = {
        "AAA": {
            "score": 0.90,
            "confidence": 0.9,
            "risk_score": 0.1,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "BBB": {
            "score": 0.89,
            "confidence": 0.85,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
        "CCC": {
            "score": 0.88,
            "confidence": 0.84,
            "risk_score": 0.2,
            "compatibility_override": {
                "expected_monitor_block_reason": "too_extended_from_vwap",
                "dominant_block_reason": "too_extended_from_vwap",
                "compatibility_bias": 0.0,
            },
        },
    }
    state = _mock_state_for_scanner(
        open_position_count=0,
        scanner_policy={"enforce_blocker_family_selection_veto": True},
        mock_scan_results=mock_results,
    )
    result = scanner_node(state)

    scanner_output = result.get("scanner_output", {})
    assert scanner_output.get("blocker_family_concentration_applied") is True
    assert scanner_output.get("selection_vetoed") is True
    assert scanner_output.get("selection_veto_enforced") is True
    assert scanner_output.get("selection_veto_reason") == "blocker_family_concentration_no_alternative"
    assert result.get("selected") is None
    assert result.get("top_stock") in ("", None)
