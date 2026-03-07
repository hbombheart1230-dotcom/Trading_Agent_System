from __future__ import annotations

from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def classify_regime_v2(
    *,
    ma20_gap: Optional[float],
    volatility20: Optional[float],
    index_trend: Optional[float] = None,
    realized_vol: Optional[float] = None,
    global_sentiment: Optional[float] = None,
    market_breadth: Optional[float] = None,
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
) -> Dict[str, Any]:
    """Classify market regime with multi-factor context.

    Returns:
      {
        "regime": "trend" | "range" | "high_volatility",
        "score": float,
        "factors": {...}
      }
    """
    gap = _to_float(ma20_gap, 0.0)
    vol_local = _to_float(volatility20, 0.0)
    vol_ctx = _to_float(realized_vol, vol_local)
    vol = max(vol_local, vol_ctx)
    idx = _to_float(index_trend, gap)
    gs = _to_float(global_sentiment, 0.0)
    breadth = _to_float(market_breadth, 0.5)

    factors = {
        "ma20_gap": float(gap),
        "volatility20": float(vol_local),
        "realized_vol": float(vol_ctx),
        "index_trend": float(idx),
        "global_sentiment": float(gs),
        "market_breadth": float(breadth),
    }

    if vol >= float(high_vol_threshold):
        return {"regime": "high_volatility", "score": float(vol), "factors": factors}

    trend_score = (
        0.50 * gap
        + 0.25 * idx
        + 0.15 * gs
        + 0.10 * ((breadth - 0.5) * 2.0)
    )
    if abs(trend_score) >= float(trend_gap_threshold):
        return {"regime": "trend", "score": float(trend_score), "factors": factors}
    return {"regime": "range", "score": float(trend_score), "factors": factors}
