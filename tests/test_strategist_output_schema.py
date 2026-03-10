from __future__ import annotations

from libs.strategies.contracts import StrategistOutput, coerce_strategist_output


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
        "report_focus": ["theme_accuracy"],
        "monitor_policy": {"min_hold_seconds": 600},
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
    assert out["monitor_policy"] == {"min_hold_seconds": 600}
    assert out["regime_score"] == 0.42
