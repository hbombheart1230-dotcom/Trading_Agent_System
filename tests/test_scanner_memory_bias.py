from __future__ import annotations

from graphs.nodes.scanner_node import scanner_node
from libs.runtime.scanner_memory_bias import (
    build_scanner_memory_bias,
    compute_scanner_memory_bias_adjustment,
)


def test_build_scanner_memory_bias_surfaces_daily_and_symbol_rules() -> None:
    out = build_scanner_memory_bias(
        commander_memory_policy={
            "scanner_bias_enabled": True,
            "active_layers": ["daily", "symbol"],
            "symbol_memory_override_enabled": True,
        },
        memory_packets={
            "daily_strategy_memory": {
                "best_playbooks": ["pullback", "defensive"],
                "recent_failures": ["breakout_failure", "volume_confirmation_failure"],
            },
            "symbol_memory_packet": {
                "symbol": "005930",
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            },
        },
    )

    assert out["enabled"] is True
    assert float(out["source_weight_delta"]["top_value"]) > 0.0
    assert float(out["source_weight_delta"]["top_change_rate"]) < 0.0
    assert out["feature_bias"]["prefer_shallow_pullback_candidates"] is True
    assert out["feature_bias"]["prefer_reclaim_candidates"] is True
    assert out["feature_bias"]["prefer_volume_confirmation"] is True
    assert float(out["symbol_adjustments"]["005930"]["delta"]) > 0.0


def test_compute_scanner_memory_bias_adjustment_caps_total() -> None:
    out = compute_scanner_memory_bias_adjustment(
        symbol="005930",
        candidate_sources=["top_value", "top_change_rate"],
        memory_bias={
            "enabled": True,
            "source_weight_delta": {
                "top_value": 0.03,
                "top_change_rate": 0.03,
            },
            "symbol_adjustments": {
                "005930": {"delta": 0.03, "reason": "strong symbol override"},
            },
        },
    )

    assert float(out["source_delta"]) == 0.06
    assert float(out["symbol_delta"]) == 0.03
    assert float(out["bias_adjustment"]) == 0.03
    assert len(list(out["adjustments"] or [])) == 3


def test_scanner_memory_bias_can_flip_near_tie_and_surfaces_artifact_fields() -> None:
    state = {
        "candidates": [
            {"symbol": "AAA", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "BBB", "sources": ["top_change_rate"], "source_scores": {"top_change_rate": 1.0}},
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
            "strategy_policy": {
                "scanner_policy": {
                    "scanner_memory_bias": {
                        "enabled": True,
                        "active_layers": ["daily"],
                        "source_weight_delta": {"top_value": 0.015, "top_change_rate": -0.02},
                        "symbol_adjustments": {},
                        "reason": ["daily memory prefers pullback/value"],
                        "bias_source": "commander_memory_bias.v1",
                    }
                }
            },
        },
        "policy": {
            "enable_practical_scoring": False,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "feature_score_weight": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }

    out = scanner_node(state)

    assert (out.get("selected") or {}).get("symbol") == "AAA"
    selection_reason = out.get("scanner_selection_reason") or {}
    assert selection_reason.get("scanner_memory_bias_applied") is True
    assert "memory_bias=commander" in str(selection_reason.get("selection_reason_with_bias") or "")
    candidate_memory_bias_adjustments = list(selection_reason.get("candidate_memory_bias_adjustments") or [])
    assert candidate_memory_bias_adjustments[0]["symbol"] == "AAA"
    assert float(candidate_memory_bias_adjustments[0]["memory_bias_adjustment"]) > 0.0
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("scanner_memory_bias_applied") is True
    assert (scanner_output.get("scanner_memory_bias_summary") or {}).get("enabled") is True
