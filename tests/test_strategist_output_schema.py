from __future__ import annotations

from libs.strategies.contracts import StrategyInput, StrategistOutput, coerce_strategist_output


def test_strategist_output_schema_normalizes_enum_fields() -> None:
    dto = StrategistOutput(
        market_regime="RISK_ON",  # type: ignore[arg-type]
        market_sentiment="BULLISH",  # type: ignore[arg-type]
        playbook="BREAKOUT",  # type: ignore[arg-type]
        scanner_bias="MOMENTUM",  # type: ignore[arg-type]
        trade_aggressiveness="HIGH",  # type: ignore[arg-type]
        risk_tone="AGGRESSIVE",  # type: ignore[arg-type]
        monitor_guidance="HOLD_THROUGH_NOISE",  # type: ignore[arg-type]
        themes=["semiconductor"],
        scanner_priority=["momentum", "trend_strength"],
        scanner_source_policy={
            "include_change_rate": True,
            "include_condition_search": True,
            "preferred_sources": ["top_change_rate", "condition_search"],
        },
        strategy_policy={
            "market_policy": {"playbook": "breakout"},
            "scanner_policy": {"candidate_sources": {"include_change_rate": True}},
        },
        report_focus=["theme_accuracy", "overtrading"],
        candidates=["005930", "000660"],
        candidate_count=2,
    ).to_dict()

    assert dto["market_regime"] == "risk_on"
    assert dto["market_sentiment"] == "bullish"
    assert dto["playbook"] == "breakout"
    assert dto["scanner_bias"] == "momentum"
    assert dto["trade_aggressiveness"] == "high"
    assert dto["risk_tone"] == "aggressive"
    assert dto["monitor_guidance"] == "hold_through_noise"
    assert dto["scanner_source_policy"]["include_change_rate"] is True
    assert dto["scanner_source_policy"]["preferred_sources"] == ["top_change_rate", "condition_search"]
    assert dto["strategy_policy"]["schema_version"] == "strategy_policy.v1"
    assert dto["strategy_policy"]["market_policy"]["playbook"] == "breakout"
    assert dto["candidate_count"] == 2


def test_strategist_output_schema_falls_back_for_invalid_enums() -> None:
    dto = StrategistOutput(
        market_regime="unknown",  # type: ignore[arg-type]
        market_sentiment="unknown",  # type: ignore[arg-type]
        playbook="unknown",  # type: ignore[arg-type]
        scanner_bias="unknown",  # type: ignore[arg-type]
        trade_aggressiveness="unknown",  # type: ignore[arg-type]
        risk_tone="unknown",  # type: ignore[arg-type]
        monitor_guidance="unknown",  # type: ignore[arg-type]
    ).to_dict()

    assert dto["market_regime"] == "neutral"
    assert dto["market_sentiment"] == "neutral"
    assert dto["playbook"] == "defensive"
    assert dto["scanner_bias"] == "leader"
    assert dto["trade_aggressiveness"] == "medium"
    assert dto["risk_tone"] == "normal"
    assert dto["monitor_guidance"] == "defensive_exit"


