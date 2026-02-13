from __future__ import annotations

import os
from typing import Any, Dict


def _is_dry_run() -> bool:
    v = os.getenv("DRY_RUN", "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def compute_global_sentiment(state: Dict[str, Any], policy: Dict[str, Any]) -> float:
    """Compute global sentiment in [-1.0, +1.0].

    Priority:
    1) state['mock_global_sentiment'] if present
    2) DRY_RUN => 0.0 (neutral)
    3) yfinance-based proxy (best-effort; if unavailable => 0.0)

    Note: this function must be safe in environments without yfinance/network.
    """
    if "mock_global_sentiment" in state and state["mock_global_sentiment"] is not None:
        try:
            return float(state["mock_global_sentiment"])
        except Exception:
            return 0.0

    if _is_dry_run():
        return 0.0

    # Best-effort live computation
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return 0.0

    # Policy defaults (can be tuned later)
    spx = str(policy.get("gs_ticker_spx") or "^GSPC")
    ndx = str(policy.get("gs_ticker_ndx") or "^IXIC")
    usdkrw = str(policy.get("gs_ticker_usdkrw") or "KRW=X")

    def _last_return(ticker: str) -> float:
        data = yf.download(ticker, period="5d", interval="1d", progress=False)
        if data is None or len(data) < 2:
            return 0.0
        close = data["Close"].dropna()
        if len(close) < 2:
            return 0.0
        r = float((close.iloc[-1] / close.iloc[-2]) - 1.0)
        return r

    # Simple proxy: equities up => risk-on, USDKRW up => risk-off for KR investors
    try:
        r_spx = _last_return(spx)
        r_ndx = _last_return(ndx)
        r_fx = _last_return(usdkrw)
    except Exception:
        return 0.0

    raw = (0.45 * r_spx + 0.45 * r_ndx) - (0.10 * r_fx)

    # normalize roughly: +/-2% daily move ~ +/-1 sentiment
    s = max(-1.0, min(1.0, raw / 0.02))
    return float(s)
