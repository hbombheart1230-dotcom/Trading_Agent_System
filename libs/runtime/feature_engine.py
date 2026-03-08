from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List, Mapping, Optional

from libs.runtime.regime import classify_regime_v2


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


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    arr = sorted(float(x) for x in values)
    n = len(arr)
    mid = n // 2
    if n % 2 == 1:
        return float(arr[mid])
    return float((arr[mid - 1] + arr[mid]) / 2.0)


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


def _pct_change(closes: List[float], period: int) -> Optional[float]:
    p = max(1, int(period))
    if len(closes) < p + 1:
        return None
    prev = float(closes[-(p + 1)])
    cur = float(closes[-1])
    if prev == 0.0:
        return None
    return float((cur / prev) - 1.0)


def _adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    p = max(2, int(period))
    if len(highs) < p + 1 or len(lows) < p + 1 or len(closes) < p + 1:
        return None

    trs: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for i in range(1, len(closes)):
        up = float(highs[i] - highs[i - 1])
        down = float(lows[i - 1] - lows[i])
        pdm = up if (up > down and up > 0.0) else 0.0
        mdm = down if (down > up and down > 0.0) else 0.0
        tr = max(
            float(highs[i] - lows[i]),
            abs(float(highs[i] - closes[i - 1])),
            abs(float(lows[i] - closes[i - 1])),
        )
        plus_dm.append(float(pdm))
        minus_dm.append(float(mdm))
        trs.append(float(tr))

    # Use simple average over last period for deterministic behavior.
    tr_n = sum(trs[-p:]) / float(p) if trs else 0.0
    pdm_n = sum(plus_dm[-p:]) / float(p) if plus_dm else 0.0
    mdm_n = sum(minus_dm[-p:]) / float(p) if minus_dm else 0.0
    if tr_n <= 0.0:
        return 0.0
    pdi = (pdm_n / tr_n) * 100.0
    mdi = (mdm_n / tr_n) * 100.0
    den = pdi + mdi
    if den <= 0.0:
        return 0.0
    dx = abs(pdi - mdi) / den * 100.0
    return float(dx)


def _gap_pct(candles: List[Mapping[str, Any]]) -> Optional[float]:
    if len(candles) < 2:
        return None
    prev_close = _to_float(candles[-2].get("close"))
    cur_open = _to_float(candles[-1].get("open"))
    if prev_close is None or cur_open is None or prev_close == 0.0:
        return None
    return float((cur_open / prev_close) - 1.0)


def _vwap_distance(candles: List[Mapping[str, Any]], closes: List[float], vols: List[float]) -> Optional[float]:
    if not candles or not closes:
        return None
    last_close = float(closes[-1])
    if last_close <= 0.0:
        return None

    # If candle has explicit vwap, use the latest value.
    last = candles[-1]
    vwap_raw = _to_float(last.get("vwap"))
    if vwap_raw is not None and vwap_raw > 0.0:
        return float((last_close / float(vwap_raw)) - 1.0)

    if len(closes) != len(vols) or not vols:
        return None
    den = float(sum(v for v in vols if v > 0.0))
    if den <= 0.0:
        return None
    num = 0.0
    for i, c in enumerate(closes):
        v = float(vols[i]) if i < len(vols) else 0.0
        if v <= 0.0:
            continue
        num += float(c) * v
    if num <= 0.0:
        return None
    vwap = num / den
    if vwap <= 0.0:
        return None
    return float((last_close / vwap) - 1.0)


