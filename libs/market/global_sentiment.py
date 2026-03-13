"""Global sentiment computation.

- Priority:
  1) state['mock_global_sentiment'] if provided
  2) DRY_RUN => 0.0
  3) LIVE best-effort via yfinance (optional dependency)

The canonical output remains a normalized signal contract, but now includes
additive index-move evidence so Strategist can reason from:
- S&P500 daily change
- Nasdaq daily change
- Dow daily change
- VIX level / daily change
- DXY daily change
- US 10Y yield delta
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from libs.data_quality.signal_contract import (
    SIGNAL_STATUS_FALLBACK,
    SIGNAL_STATUS_OK,
    SIGNAL_STATUS_UNAVAILABLE,
    make_signal,
)


def _is_dry_run() -> bool:
    v = str(os.getenv("DRY_RUN", "")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _tanh_norm(x: float, scale: float = 5.0) -> float:
    # Smoothly map to [-1, 1]
    return _clamp(math.tanh(scale * x), -1.0, 1.0)


@dataclass(frozen=True)
class SentimentInputs:
    sp500_ret: float
    nasdaq_ret: float
    dow_ret: float
    vix_ret: float
    vix_level: float
    dxy_ret: float
    tnx_delta: float  # change in 10Y yield (percentage points-ish)


def _compute_raw(
    inputs: SentimentInputs,
    w_sp: float,
    w_nq: float,
    w_dow: float,
    w_vix: float,
    w_vix_level: float,
    w_dxy: float,
    w_tnx: float,
    vix_neutral_level: float,
) -> float:
    # Risk-on: equities up, DXY down, yields down
    # - VIX up / elevated => risk-off => subtract
    # - DXY up => risk-off => subtract
    # - TNX up => tighter => subtract
    vix_ret = float(getattr(inputs, "vix_ret", 0.0) or 0.0)
    vix_level = float(getattr(inputs, "vix_level", 0.0) or 0.0)
    neutral_vix = max(1.0, float(vix_neutral_level or 20.0))
    vix_level_pressure = max(0.0, min((vix_level - neutral_vix) / neutral_vix, 2.0))
    return (
        w_sp * inputs.sp500_ret
        + w_nq * inputs.nasdaq_ret
        + w_dow * inputs.dow_ret
        - w_vix * vix_ret
        - w_vix_level * vix_level_pressure
        - w_dxy * inputs.dxy_ret
        - w_tnx * inputs.tnx_delta
    )


def _fetch_last2_closes_yfinance(ticker: str) -> Optional[Tuple[float, float]]:
    """Return (prev_close, last_close) for ticker, or None on failure."""
    try:
        import yfinance as yf  # optional
    except Exception:
        return None

    try:
        # 5d window to be resilient to holidays; use Close series
        hist = yf.Ticker(ticker).history(period="5d", interval="1d")
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna().tolist()
        if len(closes) < 2:
            return None
        return float(closes[-2]), float(closes[-1])
    except Exception:
        return None


def _fetch_inputs(policy: Dict[str, Any]) -> Optional[SentimentInputs]:
    tick_sp = str(policy.get("sentiment_ticker_sp500") or "^GSPC")
    tick_nq = str(policy.get("sentiment_ticker_nasdaq") or "^IXIC")
    tick_dow = str(policy.get("sentiment_ticker_dow") or "^DJI")
    tick_vix = str(policy.get("sentiment_ticker_vix") or "^VIX")
    tick_dxy = str(policy.get("sentiment_ticker_dxy") or "DX-Y.NYB")
    tick_tnx = str(policy.get("sentiment_ticker_tnx") or "^TNX")

    sp = _fetch_last2_closes_yfinance(tick_sp)
    nq = _fetch_last2_closes_yfinance(tick_nq)
    dow = _fetch_last2_closes_yfinance(tick_dow)
    vix = _fetch_last2_closes_yfinance(tick_vix)
    dxy = _fetch_last2_closes_yfinance(tick_dxy)
    tnx = _fetch_last2_closes_yfinance(tick_tnx)

    if not (sp and nq and dow and dxy and tnx):
        return None

    sp_ret = (sp[1] / sp[0]) - 1.0 if sp[0] != 0 else 0.0
    nq_ret = (nq[1] / nq[0]) - 1.0 if nq[0] != 0 else 0.0
    dow_ret = (dow[1] / dow[0]) - 1.0 if dow[0] != 0 else 0.0
    vix_ret = (vix[1] / vix[0]) - 1.0 if vix and vix[0] != 0 else 0.0
    vix_level = float(vix[1]) if vix else 0.0
    dxy_ret = (dxy[1] / dxy[0]) - 1.0 if dxy[0] != 0 else 0.0

    # ^TNX is typically 10Y yield * 10 (e.g., 45 => 4.5%).
    # Convert delta to "percentage points" approx: delta / 10.
    tnx_delta = (tnx[1] - tnx[0]) / 10.0

    return SentimentInputs(
        sp500_ret=sp_ret,
        nasdaq_ret=nq_ret,
        dow_ret=dow_ret,
        vix_ret=vix_ret,
        vix_level=vix_level,
        dxy_ret=dxy_ret,
        tnx_delta=tnx_delta,
    )


def _sentiment_evidence(inputs: Optional[SentimentInputs], weights: Dict[str, float], raw: float) -> Dict[str, Any]:
    components = {
        "sp500_ret": float(inputs.sp500_ret) if inputs is not None else 0.0,
        "nasdaq_ret": float(inputs.nasdaq_ret) if inputs is not None else 0.0,
        "dow_ret": float(inputs.dow_ret) if inputs is not None else 0.0,
        "vix_ret": float(getattr(inputs, "vix_ret", 0.0) or 0.0) if inputs is not None else 0.0,
        "vix_level": float(getattr(inputs, "vix_level", 0.0) or 0.0) if inputs is not None else 0.0,
        "dxy_ret": float(inputs.dxy_ret) if inputs is not None else 0.0,
        "tnx_delta": float(inputs.tnx_delta) if inputs is not None else 0.0,
    }
    equity_avg = (components["sp500_ret"] + components["nasdaq_ret"] + components["dow_ret"]) / 3.0
    neutral_vix = max(1.0, float(weights.get("vix_neutral_level", 20.0) or 20.0))
    vix_level_pressure = max(0.0, min((components["vix_level"] - neutral_vix) / neutral_vix, 2.0))
    return {
        "weights": {
            "sp500": float(weights.get("sp500", 0.0)),
            "nasdaq": float(weights.get("nasdaq", 0.0)),
            "dow": float(weights.get("dow", 0.0)),
            "vix": float(weights.get("vix", 0.0)),
            "vix_level": float(weights.get("vix_level", 0.0)),
            "dxy": float(weights.get("dxy", 0.0)),
            "tnx": float(weights.get("tnx", 0.0)),
            "vix_neutral_level": float(weights.get("vix_neutral_level", 20.0)),
        },
        "components": dict(components),
        "index_moves": {
            "sp500_pct": float(components["sp500_ret"] * 100.0),
            "nasdaq_pct": float(components["nasdaq_ret"] * 100.0),
            "dow_pct": float(components["dow_ret"] * 100.0),
        },
        "macro_moves": {
            "vix_pct": float(components["vix_ret"] * 100.0),
            "vix_level": float(components["vix_level"]),
            "vix_level_pressure": float(vix_level_pressure),
            "dxy_pct": float(components["dxy_ret"] * 100.0),
            "tnx_delta": float(components["tnx_delta"]),
        },
        "fear_index": {
            "provider": "yfinance",
            "ticker": "^VIX",
            "level": float(components["vix_level"]),
            "change_pct": float(components["vix_ret"] * 100.0),
            "neutral_level": float(neutral_vix),
            "level_pressure": float(vix_level_pressure),
        },
        "equity_breadth": {
            "equity_index_average_pct": float(equity_avg * 100.0),
            "equity_advancing": int(sum(1 for v in (components["sp500_ret"], components["nasdaq_ret"], components["dow_ret"]) if v > 0.0)),
        },
        "raw_score": float(raw),
    }


def _signal_with_evidence(
    *,
    score: float,
    status: str,
    source: str,
    reason: str,
    ts: int,
    inputs: Optional[SentimentInputs],
    weights: Dict[str, float],
    raw_score: float,
) -> Dict[str, Any]:
    signal = make_signal(score=score, status=status, source=source, reason=reason, ts=ts)
    signal.update(_sentiment_evidence(inputs, weights, raw_score))
    return signal


def compute_global_sentiment(state: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> float:
    """Compute global sentiment in [-1, 1].

    Policy knobs (all optional):
      - sentiment_weights: dict with keys {sp500, nasdaq, dow, vix, vix_level, dxy, tnx, vix_neutral_level}
        defaults: 0.30, 0.35, 0.20, 0.10, 0.08, 0.075, 0.075, 20.0
    - sentiment_norm: dict with key {scale} for tanh scale (default 5.0)
    - sentiment_ticker_sp500 / nasdaq / dow / vix / dxy / tnx: override tickers
    """
    signal = compute_global_sentiment_signal(state=state, policy=policy)
    status = str(signal.get("status") or "").strip().lower()
    # Do not silently collapse unavailable data into neutral value.
    if status == SIGNAL_STATUS_UNAVAILABLE:
        return float("nan")
    try:
        return _clamp(float(signal.get("score", 0.0)))
    except Exception:
        return 0.0


def compute_global_sentiment_signal(state: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compute global sentiment as normalized signal contract.

    Contract:
      {
        "score": float [-1, +1],
        "status": "ok" | "fallback" | "unavailable",
        "source": str,
        "reason": str,
        "ts": int(epoch)
      }
    """
    policy = dict(policy or {})
    now = int(time.time())

    # 1) explicit mock (tests)
    if state.get("mock_global_sentiment") is not None:
        try:
            weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "vix_neutral_level": 20.0}
            return _signal_with_evidence(
                score=_clamp(float(state["mock_global_sentiment"])),
                status=SIGNAL_STATUS_OK,
                source="mock_global_sentiment",
                reason="",
                ts=now,
                inputs=None,
                weights=weights,
                raw_score=float(state["mock_global_sentiment"]),
            )
        except Exception:
            weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "vix_neutral_level": 20.0}
            return _signal_with_evidence(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="mock_global_sentiment",
                reason="invalid_mock_value",
                ts=now,
                inputs=None,
                weights=weights,
                raw_score=0.0,
            )

    # 2) DRY_RUN => no network
    if _is_dry_run():
        weights = {"sp500": 0.30, "nasdaq": 0.35, "dow": 0.20, "vix": 0.10, "vix_level": 0.08, "dxy": 0.075, "tnx": 0.075, "vix_neutral_level": 20.0}
        return _signal_with_evidence(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="dry_run_policy",
            reason="dry_run_neutral",
            ts=now,
            inputs=None,
            weights=weights,
            raw_score=0.0,
        )

    weights = dict(policy.get("sentiment_weights") or {})
    w_sp = float(weights.get("sp500", 0.30))
    w_nq = float(weights.get("nasdaq", 0.35))
    w_dow = float(weights.get("dow", 0.20))
    w_vix = float(weights.get("vix", 0.10))
    w_vix_level = float(weights.get("vix_level", 0.08))
    w_dxy = float(weights.get("dxy", 0.075))
    w_tnx = float(weights.get("tnx", 0.075))
    vix_neutral_level = float(weights.get("vix_neutral_level", 20.0))
    resolved_weights = {
        "sp500": w_sp,
        "nasdaq": w_nq,
        "dow": w_dow,
        "vix": w_vix,
        "vix_level": w_vix_level,
        "dxy": w_dxy,
        "tnx": w_tnx,
        "vix_neutral_level": vix_neutral_level,
    }

    norm = dict(policy.get("sentiment_norm") or {})
    scale = float(norm.get("scale", 5.0))

    inputs = _fetch_inputs(policy)
    if inputs is None:
        return _signal_with_evidence(
            score=0.0,
            status=SIGNAL_STATUS_UNAVAILABLE,
            source="yfinance",
            reason="fetch_failed",
            ts=now,
            inputs=None,
            weights=resolved_weights,
            raw_score=0.0,
        )

    raw = _compute_raw(
        inputs,
        w_sp=w_sp,
        w_nq=w_nq,
        w_dow=w_dow,
        w_vix=w_vix,
        w_vix_level=w_vix_level,
        w_dxy=w_dxy,
        w_tnx=w_tnx,
        vix_neutral_level=vix_neutral_level,
    )
    return _signal_with_evidence(
        score=_tanh_norm(raw, scale=scale),
        status=SIGNAL_STATUS_OK,
        source="yfinance",
        reason="",
        ts=now,
        inputs=inputs,
        weights=resolved_weights,
        raw_score=raw,
    )


# Backward/alias (in case older code imports these names)
get_global_sentiment = compute_global_sentiment
