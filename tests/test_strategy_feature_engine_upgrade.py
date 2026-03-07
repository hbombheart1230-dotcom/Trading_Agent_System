from __future__ import annotations

from libs.runtime.feature_engine import build_feature_map, build_feature_row
from libs.runtime.regime import classify_regime_v2


def _candles(px0: float, drift: float, n: int = 160) -> list[dict]:
    rows: list[dict] = []
    px = float(px0)
    for i in range(n):
        op = px
        cl = max(1.0, op + drift)
        hi = max(op, cl) + 0.4
        lo = min(op, cl) - 0.4
        rows.append(
            {
                "open": op,
                "high": hi,
                "low": lo,
                "close": cl,
                "volume": 1000 + i,
            }
        )
        px = cl
    return rows


def test_feature_engine_upgrade_adds_extended_feature_fields():
    row = build_feature_row(_candles(100.0, 0.5))
    assert "ma60" in row
    assert "ma120" in row
    assert "ma60_gap" in row
    assert "ma120_gap" in row
    assert "adx14" in row
    assert "trend_strength" in row
    assert "gap_pct" in row
    assert "vwap_distance" in row
    assert "rolling_drawdown20" in row
    assert "realized_volatility" in row
    assert "return20" in row
    assert "regime_score" in row
    assert "regime_factors" in row


def test_feature_engine_upgrade_build_feature_map_adds_cross_section_fields():
    out = build_feature_map(
        {
            "AAA": _candles(100.0, 0.6),
            "BBB": _candles(200.0, -0.4),
        }
    )
    assert set(out.keys()) == {"AAA", "BBB"}
    assert "cross_section_rank_signal" in out["AAA"]
    assert "cross_section_rank" in out["AAA"]
    assert "cross_section_rank_signal" in out["BBB"]
    assert "cross_section_rank" in out["BBB"]
    assert "market_breadth" in out["AAA"]
    assert "relative_strength20" in out["AAA"]
    assert "sector_relative_strength" in out["AAA"]


def test_regime_v2_uses_realized_vol_context_for_high_vol():
    obj = classify_regime_v2(
        ma20_gap=0.02,
        volatility20=0.01,
        realized_vol=0.05,
        global_sentiment=0.2,
        market_breadth=0.7,
        trend_gap_threshold=0.01,
        high_vol_threshold=0.03,
    )
    assert obj["regime"] == "high_volatility"
    assert "factors" in obj


def test_regime_v2_accepts_realized_volatility_alias():
    obj = classify_regime_v2(
        ma20_gap=0.015,
        volatility20=0.01,
        realized_volatility=0.04,
        global_sentiment=0.1,
        market_breadth=0.6,
        trend_gap_threshold=0.01,
        high_vol_threshold=0.03,
    )
    assert obj["regime"] == "high_volatility"
    assert obj["factors"]["realized_volatility"] == 0.04