def _rolling_drawdown(closes: List[float], lookback: int = 20) -> Optional[float]:
    lb = max(2, int(lookback))
    if len(closes) < lb:
        return None
    window = closes[-lb:]
    peak = max(window)
    cur = float(window[-1])
    if peak <= 0.0:
        return None
    return float((cur / peak) - 1.0)


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
    global_sentiment: Optional[float] = None,
    market_breadth: Optional[float] = None,
    index_trend: Optional[float] = None,
    realized_vol: Optional[float] = None,
    realized_volatility: Optional[float] = None,
) -> Dict[str, Any]:
    closes = _series(candles, "close")
    highs = _series(candles, "high")
    lows = _series(candles, "low")
    vols = _series(candles, "volume")

    close_last = float(closes[-1]) if closes else None
    sma20 = _sma(closes, 20)
    sma60 = _sma(closes, 60)
    sma120 = _sma(closes, 120)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)
    adx14 = _adx(highs, lows, closes, 14)
    vol_ret = _pct_returns(closes, 20)
    volatility20 = _std(vol_ret)
    return20 = _pct_change(closes, 20)

    vol_avg20 = _sma(vols, 20)
    volume_spike20: Optional[float] = None
    if vols and vol_avg20 is not None and vol_avg20 > 0.0:
        volume_spike20 = float(vols[-1] / vol_avg20)

    ma20_gap: Optional[float] = None
    if close_last is not None and sma20 is not None and sma20 != 0.0:
        ma20_gap = float((close_last / sma20) - 1.0)
    ma60_gap: Optional[float] = None
    if close_last is not None and sma60 is not None and sma60 != 0.0:
        ma60_gap = float((close_last / sma60) - 1.0)
    ma120_gap: Optional[float] = None
    if close_last is not None and sma120 is not None and sma120 != 0.0:
        ma120_gap = float((close_last / sma120) - 1.0)

    gap_pct = _gap_pct(candles)
    vwap_distance = _vwap_distance(candles, closes, vols)
    rolling_drawdown20 = _rolling_drawdown(closes, 20)

    vol_ctx_input = realized_volatility if realized_volatility is not None else realized_vol
    regime_obj = classify_regime_v2(
        ma20_gap=ma20_gap,
        volatility20=volatility20,
        index_trend=index_trend if index_trend is not None else ma20_gap,
        realized_vol=vol_ctx_input if vol_ctx_input is not None else volatility20,
        global_sentiment=global_sentiment,
        market_breadth=market_breadth,
        trend_gap_threshold=trend_gap_threshold,
        high_vol_threshold=high_vol_threshold,
    )
    regime = str(regime_obj.get("regime") or "range")
    signal = _signal_score(ma20_gap=ma20_gap, rsi14=rsi14)
    # Signed trend strength in [-1, 1], derived from ADX magnitude + trend direction.
    trend_strength: Optional[float] = None
    if adx14 is not None:
        direction_ref = ma20_gap if ma20_gap is not None else index_trend
        direction_num = _to_float(direction_ref)
        direction = 1.0 if (direction_num is None or direction_num >= 0.0) else -1.0
        trend_strength = max(-1.0, min(1.0, (float(adx14) / 100.0) * direction))
    realized_vol_out = _to_float(vol_ctx_input)
    if realized_vol_out is None:
        realized_vol_out = _to_float(volatility20)

    return {
        "close_last": close_last,
        "rsi14": rsi14,
        "ma20": sma20,
        "ma60": sma60,
        "ma120": sma120,
        "ma20_gap": ma20_gap,
        "ma60_gap": ma60_gap,
        "ma120_gap": ma120_gap,
        "atr14": atr14,
        # Alias kept for strategy contracts that refer to generic ADX.
        "adx": adx14,
        "adx14": adx14,
        "trend_strength": trend_strength,
        "gap_pct": gap_pct,
        "vwap_distance": vwap_distance,
        "return20": return20,
        "rolling_drawdown20": rolling_drawdown20,
        "volume_spike20": volume_spike20,
        "volatility20": volatility20,
        "realized_volatility": realized_vol_out,
        "regime": regime,
        "regime_score": regime_obj.get("score"),
        "regime_factors": regime_obj.get("factors"),
        "signal_score": signal,
    }


def build_feature_map(
    ohlcv_by_symbol: Mapping[str, List[Mapping[str, Any]]],
    *,
    trend_gap_threshold: float = 0.01,
    high_vol_threshold: float = 0.03,
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    ctx = dict(context or {})
    gs = _to_float(ctx.get("global_sentiment")) if isinstance(ctx, dict) else None
    breadth = _to_float(ctx.get("market_breadth")) if isinstance(ctx, dict) else None
    idx_trend = _to_float(ctx.get("index_trend")) if isinstance(ctx, dict) else None
    rv = _to_float(ctx.get("realized_vol")) if isinstance(ctx, dict) else None
    if rv is None:
        rv = _to_float(ctx.get("realized_volatility")) if isinstance(ctx, dict) else None
    for k, rows in ohlcv_by_symbol.items():
        sym = str(k or "").strip()
        if not sym or not isinstance(rows, list) or not rows:
            continue
        out[sym] = build_feature_row(
            rows,
            trend_gap_threshold=trend_gap_threshold,
            high_vol_threshold=high_vol_threshold,
            global_sentiment=gs,
            market_breadth=breadth,
            index_trend=idx_trend,
            realized_vol=rv,
            realized_volatility=rv,
        )

    if not out:
        return out

    # Cross-sectional enrichments (deterministic and additive).
    signal_pairs = [
        (sym, float(out[sym].get("signal_score") or 0.0))
        for sym in out.keys()
    ]
    signal_pairs.sort(key=lambda x: x[1])
    n = len(signal_pairs)
    if n > 1:
        for i, (sym, _score) in enumerate(signal_pairs):
            out[sym]["cross_section_rank_signal"] = float(i / float(n - 1))
            out[sym]["cross_section_rank"] = float(i / float(n - 1))
    else:
        only_sym = signal_pairs[0][0]
        out[only_sym]["cross_section_rank_signal"] = 1.0
        out[only_sym]["cross_section_rank"] = 1.0

    returns = [float(v.get("return20")) for v in out.values() if v.get("return20") is not None]
    med_ret = _median(returns)
    for sym, row in out.items():
        r20 = row.get("return20")
        if r20 is None or med_ret is None:
            row["relative_strength20"] = None
            row["sector_relative_strength"] = None
        else:
            rs = float(float(r20) - float(med_ret))
            row["relative_strength20"] = rs
            row["sector_relative_strength"] = rs

    breadth_val = sum(1 for _sym, s in signal_pairs if s > 0.0) / float(len(signal_pairs))
    for row in out.values():
        row["market_breadth"] = float(breadth_val)

    # Cross-sectional volatility percentile for downstream sizing.
    vol_pairs = [
        (sym, float(out[sym].get("volatility20")))
        for sym in out.keys()
        if out[sym].get("volatility20") is not None
    ]
    vol_pairs.sort(key=lambda x: x[1])
    m = len(vol_pairs)
    if m > 1:
        for i, (sym, _vol) in enumerate(vol_pairs):
            out[sym]["volatility_percentile"] = float(i / float(m - 1))
    elif m == 1:
        out[vol_pairs[0][0]]["volatility_percentile"] = 0.5
    for sym in out.keys():
        if out[sym].get("volatility_percentile") is None:
            out[sym]["volatility_percentile"] = 0.5

    return out