def test_coerce_strategist_output_normalizes_required_fields_and_keeps_additive_keys() -> None:
    raw = {
        "market_regime": "RISK_ON",
        "market_sentiment": "BULLISH",
        "playbook": "BREAKOUT",
        "scanner_bias": "LEADER",
        "trade_aggressiveness": "HIGH",
        "risk_tone": "AGGRESSIVE",
        "monitor_guidance": "HOLD_THROUGH_NOISE",
        "themes": ["semiconductor"],
        "scanner_priority": ["momentum"],
        "scanner_source_policy": {
            "include_change_rate": False,
            "include_condition_search": False,
            "preferred_sources": ["top_value", "top_volume"],
        },
        "strategy_policy": {
            "market_policy": {"playbook": "breakout"},
            "monitor_policy": {
                "position_guards": {"min_hold_seconds": 60},
                "entry_policy": {"volume_ratio_min": 0.72},
            },
        },
        "report_focus": ["theme_accuracy"],
        "monitor_policy": {"min_hold_seconds": 600},
        "policy_rationale": "Use a measured breakout policy.",
        "policy_validation_status": "ok",
        "policy_fallback_used": False,
        "confidence": 0.71,
        "regime_score": 0.42,
    }
    out = coerce_strategist_output(raw)

    assert out["market_regime"] == "risk_on"
    assert out["market_sentiment"] == "bullish"
    assert out["playbook"] == "breakout"
    assert out["scanner_bias"] == "leader"
    assert out["trade_aggressiveness"] == "high"
    assert out["risk_tone"] == "aggressive"
    assert out["monitor_guidance"] == "hold_through_noise"
    assert out["scanner_source_policy"]["include_change_rate"] is False
    assert out["scanner_source_policy"]["preferred_sources"] == ["top_value", "top_volume"]
    assert out["strategy_policy"]["schema_version"] == "strategy_policy.v1"
    assert out["strategy_policy"]["monitor_policy"]["position_guards"]["min_hold_seconds"] == 60
    assert out["monitor_policy"] == {"min_hold_seconds": 600}
    assert out["monitor_entry_policy"]["volume_ratio_min"] == 0.72
    assert out["monitor_entry_policy"]["threshold_policy"]["volume_ratio_min"] == 0.72
    assert out["monitor_entry_policy"]["interpretation_policy"]["entry_style"] == "breakout"
    assert "structure_hh_hl=intact" in list(out["monitor_entry_policy"]["interpretation_policy"]["preferred_checks"] or [])
    assert "momentum_follow_through=strong" in list(out["monitor_entry_policy"]["interpretation_policy"]["preferred_checks"] or [])
    assert "failed_breakout=confirmed" in list(out["monitor_entry_policy"]["interpretation_policy"]["blockers"] or [])
    assert "structure_hh_hl" in list(out["monitor_entry_policy"]["interpretation_policy"]["evidence_focus"]["primary"] or [])
    assert "momentum_follow_through" in list(out["monitor_entry_policy"]["interpretation_policy"]["evidence_focus"]["primary"] or [])
    assert out["policy_rationale"] == "Use a measured breakout policy."
    assert out["policy_validation_status"] == "ok"
    assert out["policy_fallback_used"] is False
    assert out["confidence"] == 0.71
    assert out["regime_score"] == 0.42


def test_coerce_strategist_output_preserves_string_list_fields_as_items() -> None:
    raw = {
        "themes": "semiconductor, AI",
        "avoid_themes": "high_gap_speculative",
        "scanner_priority": '["trading_value", "trend_strength"]',
        "report_focus": "theme_accuracy|exit_quality",
        "candidates": "005930,000660",
        "candidate_hints": "005930",
    }

    out = coerce_strategist_output(raw)

    assert out["themes"] == ["semiconductor", "AI"]
    assert out["avoid_themes"] == ["high_gap_speculative"]
    assert out["scanner_priority"] == ["trading_value", "trend_strength"]
    assert out["report_focus"] == ["theme_accuracy", "exit_quality"]
    assert out["candidates"] == ["005930", "000660"]
    assert out["candidate_hints"] == ["005930"]
    assert out["candidate_count"] == 2


def test_coerce_strategist_output_unwraps_nested_output_contract() -> None:
    raw = {
        "output": {
            "market_regime": "risk_on",
            "themes": ["semiconductor"],
            "avoid_themes": "high_gap_speculative",
        },
        "trace_id": "abc",
    }

    out = coerce_strategist_output(raw)

    assert out["market_regime"] == "risk_on"
    assert out["themes"] == ["semiconductor"]
    assert out["avoid_themes"] == ["high_gap_speculative"]
    assert out["trace_id"] == "abc"


def test_strategist_output_schema_normalizes_scanner_bias_context() -> None:
    dto = StrategistOutput(
        scanner_bias_context={
            "prefer_shallow_pullback_candidates": "yes",
            "penalize_overextended": True,
            "prefer_reclaim_candidates": False,
            "prefer_volume_confirmation": "1",
            "bias_strength": "MEDIUM",
        }
    ).to_dict()

    assert dto["scanner_bias_context"]["prefer_shallow_pullback_candidates"] is True
    assert dto["scanner_bias_context"]["penalize_overextended"] is True
    assert dto["scanner_bias_context"]["prefer_volume_confirmation"] is True
    assert dto["scanner_bias_context"]["bias_strength"] == "medium"


def test_coerce_strategist_output_invalid_scanner_bias_context_falls_back_safely() -> None:
    out = coerce_strategist_output(
        {
            "scanner_bias_context": {
                "prefer_shallow_pullback_candidates": True,
                "bias_strength": "extreme",
            }
        }
    )

    assert out["scanner_bias_context"]["prefer_shallow_pullback_candidates"] is True
    assert out["scanner_bias_context"]["bias_strength"] == "low"


def test_strategy_input_contract_keeps_reporter_feedback_packet_additively() -> None:
    dto = StrategyInput(
        symbol="005930",
        strategist_feedback_packet={
            "available": True,
            "status": "ok",
            "insight_summary": "Monitor-only share is elevated.",
        },
    ).to_dict()

    assert dto["symbol"] == "005930"
    assert dto["strategist_feedback_packet"]["available"] is True
    assert dto["strategist_feedback_packet"]["status"] == "ok"
