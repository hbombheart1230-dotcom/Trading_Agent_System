from libs.runtime.chart_structure_features import (
    build_chart_structure_features,
    empty_chart_structure_features,
)


def _rows_breakout() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]


def _rows_failed_breakout() -> list[dict]:
    rows = _rows_breakout()
    rows[-1]["close"] = 100.95
    rows[-1]["high"] = 101.9
    rows[-1]["low"] = 100.9
    rows[-1]["vwap"] = 101.25
    rows[-1]["volume"] = 800
    return rows


def test_empty_chart_structure_features_is_unavailable_safe() -> None:
    out = empty_chart_structure_features(notes=["insufficient_candles"])

    assert out["schema_version"] == "chart_structure_features.v1"
    assert out["available"] is False
    assert (out.get("structure") or {}).get("structure_hh_hl") is None
    assert (out.get("trend_alignment") or {}).get("ma_alignment_state") is None
    assert (out.get("support_resistance") or {}).get("support_holding") is None
    assert (out.get("continuity_momentum") or {}).get("momentum_follow_through") is None
    assert out["notes"] == ["insufficient_candles"]


def test_build_chart_structure_features_extracts_breakout_bias_states() -> None:
    rows = _rows_breakout()
    out = build_chart_structure_features(
        rows,
        current_price=101.8,
        current_vwap=101.2,
        recent_high=101.4,
        breakout_ok=True,
        pullback_ok=False,
        reclaim_ok=True,
        volume_ok=True,
        confidence_ok=True,
        volume_ratio=2.31,
        too_extended=False,
    )

    assert out["schema_version"] == "chart_structure_features.v1"
    assert out["available"] is True
    assert (out.get("structure") or {}).get("structure_breakout_attempt") == "confirmed"
    assert (out.get("trend_alignment") or {}).get("ma_alignment_state") == "bullish"
    assert (out.get("trend_alignment") or {}).get("trend_regime") == "trending"
    assert (out.get("support_resistance") or {}).get("resistance_break_confirmed") == "confirmed"
    assert (out.get("continuity_momentum") or {}).get("volume_sustain") == "strong"
    assert (out.get("continuity_momentum") or {}).get("momentum_follow_through") in {"moderate", "strong"}


def test_build_chart_structure_features_marks_failed_breakout_when_rejected() -> None:
    rows = _rows_failed_breakout()
    out = build_chart_structure_features(
        rows,
        current_price=100.95,
        current_vwap=101.25,
        recent_high=101.4,
        breakout_ok=False,
        pullback_ok=False,
        reclaim_ok=False,
        volume_ok=False,
        confidence_ok=False,
        volume_ratio=0.74,
        too_extended=False,
    )

    assert out["available"] is True
    assert (out.get("structure") or {}).get("structure_breakout_attempt") == "rejected"
    assert (out.get("support_resistance") or {}).get("resistance_break_confirmed") == "failed"
    assert (out.get("support_resistance") or {}).get("failed_breakout") in {"suspected", "confirmed"}
    assert (out.get("continuity_momentum") or {}).get("momentum_decay") in {"mild", "strong"}
