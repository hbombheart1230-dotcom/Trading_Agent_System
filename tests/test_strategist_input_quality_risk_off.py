from libs.runtime.strategist_input_quality import build_risk_off_exception_policy


def test_krx_night_futures_gap_down_is_risk_off_exception_policy_active():
    policy = build_risk_off_exception_policy(
        market_regime_rail={
            "market_regime": "risk_off",
            "market_regime_rail": "krx_night_futures_gap_down",
        },
        news_quality={"status": "ok"},
    )

    assert policy["risk_off_active"] is True
    assert "below_vwap_without_reclaim" in policy["disallowed_conditions"]
    assert "volume_confirmation" in policy["allowed_exception_conditions"]


def test_gap_down_rail_string_is_risk_off_even_when_regime_missing():
    policy = build_risk_off_exception_policy(
        market_regime_rail={
            "market_regime": "",
            "market_regime_rail": "krx_night_futures_gap_down",
        },
        news_quality={"status": "partial"},
    )

    assert policy["risk_off_active"] is True
    assert policy["market_regime_rail"] == "krx_night_futures_gap_down"
