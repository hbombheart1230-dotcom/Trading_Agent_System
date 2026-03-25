from __future__ import annotations

import graphs.nodes.scanner_node as scanner_mod
from graphs.nodes.scanner_node import _compute_structured_scanner_bias, scanner_node


def _base_policy() -> dict:
    return {
        "enable_practical_scoring": False,
        "weight_news": 0.0,
        "weight_global": 0.0,
        "feature_score_weight": 0.0,
        "risk_news_penalty": 0.0,
        "risk_global_penalty": 0.0,
        "confidence_news_boost": 0.0,
    }


def _near_tie_state(*, scanner_bias: dict | None) -> dict:
    scanner_policy = {"scanner_bias": dict(scanner_bias or {})} if scanner_bias is not None else {}
    return {
        "candidates": [
            {"symbol": "AAA", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "BBB", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "AAA": {"score": 0.500, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.501, "risk_score": 0.20, "confidence": 0.80},
        },
        "scanner_features": {
            "AAA": {"vwap_distance": 0.005, "volume_spike20": 1.0},
            "BBB": {"vwap_distance": 0.060, "volume_spike20": 1.0},
        },
        "strategist_output": {
            "playbook": "pullback",
            "strategy_policy": {"scanner_policy": scanner_policy},
        },
        "policy": _base_policy(),
    }


def test_scanner_bias_missing_keeps_adjustment_zero() -> None:
    res = _compute_structured_scanner_bias(
        symbol="AAA",
        feature_row={"vwap_distance": 0.005, "volume_spike20": 1.5},
        metrics={"change_pct": 0.01},
        bias_context={},
    )

    assert res["bias_adjustment"] == 0.0
    assert res["bias_adjustments"] == []
    assert res["bias_summary"]["enabled"] is False


def test_scanner_bias_shallow_pullback_can_break_near_tie_only() -> None:
    no_bias_state = _near_tie_state(scanner_bias=None)
    biased_state = _near_tie_state(
        scanner_bias={
            "prefer_shallow_pullback_candidates": True,
            "bias_strength": "low",
        }
    )

    no_bias = scanner_node(no_bias_state)
    with_bias = scanner_node(biased_state)

    assert (no_bias.get("selected") or {}).get("symbol") == "BBB"
    assert (with_bias.get("selected") or {}).get("symbol") == "AAA"
    aaa_row = next(row for row in list(with_bias.get("scan_results") or []) if row.get("symbol") == "AAA")
    assert float(aaa_row.get("bias_adjustment") or 0.0) > 0.0
    assert float(aaa_row.get("bias_adjustment") or 0.0) <= 0.02


def test_scanner_bias_penalize_overextended_is_small_penalty() -> None:
    res = _compute_structured_scanner_bias(
        symbol="AAA",
        feature_row={"vwap_distance": 0.12, "volume_spike20": 1.0},
        metrics={"change_pct": 0.03},
        bias_context={
            "penalize_overextended": True,
            "bias_strength": "low",
        },
    )

    assert float(res["bias_adjustment"]) < 0.0
    assert abs(float(res["bias_adjustment"])) <= 0.02
    assert any(row.get("rule") == "penalize_overextended" for row in list(res["bias_adjustments"] or []))


def test_scanner_bias_total_effect_is_capped(monkeypatch) -> None:
    monkeypatch.setattr(scanner_mod, "_scanner_bias_total_cap", lambda strength: 0.01)
    res = _compute_structured_scanner_bias(
        symbol="AAA",
        feature_row={"vwap_distance": 0.0, "volume_spike20": 2.0},
        metrics={"change_pct": 0.01},
        bias_context={
            "prefer_shallow_pullback_candidates": True,
            "prefer_reclaim_candidates": True,
            "prefer_volume_confirmation": True,
            "bias_strength": "medium",
        },
    )

    assert float(res["bias_adjustment"]) == 0.01
