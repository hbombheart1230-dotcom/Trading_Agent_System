from __future__ import annotations

from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes


def test_attach_forward_outcomes_rejects_cross_day_target_row() -> None:
    candidates = [
        {
            "symbol": "005930",
            "shadow_forward_base": {
                "available": True,
                "baseline_epoch": 1780876980,
                "baseline_price": 298500,
                "baseline_raw_ts": "20260608090300",
            },
        }
    ]
    minute_rows = {
        "005930": [
            {"ts": 1780876980, "close": 298500, "high": 298500, "low": 298500, "raw_ts": "20260608090300"},
            {"ts": 1781265120, "close": 335500, "high": 336500, "low": 335500, "raw_ts": "20260612125200"},
        ]
    }

    out = attach_forward_outcomes(candidates, minute_rows_by_symbol=minute_rows)
    checkpoint = out[0]["shadow_forward_outcome"]["checkpoints"]["+5m"]

    assert out[0]["shadow_forward_outcome"]["available"] is False
    assert checkpoint["status"] == "stale"
    assert checkpoint["reason"] == "stale_cross_day_observation"
    assert checkpoint["observed_ts"] == "20260612125200"


def test_attach_forward_outcomes_rejects_same_day_stale_gap() -> None:
    candidates = [
        {
            "symbol": "005930",
            "shadow_forward_base": {
                "available": True,
                "baseline_epoch": 1780876980,
                "baseline_price": 298500,
                "baseline_raw_ts": "20260608090300",
            },
        }
    ]
    minute_rows = {
        "005930": [
            {"ts": 1780876980, "close": 298500, "high": 298500, "low": 298500, "raw_ts": "20260608090300"},
            {"ts": 1780878000, "close": 301000, "high": 301000, "low": 300000, "raw_ts": "20260608092000"},
        ]
    }

    out = attach_forward_outcomes(candidates, minute_rows_by_symbol=minute_rows)
    checkpoint = out[0]["shadow_forward_outcome"]["checkpoints"]["+5m"]

    assert checkpoint["status"] == "stale"
    assert checkpoint["reason"] == "stale_forward_gap"
    assert checkpoint["delay_sec"] > 180


def test_attach_forward_outcomes_accepts_near_target_same_day_row() -> None:
    candidates = [
        {
            "symbol": "005930",
            "shadow_forward_base": {
                "available": True,
                "baseline_epoch": 1780876980,
                "baseline_price": 298500,
                "baseline_raw_ts": "20260608090300",
            },
        }
    ]
    minute_rows = {
        "005930": [
            {"ts": 1780876980, "close": 298500, "high": 299000, "low": 298000, "raw_ts": "20260608090300"},
            {"ts": 1780877280, "close": 299500, "high": 300000, "low": 298500, "raw_ts": "20260608090800"},
        ]
    }

    out = attach_forward_outcomes(candidates, minute_rows_by_symbol=minute_rows)
    checkpoint = out[0]["shadow_forward_outcome"]["checkpoints"]["+5m"]

    assert out[0]["shadow_forward_outcome"]["available"] is True
    assert checkpoint["status"] == "observed"
    assert checkpoint["observed_ts"] == "20260608090800"


def test_attach_forward_outcomes_adds_eod_checkpoint() -> None:
    candidates = [{
        "symbol": "005930",
        "shadow_forward_base": {
            "available": True,
            "baseline_epoch": 1782172800,
            "baseline_price": 100.0,
            "baseline_raw_ts": "20260623090000",
        },
    }]
    minute_rows = {
        "005930": [
            {"ts": 1782172800, "close": 100.0, "high": 100.0, "low": 100.0, "raw_ts": "20260623090000"},
            {"ts": 1782195600, "close": 102.0, "high": 103.0, "low": 99.0, "raw_ts": "20260623152000"},
        ]
    }

    out = attach_forward_outcomes(candidates, minute_rows_by_symbol=minute_rows)
    eod = out[0]["shadow_forward_outcome"]["checkpoints"]["EOD"]

    assert eod["status"] == "observed"
    assert eod["return_pct"] == 2.0
