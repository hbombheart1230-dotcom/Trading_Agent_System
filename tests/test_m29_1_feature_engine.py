from __future__ import annotations

from libs.runtime.feature_engine import build_feature_map, build_feature_row


def _trend_up_candles(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    px = 100.0
    for i in range(n):
        op = px
        cl = px + 1.0
        hi = max(op, cl) + 0.5
        lo = min(op, cl) - 0.5
        rows.append(
            {
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "volume": 1000 + i * 5,
            }
        )
        px = cl
    return rows


def _high_vol_candles(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    px = 100.0
    for i in range(n):
        jump = 6.0 if i % 2 == 0 else -5.5
        op = px
        cl = max(1.0, px + jump)
        hi = max(op, cl) + 2.0
        lo = min(op, cl) - 2.0
        rows.append(
            {
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "volume": 1200 + (i % 3) * 10,
            }
        )
        px = cl
    return rows


def test_m29_1_feature_row_trend_signal_is_positive():
    row = build_feature_row(_trend_up_candles())
    assert row["rsi14"] is not None
    assert row["ma20_gap"] is not None
    assert float(row["ma20_gap"]) > 0.0
    assert row["regime"] == "trend"
    assert abs(float(row["signal_score"])) > 0.0


def test_m29_1_feature_row_high_volatility_regime():
    row = build_feature_row(_high_vol_candles(), high_vol_threshold=0.02)
    assert row["volatility20"] is not None
    assert float(row["volatility20"]) > 0.0
    assert row["regime"] == "high_volatility"


def test_m29_1_build_feature_map_from_symbol_series():
    out = build_feature_map({"AAA": _trend_up_candles(), "BBB": _high_vol_candles()})
    assert "AAA" in out
    assert "BBB" in out
    assert "signal_score" in out["AAA"]
    assert "regime" in out["BBB"]
