from libs.runtime.intraday_monitor_signals import evaluate_intraday_entry_signal


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
        {"open": 100.4, "high": 101.0, "low": 100.3, "close": 100.8, "volume": 1050, "vwap": 100.4},
        {"open": 100.8, "high": 101.5, "low": 100.7, "close": 101.3, "volume": 1100, "vwap": 100.8},
        {"open": 101.3, "high": 101.4, "low": 100.9, "close": 101.0, "volume": 950, "vwap": 101.1},
        {"open": 101.0, "high": 101.1, "low": 100.8, "close": 100.9, "volume": 980, "vwap": 101.0},
        {"open": 100.9, "high": 101.3, "low": 100.9, "close": 101.2, "volume": 1600, "vwap": 101.0},
    ]


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
        policy={"entry_breakout_lookback": 4, "entry_volume_ratio_min": 1.10},
        frame={"playbook": "pullback"},
    )

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["pattern"] == "pullback_rebound"
    assert "pullback_rebound" in list(out.get("signal_chain") or [])


def test_intraday_entry_rejects_overextended_breakout() -> None:
    rows = _rows_breakout()
    rows[-1]["close"] = 103.2
    rows[-1]["high"] = 103.4
    rows[-1]["vwap"] = 101.1
    out = evaluate_intraday_entry_signal(rows)

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["reason"] == "too_extended_from_vwap"


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
    rows[-1]["close"] = 100.7
    rows[-1]["high"] = 100.9
    rows[-1]["vwap"] = 101.0
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "no_breakout_signal"


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
