from libs.reporting.market_regime_rail_review import classify_market_regime_rail
from libs.reporting.q8_shadow_blocker_review import build_q8_shadow_blocker_review


def test_classify_market_regime_rail_for_us_tech_positive_korea_weak() -> None:
    rail = classify_market_regime_rail(
        {
            "available": True,
            "generated_at": "2026-06-02T06:10:39+00:00",
            "index_moves": {
                "nasdaq_pct": 0.42,
                "sp500_pct": 0.26,
                "kospi_pct": -0.40,
                "kosdaq_pct": -2.45,
            },
            "korea_indices": {"breadth": -0.52},
            "macro_moves": {"dxy_pct": -0.04, "vix_level": 16.0, "vix_pct": 4.8},
            "macro_indicators": {
                "indicators": {
                    "usdkrw": {"change_pct": 0.58},
                    "us_10y_yield": {"delta": 0.02},
                }
            },
            "global_sentiment": {"score": -0.05},
        }
    )

    assert rail["rail_id"] == "us_tech_risk_on_korea_weak"
    assert rail["rail_confidence"] == "high"
    assert "breakout_not_ready" in rail["q8_review_focus"]
    assert rail["behavior_effect"] == "evaluation_only"


def test_q8_shadow_blocker_review_carries_market_regime_rail() -> None:
    review = build_q8_shadow_blocker_review(
        [],
        market_regime_rail={
            "rail_id": "us_tech_risk_on_korea_weak",
            "rail_confidence": "high",
            "rationale": "fixture",
            "q8_review_focus": ["breakout_not_ready"],
        },
    )

    assert review["market_regime_rail"]["rail_id"] == "us_tech_risk_on_korea_weak"
    assert review["behavior_effect"] == "evaluation_only"
