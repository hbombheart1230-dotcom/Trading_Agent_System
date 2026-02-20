from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List, Mapping, Optional


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _series(candles: List[Mapping[str, Any]], key: str) -> List[float]:
    out: List[float] = []
    for row in candles:
        x = _to_float(row.get(key))
        if x is None:
            continue
        out.append(float(x))
    return out


def _sma(values: List[float], period: int) -> Optional[float]:
    p = max(1, int(period))
    if len(values) < p:
        return None
    return float(sum(values[-p:]) / float(p))


def _std(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = float(sum(values) / float(len(values)))
    var = float(sum((x - mean) ** 2 for x in values) / float(len(values)))
    return float(sqrt(var))


def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    p = max(1, int(period))
    if len(closes) < p + 1:
        return None
    diffs = [float(closes[i] - closes[i - 1]) for i in range(len(closes) - p, len(closes))]
    gains = [d for d in diffs if d > 0.0]
    losses = [-d for d in diffs if d < 0.0]
    avg_gain = float(sum(gains) / float(p)) if gains else 0.0
    avg_loss = float(sum(losses) / float(p)) if losses else 0.0
    if avg_loss <= 0.0:
        return 100.0
    rs = float(avg_gain / avg_loss)
    return float(100.0 - (100.0 / (1.0 + rs)))


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    p = max(1, int(period))
    if len(highs) < p + 1 or len(lows) < p + 1 or len(closes) < p + 1:
        return None
    trs: List[float] = []
    start = len(closes) - p
    for i in range(start, len(closes)):
        hi = float(highs[i])
        lo = float(lows[i])
        prev_close = float(closes[i - 1])
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs.append(float(tr))
    return float(sum(trs) / float(len(trs))) if trs else None


def _pct_returns(closes: List[float], period: int) -> List[float]:
    p = max(1, int(period))
    if len(closes) < p + 1:
        return []
    out: List[float] = []
    base = closes[-(p + 1) :]
    for i in range(1, len(base)):
        prev = float(base[i - 1])
        cur = float(base[i])
        if prev == 0.0:
            continue
        out.append(float((cur / prev) - 1.0))
    return out


def classify_regime(
    *,
    ma20_gap: Optional[float],
    volatility20: Optional[float],
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
) -> str:
    gap = float(ma20_gap or 0.0)
    vol = float(volatility20 or 0.0)
    if vol >= float(high_vol_threshold):
        return "high_volatility"
    if abs(gap) >= float(trend_gap_threshold):
        return "trend"
    return "range"


def _signal_score(*, ma20_gap: Optional[float], rsi14: Optional[float]) -> float:
    gap = float(ma20_gap or 0.0)
    rsi = float(rsi14 or 50.0)
    score = 0.0
    if gap > 0.0 and rsi >= 50.0 and rsi <= 70.0:
        score += 0.5
    if gap < 0.0 and rsi >= 30.0 and rsi <= 50.0:
        score -= 0.5
    if rsi >= 75.0:
        score -= 0.2
    if rsi <= 25.0:
        score += 0.2
    if score > 1.0:
        score = 1.0
    if score < -1.0:
        score = -1.0
    return float(score)


def build_feature_row(
    candles: List[Mapping[str, Any]],
    *,
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
) -> Dict[str, Any]:
    closes = _series(candles, "close")
    highs = _series(candles, "high")
    lows = _series(candles, "low")
    vols = _series(candles, "volume")

    close_last = float(closes[-1]) if closes else None
    sma20 = _sma(closes, 20)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)
    vol_ret = _pct_returns(closes, 20)
    volatility20 = _std(vol_ret)

    vol_avg20 = _sma(vols, 20)
    volume_spike20: Optional[float] = None
    if vols and vol_avg20 is not None and vol_avg20 > 0.0:
        volume_spike20 = float(vols[-1] / vol_avg20)

    ma20_gap: Optional[float] = None
    if close_last is not None and sma20 is not None and sma20 != 0.0:
        ma20_gap = float((close_last / sma20) - 1.0)

    regime = classify_regime(
        ma20_gap=ma20_gap,
        volatility20=volatility20,
        trend_gap_threshold=trend_gap_threshold,
        high_vol_threshold=high_vol_threshold,
    )
    signal = _signal_score(ma20_gap=ma20_gap, rsi14=rsi14)

    return {
        "close_last": close_last,
        "rsi14": rsi14,
        "ma20": sma20,
        "ma20_gap": ma20_gap,
        "atr14": atr14,
        "volume_spike20": volume_spike20,
        "volatility20": volatility20,
        "regime": regime,
        "signal_score": signal,
    }


def build_feature_map(
    ohlcv_by_symbol: Mapping[str, List[Mapping[str, Any]]],
    *,
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for k, rows in ohlcv_by_symbol.items():
        sym = str(k or "").strip()
        if not sym or not isinstance(rows, list) or not rows:
            continue
        out[sym] = build_feature_row(
            rows,
            trend_gap_threshold=trend_gap_threshold,
            high_vol_threshold=high_vol_threshold,
        )
    return out
