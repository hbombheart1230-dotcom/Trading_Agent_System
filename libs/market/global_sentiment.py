"""Global sentiment computation.

- Priority:
  1) state['mock_global_sentiment'] if provided
  2) DRY_RUN => 0.0
  3) LIVE best-effort via yfinance (optional dependency)
     - If yfinance is missing or any error occurs => 0.0

Output is a float clamped to [-1.0, +1.0].
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


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
    dxy_ret: float
    tnx_delta: float  # change in 10Y yield (percentage points-ish)


def _compute_raw(inputs: SentimentInputs, w_sp: float, w_nq: float, w_dxy: float, w_tnx: float) -> float:
    # Risk-on: equities up, DXY down, yields down
    # - DXY up => risk-off => subtract
    # - TNX up => tighter => subtract
    return (
        w_sp * inputs.sp500_ret
        + w_nq * inputs.nasdaq_ret
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
    tick_dxy = str(policy.get("sentiment_ticker_dxy") or "DX-Y.NYB")
    tick_tnx = str(policy.get("sentiment_ticker_tnx") or "^TNX")

    sp = _fetch_last2_closes_yfinance(tick_sp)
    nq = _fetch_last2_closes_yfinance(tick_nq)
    dxy = _fetch_last2_closes_yfinance(tick_dxy)
    tnx = _fetch_last2_closes_yfinance(tick_tnx)

    if not (sp and nq and dxy and tnx):
        return None

    sp_ret = (sp[1] / sp[0]) - 1.0 if sp[0] != 0 else 0.0
    nq_ret = (nq[1] / nq[0]) - 1.0 if nq[0] != 0 else 0.0
    dxy_ret = (dxy[1] / dxy[0]) - 1.0 if dxy[0] != 0 else 0.0

    # ^TNX is typically 10Y yield * 10 (e.g., 45 => 4.5%).
    # Convert delta to "percentage points" approx: delta / 10.
    tnx_delta = (tnx[1] - tnx[0]) / 10.0

    return SentimentInputs(
        sp500_ret=sp_ret,
        nasdaq_ret=nq_ret,
        dxy_ret=dxy_ret,
        tnx_delta=tnx_delta,
    )


def compute_global_sentiment(state: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> float:
    """Compute global sentiment in [-1, 1].

    Policy knobs (all optional):
    - sentiment_weights: dict with keys {sp500, nasdaq, dxy, tnx}
      defaults: 0.4, 0.4, 0.1, 0.1
    - sentiment_norm: dict with key {scale} for tanh scale (default 5.0)
    - sentiment_ticker_sp500 / nasdaq / dxy / tnx: override tickers
    """
    policy = dict(policy or {})

    # 1) explicit mock (tests)
    if state.get("mock_global_sentiment") is not None:
        try:
            return _clamp(float(state["mock_global_sentiment"]))
        except Exception:
            return 0.0

    # 2) DRY_RUN => no network
    if _is_dry_run():
        return 0.0

    weights = dict(policy.get("sentiment_weights") or {})
    w_sp = float(weights.get("sp500", 0.4))
    w_nq = float(weights.get("nasdaq", 0.4))
    w_dxy = float(weights.get("dxy", 0.1))
    w_tnx = float(weights.get("tnx", 0.1))

    norm = dict(policy.get("sentiment_norm") or {})
    scale = float(norm.get("scale", 5.0))

    inputs = _fetch_inputs(policy)
    if inputs is None:
        return 0.0

    raw = _compute_raw(inputs, w_sp=w_sp, w_nq=w_nq, w_dxy=w_dxy, w_tnx=w_tnx)

    # Normalize: tanh
    return _tanh_norm(raw, scale=scale)


# Backward/alias (in case older code imports these names)
get_global_sentiment = compute_global_sentiment
