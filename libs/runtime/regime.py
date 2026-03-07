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
    realized_volatility: Optional[float] = None,
    global_sentiment: Optional[float] = None,
    market_breadth: Optional[float] = None,
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
    weight_ma_gap: float = 0.50,
    weight_index_trend: float = 0.25,
    weight_global_sentiment: float = 0.15,
    weight_market_breadth: float = 0.10,
    weight_volatility_penalty: float = 0.05,
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
    vol_input = realized_volatility if realized_volatility is not None else realized_vol
    vol_ctx = _to_float(vol_input, vol_local)
    vol = max(vol_local, vol_ctx)
    idx = _to_float(index_trend, gap)
    gs = _to_float(global_sentiment, 0.0)
    breadth = _to_float(market_breadth, 0.5)
    breadth_centered = (breadth - 0.5) * 2.0
    # Volatility penalty is active only before hard high-vol cutoff.
    # 0.0 near calm market, down to -1.0 as vol approaches threshold.
    if high_vol_threshold > 0.0:
        vol_ratio = min(max(vol / float(high_vol_threshold), 0.0), 1.0)
    else:
        vol_ratio = 0.0
    volatility_penalty = -vol_ratio

    factors = {
        "ma20_gap": float(gap),
        "volatility20": float(vol_local),
        "realized_vol": float(vol_ctx),
        "realized_volatility": float(vol_ctx),
        "index_trend": float(idx),
        "global_sentiment": float(gs),
        "market_breadth": float(breadth),
        "market_breadth_centered": float(breadth_centered),
        "volatility_penalty": float(volatility_penalty),
    }

    if vol >= float(high_vol_threshold):
        return {"regime": "high_volatility", "score": float(vol), "factors": factors}

    trend_score = (
        float(weight_ma_gap) * gap
        + float(weight_index_trend) * idx
        + float(weight_global_sentiment) * gs
        + float(weight_market_breadth) * breadth_centered
        + float(weight_volatility_penalty) * volatility_penalty
    )
    if abs(trend_score) >= float(trend_gap_threshold):
        return {"regime": "trend", "score": float(trend_score), "factors": factors}
    return {"regime": "range", "score": float(trend_score), "factors": factors}
