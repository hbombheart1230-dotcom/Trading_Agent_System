from __future__ import annotations

from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp_non_negative(v: float) -> float:
    return float(v) if v > 0.0 else 0.0


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return bool(default)
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def evaluate_exit_policy(
    *,
    price: Optional[float],
    avg_price: Optional[float],
    qty: int,
    hold_sec: Optional[int] = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate stop-loss / take-profit exit policy for one position.

    Returns a deterministic decision payload. It never raises.
    """
    p = dict(policy or {})
    out: Dict[str, Any] = {
        "evaluated": True,
        "triggered": False,
        "reason": "",
        "pnl_ratio": None,
        "thresholds": {
            "stop_loss_pct": _clamp_non_negative(_to_float(p.get("stop_loss_pct"), 0.03)),
            "take_profit_pct": _clamp_non_negative(_to_float(p.get("take_profit_pct"), 0.05)),
            "max_hold_sec": max(0, int(_to_float(p.get("max_hold_sec"), 0))),
            "trailing_stop_pct": _clamp_non_negative(_to_float(p.get("trailing_stop_pct"), 0.0)),
            "vol_expansion_ratio": _clamp_non_negative(_to_float(p.get("vol_expansion_ratio"), 0.0)),
            "eod_flat_cutoff_min": max(0, int(_to_float(p.get("eod_flat_cutoff_min"), 10))),
        },
    }

    q = max(0, int(qty or 0))
    if q <= 0:
        out["reason"] = "no_position"
        return out

    emergency_halt = _to_bool(p.get("emergency_halt"), False)
    if emergency_halt:
        out["triggered"] = True
        out["reason"] = "emergency_halt"
        return out

    use_eod_flat = _to_bool(p.get("use_eod_flat"), False)
    minutes_to_close = _to_float(p.get("minutes_to_close"), -1.0)
    eod_cutoff = int(out["thresholds"]["eod_flat_cutoff_min"])
    if use_eod_flat and minutes_to_close >= 0.0 and minutes_to_close <= float(eod_cutoff):
        out["triggered"] = True
        out["reason"] = "eod_flat"
        out["minutes_to_close"] = float(minutes_to_close)
        return out

    max_hold_sec = int(out["thresholds"]["max_hold_sec"])
    hs = None if hold_sec is None else max(0, int(hold_sec))
    out["hold_sec"] = hs
    if max_hold_sec > 0 and hs is not None and hs >= max_hold_sec:
        out["triggered"] = True
        out["reason"] = "max_hold"
        return out

    px = _to_float(price, 0.0) if price is not None else 0.0
    apx = _to_float(avg_price, 0.0) if avg_price is not None else 0.0
    if px <= 0.0 or apx <= 0.0:
        out["reason"] = "price_unavailable"
        return out

    # Volatility expansion stop (optional).
    vol_ratio_th = float(out["thresholds"]["vol_expansion_ratio"])
    if vol_ratio_th > 0.0:
        current_vol = _to_float(p.get("current_volatility"), 0.0)
        baseline_vol = _to_float(p.get("baseline_volatility"), 0.0)
        if baseline_vol > 0.0 and current_vol > 0.0:
            vol_ratio = float(current_vol / baseline_vol)
            out["volatility_ratio"] = vol_ratio
            if vol_ratio >= vol_ratio_th:
                out["triggered"] = True
                out["reason"] = "volatility_expansion"
                return out

    pnl_ratio = float((px / apx) - 1.0)
    out["pnl_ratio"] = pnl_ratio

    sl = float(out["thresholds"]["stop_loss_pct"])
    tp = float(out["thresholds"]["take_profit_pct"])

    if sl > 0.0 and pnl_ratio <= -sl:
        out["triggered"] = True
        out["reason"] = "stop_loss"
        return out

    if tp > 0.0 and pnl_ratio >= tp:
        out["triggered"] = True
        out["reason"] = "take_profit"
        return out

    # Trailing stop (optional).
    trail = float(out["thresholds"]["trailing_stop_pct"])
    if trail > 0.0:
        peak_price = _to_float(p.get("peak_price"), 0.0)
        if peak_price <= 0.0:
            peak_price = max(apx, px)
        if peak_price > 0.0:
            drawdown = float((px / peak_price) - 1.0)
            out["trailing_drawdown"] = drawdown
            if drawdown <= -trail:
                out["triggered"] = True
                out["reason"] = "trailing_stop"
                return out

    out["reason"] = "hold"
    return out
