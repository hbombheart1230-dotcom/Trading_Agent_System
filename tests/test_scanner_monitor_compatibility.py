from __future__ import annotations

import graphs.nodes.scanner_node as scanner_mod
from graphs.nodes.scanner_node import scanner_node


def _base_state() -> dict:
    return {
        "policy": {
            "enable_practical_scoring": False,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "feature_score_weight": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
        "strategist_output": {
            "playbook": "pullback",
            "monitor_guidance": "wait_for_reclaim",
            "trade_aggressiveness": "medium",
            "risk_tone": "balanced",
            "strategy_policy": {
                "commander_context": {
                    "policy_source": "strategist",
                    "applied_policy": {
                        "timeframe_minutes": 1,
                        "breakout_lookback": 5,
                        "volume_lookback": 5,
                        "volume_ratio_min": 0.68,
                        "min_extended_from_vwap_pct": -0.02,
                        "max_extended_from_vwap_pct": 0.13,
                        "pullback_min_pct": 0.008,
                        "pullback_max_pct": 0.07,
                        "reclaim_tolerance_pct": 0.0015,
                        "breakout_buffer_pct": 0.0,
                        "intent_cooldown_sec": 60,
                        "require_vwap_reclaim": True,
                        "require_rebound": True,
                    },
                },
                "monitor_policy": {
                    "entry_policy": {
                        "volume_ratio_min": 0.68,
                    }
                },
            },
        },
    }


def test_scanner_refreshes_feature_hydration_when_quote_metrics_missing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_hydrate(*, state, candidates, skill_quotes, policy, refresh_existing=False):
        captured["refresh_existing"] = bool(refresh_existing)
        return (
            {
                "005930": {"vwap_distance": 0.01, "volume_spike20": 1.0},
                "000660": {"vwap_distance": 0.02, "volume_spike20": 1.0},
            },
            "state.feature_engine.by_symbol",
            [],
        )

    monkeypatch.setattr(scanner_mod, "hydrate_scanner_feature_map", _fake_hydrate)

    state = _base_state()
    state.update(
        {
            "candidates": ["005930", "000660"],
            "feature_engine": {
                "by_symbol": {
                    "005930": {"vwap_distance": 0.01},
                    "000660": {"vwap_distance": 0.02},
                }
            },
            "mock_scan_results": {
                "005930": {"score": 0.51, "risk_score": 0.20, "confidence": 0.80},
                "000660": {"score": 0.50, "risk_score": 0.21, "confidence": 0.79},
            },
        }
    )

    out = scanner_node(state)

    assert captured["refresh_existing"] is True
    assert (out.get("scanner_quote_diagnostic") or {}).get("feature_refresh_forced") is True
    assert (out.get("scanner_feature") or {}).get("refresh_existing") is True


def test_scanner_compatibility_bias_stays_neutral_without_applied_policy() -> None:
    state = {
        "policy": {
            "enable_practical_scoring": False,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "feature_score_weight": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
        "candidates": ["AAA", "BBB"],
        "mock_scan_results": {
            "AAA": {"score": 0.500, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.501, "risk_score": 0.20, "confidence": 0.80},
        },
        "scanner_features": {
            "AAA": {"vwap_distance": 0.002, "volume_spike20": 1.3},
            "BBB": {"vwap_distance": -0.08, "volume_spike20": 0.4},
        },
        "strategist_output": {
            "playbook": "pullback",
            "strategy_policy": {"scanner_policy": {}},
        },
    }

    out = scanner_node(state)

    assert (out.get("selected") or {}).get("symbol") == "BBB"
    assert float(((out.get("selected") or {}).get("compatibility_bias") or 0.0)) == 0.0


def test_scanner_entry_compatibility_bias_can_flip_near_tie(monkeypatch) -> None:
    def _fake_compatibility(*, symbol, feature_row, metrics, candidate_rows, current_price, policy):
        if symbol == "005930":
            return {
                "entry_compatibility_score": 0.95,
                "compatibility_bias": 0.024,
                "compatibility_components": {
                    "vwap_proximity_score": 0.96,
                    "volume_readiness_score": 1.0,
                    "breakout_readiness_score": 0.90,
                    "reclaim_proximity": 0.96,
                },
                "expected_monitor_block_reason": "",
                "compatibility_source": "minute_eval",
                "triggered_path": "breakout_path",
                "paths_passed": ["breakout_path"],
                "vwap_distance_abs": 0.004,
                "is_below_vwap": False,
                "reclaim_proximity": 1.0,
                "volume_ratio": 0.96,
                "breakout_gap_pct": 0.002,
            }
        return {
            "entry_compatibility_score": 0.10,
            "compatibility_bias": -0.024,
            "compatibility_components": {
                "vwap_proximity_score": 0.17,
                "volume_readiness_score": 0.34,
                "breakout_readiness_score": 0.20,
                "reclaim_proximity": 0.17,
            },
            "expected_monitor_block_reason": "below_vwap_reclaim_not_ready",
            "compatibility_source": "minute_eval",
            "triggered_path": "",
            "paths_passed": [],
            "vwap_distance_abs": 0.083,
            "is_below_vwap": True,
            "reclaim_proximity": 0.08,
            "volume_ratio": 0.23,
            "breakout_gap_pct": -0.008,
        }

    monkeypatch.setattr(scanner_mod, "_compute_entry_compatibility_signal", _fake_compatibility)

    state = _base_state()
    state.update(
        {
            "candidates": [
                {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
                {"symbol": "000660", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            ],
            "mock_scan_results": {
                "005930": {"score": 0.500, "risk_score": 0.20, "confidence": 0.80},
                "000660": {"score": 0.501, "risk_score": 0.20, "confidence": 0.80},
            },
            "scanner_features": {
                "005930": {"vwap_distance": 0.002, "volume_spike20": 1.3},
                "000660": {"vwap_distance": -0.08, "volume_spike20": 0.4},
            },
        }
    )

    out = scanner_node(state)

    assert (out.get("selected") or {}).get("symbol") == "005930"
    ranked = list(out.get("ranked_candidates") or [])
    top_row = ranked[0]
    second_row = ranked[1]
    assert top_row["symbol"] == "005930"
    assert float(top_row.get("compatibility_bias") or 0.0) > 0.0
    assert float(second_row.get("compatibility_bias") or 0.0) < 0.0
    assert "entry_compatibility_bias" in ((out.get("selected") or {}).get("score_breakdown") or {})
    assert float((out.get("selected") or {}).get("pre_adjust_score_total") or 0.0) < float((out.get("selected") or {}).get("post_adjust_score_total") or 0.0)


def test_scanner_compatibility_bias_shrinks_032820_margin_vs_396500(monkeypatch) -> None:
    def _fake_compatibility(*, symbol, feature_row, metrics, candidate_rows, current_price, policy):
        if symbol == "032820":
            return {
                "entry_compatibility_score": 0.22,
                "compatibility_bias": -0.0224,
                "compatibility_components": {
                    "vwap_proximity_score": 0.18,
                    "volume_readiness_score": 0.31,
                    "breakout_readiness_score": 0.28,
                    "reclaim_proximity": 0.18,
                },
                "expected_monitor_block_reason": "below_vwap_reclaim_not_ready",
                "compatibility_source": "minute_eval",
                "triggered_path": "",
                "paths_passed": [],
                "vwap_distance_abs": 0.083,
                "is_below_vwap": True,
                "reclaim_proximity": 0.18,
                "volume_ratio": 0.24,
                "breakout_gap_pct": -0.008,
            }
        return {
            "entry_compatibility_score": 0.60,
            "compatibility_bias": 0.008,
            "compatibility_components": {
                "vwap_proximity_score": 0.72,
                "volume_readiness_score": 0.58,
                "breakout_readiness_score": 0.48,
                "reclaim_proximity": 0.72,
            },
            "expected_monitor_block_reason": "breakout_not_ready",
            "compatibility_source": "minute_eval",
            "triggered_path": "",
            "paths_passed": [],
            "vwap_distance_abs": 0.018,
            "is_below_vwap": False,
            "reclaim_proximity": 0.72,
            "volume_ratio": 0.62,
            "breakout_gap_pct": -0.004,
        }

    monkeypatch.setattr(scanner_mod, "_compute_entry_compatibility_signal", _fake_compatibility)

    state = _base_state()
    state.update(
        {
            "candidates": [
                {"symbol": "032820", "sources": ["sector_theme"], "source_scores": {"top_value": 1.0}},
                {"symbol": "396500", "sources": ["sector_theme"], "source_scores": {"top_value": 1.0}},
            ],
            "mock_scan_results": {
                "032820": {"score": 0.530, "risk_score": 0.20, "confidence": 0.80},
                "396500": {"score": 0.525, "risk_score": 0.20, "confidence": 0.80},
            },
            "scanner_features": {
                "032820": {"vwap_distance": -0.08, "volume_spike20": 0.4},
                "396500": {"vwap_distance": -0.01, "volume_spike20": 0.9},
            },
        }
    )

    out = scanner_node(state)
    ranked = list(out.get("ranked_candidates") or [])

    assert ranked[0]["symbol"] == "396500"
    assert ranked[1]["symbol"] == "032820"
    assert float(ranked[1]["pre_adjust_score_total"]) > float(ranked[0]["pre_adjust_score_total"])
    assert float(ranked[1]["post_adjust_score_total"]) < float(ranked[0]["post_adjust_score_total"])


def test_scanner_output_records_entry_compatibility_trace(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner_mod,
        "_compute_entry_compatibility_signal",
        lambda **kwargs: {
            "entry_compatibility_score": 0.88,
            "compatibility_bias": 0.018,
            "compatibility_components": {
                "vwap_proximity_score": 0.90,
                "volume_readiness_score": 0.84,
                "breakout_readiness_score": 0.72,
                "reclaim_proximity": 0.90,
            },
            "expected_monitor_block_reason": "",
            "compatibility_source": "minute_eval",
            "triggered_path": "pullback_volume_path",
            "paths_passed": ["pullback_volume_path"],
            "vwap_distance_abs": 0.01,
            "is_below_vwap": False,
            "reclaim_proximity": 0.92,
            "volume_ratio": 0.84,
            "breakout_gap_pct": -0.001,
        },
    )

    state = _base_state()
    state.update(
        {
            "candidates": ["005930"],
            "mock_scan_results": {
                "005930": {"score": 0.55, "risk_score": 0.20, "confidence": 0.82},
            },
            "scanner_features": {
                "005930": {"vwap_distance": 0.001, "volume_spike20": 1.2},
            },
        }
    )

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    selection_reason = out.get("scanner_candidate_selection_reason") or {}

    assert scanner_output.get("entry_compatibility_score") == 0.88
    assert scanner_output.get("compatibility_bias") == 0.018
    assert scanner_output.get("compatibility_components", {}).get("vwap_proximity_score") == 0.90
    assert scanner_output.get("expected_monitor_block_reason") == ""
    assert scanner_output.get("compatibility_trace", {}).get("triggered_path") == "pullback_volume_path"
    assert scanner_output.get("pre_adjust_score_total") == 0.55
    assert scanner_output.get("post_adjust_score_total") == 0.5680000000000001
    assert selection_reason.get("entry_compatibility_score") == 0.88
    assert selection_reason.get("compatibility_trace", {}).get("paths_passed") == ["pullback_volume_path"]
