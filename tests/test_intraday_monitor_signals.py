from libs.runtime.intraday_monitor_signals import (
    evaluate_intraday_entry_signal,
    resolve_intraday_entry_policy,
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


def _rows_pullback_rebound() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
        {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
        {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
        {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
        {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
        {"open": 100.2, "high": 101.3, "low": 100.1, "close": 101.1, "volume": 1500, "vwap": 100.7},
    ]


def _rows_daily_seed_like() -> list[dict]:
    start_ts = 1_710_000_000
    rows: list[dict] = []
    closes = [100.0, 101.5, 102.0, 103.0, 102.8, 104.0]
    for idx, close in enumerate(closes[:-1]):
        rows.append(
            {
                "ts": start_ts + idx * 86400,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + idx * 20_000,
                "vwap": close - 0.2,
            }
        )
    rows.append(
        {
            "ts": start_ts + len(closes[:-1]) * 86400,
            "open": 104.0,
            "high": 104.0,
            "low": 104.0,
            "close": 104.0,
            "volume": 1.0,
            "vwap": 103.4,
        }
    )
    return rows


def test_intraday_entry_triggers_on_breakout_vwap_hold_and_volume_confirmation() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["pattern"] == "breakout_vwap_hold"
    assert "volume_confirmation" in list(out.get("signal_chain") or [])
    assert float((out.get("metrics") or {}).get("volume_ratio") or 0.0) >= 1.15


def test_intraday_entry_triggers_on_pullback_rebound_setup() -> None:
    out = evaluate_intraday_entry_signal(
        _rows_pullback_rebound(),
        policy={"entry_breakout_lookback": 4, "entry_volume_ratio_min": 0.95},
        frame={"playbook": "pullback"},
    )

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["pattern"] == "pullback_vwap_reclaim"
    assert "pullback_rebound" in list(out.get("signal_chain") or [])
    assert "pullback_mature" in list(out.get("passed_checks") or [])
    assert out.get("primary_failure_axis") == "confirmed_entry"
    thresholds = out.get("thresholds") or {}
    assert float(thresholds.get("max_extended_from_vwap_pct") or 0.0) >= 0.05
    assert float(thresholds.get("pullback_max_pct") or 0.0) >= 0.06


def test_intraday_entry_rejects_overextended_breakout() -> None:
    rows = _rows_breakout()
    rows[-1]["close"] = 103.2
    rows[-1]["high"] = 103.4
    rows[-1]["vwap"] = 101.1
    out = evaluate_intraday_entry_signal(rows)

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["reason"] == "too_extended_from_vwap"
    assert out.get("primary_failure_axis") == "overextension"
    assert "extension_ok" in list(out.get("failed_checks") or [])


def test_intraday_entry_rejects_weak_volume_breakout() -> None:
    rows = _rows_breakout()
    rows[-1]["volume"] = 900
    out = evaluate_intraday_entry_signal(rows)

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "volume_insufficient"


def test_intraday_entry_rejects_failed_reclaim() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 100.1
    rows[-1]["high"] = 100.4
    rows[-1]["vwap"] = 100.8
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "reclaim_not_confirmed"
    assert out.get("primary_failure_axis") == "vwap_relationship"


def test_intraday_entry_rejects_overextended_pullback_even_after_rebound() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 106.0
    rows[-1]["high"] = 106.2
    rows[-1]["vwap"] = 100.7
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "still_overextended_after_pullback"
    assert out.get("primary_failure_axis") == "overextension"
    margins = out.get("threshold_margins") or {}
    ext = margins.get("extended_from_vwap_pct") or {}
    assert float(ext.get("actual") or 0.0) > float(ext.get("max") or 0.0)


def test_intraday_entry_rejects_deeply_broken_pullback_structure() -> None:
    rows = _rows_pullback_rebound()
    rows[4]["low"] = 94.8
    rows[4]["close"] = 99.8
    rows[-1]["close"] = 100.9
    rows[-1]["high"] = 101.0
    rows[-1]["vwap"] = 100.5
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["reason"] == "no_valid_pullback_structure"
    assert out.get("primary_failure_axis") == "pullback_structure"
    assert "pullback_not_too_deep" in list(out.get("failed_checks") or [])


def test_intraday_entry_pullback_can_pass_without_strict_volume_spike_if_reclaim_is_clean() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["volume"] = 900
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["pattern"] == "pullback_vwap_reclaim"


def test_intraday_entry_pullback_policy_is_looser_than_breakout_policy() -> None:
    breakout = resolve_intraday_entry_policy(frame={"playbook": "breakout"})
    pullback = resolve_intraday_entry_policy(frame={"playbook": "pullback"})

    assert float(pullback.get("max_extended_from_vwap_pct") or 0.0) > float(breakout.get("max_extended_from_vwap_pct") or 0.0)
    assert float(pullback.get("pullback_max_pct") or 0.0) > float(breakout.get("pullback_max_pct") or 0.0)
    assert float(pullback.get("volume_ratio_min") or 0.0) <= float(breakout.get("volume_ratio_min") or 0.0)


def test_intraday_entry_pullback_defensive_guidance_stays_realistic() -> None:
    pullback = resolve_intraday_entry_policy(
        frame={
            "playbook": "pullback",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        }
    )

    assert float(pullback.get("max_extended_from_vwap_pct") or 0.0) >= 0.05
    assert float(pullback.get("volume_ratio_min") or 0.0) <= 1.0


def test_intraday_entry_defensive_stack_stays_usable_without_becoming_loose() -> None:
    defensive = resolve_intraday_entry_policy(
        frame={
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "medium",
        }
    )

    assert float(defensive.get("max_extended_from_vwap_pct") or 0.0) >= 0.03
    assert float(defensive.get("max_extended_from_vwap_pct") or 0.0) <= 0.05
    assert float(defensive.get("volume_ratio_min") or 0.0) <= 1.1


def test_intraday_entry_waits_when_minute_candles_missing() -> None:
    out = evaluate_intraday_entry_signal([])

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "minute_candle_missing"
    metrics = out.get("metrics") or {}
    assert metrics.get("bar_count") == 0


def test_intraday_entry_waits_when_candle_data_incomplete() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout()[:3])

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "data_incomplete"
    metrics = out.get("metrics") or {}
    assert int(metrics.get("bar_count") or 0) == 3


def test_intraday_entry_rejects_non_intraday_seed_series_as_minute_data() -> None:
    out = evaluate_intraday_entry_signal(_rows_daily_seed_like(), current_price=104.0)

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "minute_candle_missing"
    metrics = out.get("metrics") or {}
    assert float(metrics.get("inferred_spacing_minutes") or 0.0) >= 1000.0
    assert metrics.get("series_class") == "daily_or_higher"
