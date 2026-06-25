from __future__ import annotations

from libs.runtime.scanner.candidate_risk import resolve_candidate_base_risk


def test_explicit_scanner_risk_remains_authoritative() -> None:
    result = resolve_candidate_base_risk(
        candidate={"risk_score": 0.42},
        scanner_row={"risk_score": 0.21},
        features={"volatility20": 0.20},
        quote_metrics={},
    )

    assert result["risk_score"] == 0.21
    assert result["source"] == "scanner_row"


def test_candidate_risk_fallback_does_not_depend_on_symbol_identity() -> None:
    inputs = {
        "features": {
            "close_last": 100_000,
            "atr14": 2_000,
            "volatility20": 0.04,
            "rolling_drawdown20": 0.02,
            "gap_pct": 0.01,
        },
        "quote_metrics": {
            "spread_bps": 4.0,
            "volume": 1_000_000,
            "trading_value": 100_000_000_000,
        },
    }

    samsung = resolve_candidate_base_risk(
        candidate={"symbol": "005930"},
        scanner_row={},
        **inputs,
    )
    hynix = resolve_candidate_base_risk(
        candidate={"symbol": "000660"},
        scanner_row={},
        **inputs,
    )

    assert samsung["risk_score"] == hynix["risk_score"]
    assert samsung["source"] == "market_data_fallback"


def test_higher_market_risk_inputs_produce_higher_fallback_risk() -> None:
    low = resolve_candidate_base_risk(
        features={
            "close_last": 100_000,
            "atr14": 1_000,
            "volatility20": 0.02,
            "rolling_drawdown20": 0.01,
            "gap_pct": 0.005,
        },
        quote_metrics={
            "spread_bps": 2.0,
            "volume": 1_000_000,
            "trading_value": 100_000_000_000,
        },
    )
    high = resolve_candidate_base_risk(
        features={
            "close_last": 100_000,
            "atr14": 5_000,
            "volatility20": 0.10,
            "rolling_drawdown20": 0.10,
            "gap_pct": 0.12,
        },
        quote_metrics={
            "spread_bps": 80.0,
            "volume": 1_000_000,
            "trading_value": 100_000_000_000,
        },
    )

    assert low["risk_score"] < high["risk_score"]
    assert low["risk_score"] < 0.70


def test_missing_market_inputs_are_visible_and_deterministic() -> None:
    first = resolve_candidate_base_risk(candidate={"symbol": "AAA"})
    second = resolve_candidate_base_risk(candidate={"symbol": "BBB"})

    assert first == second
    assert first["source"] == "market_data_fallback"
    assert "atr_ratio" in first["missing_inputs"]
    assert "trading_value" in first["missing_inputs"]
