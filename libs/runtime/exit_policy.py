from __future__ import annotations

from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp_non_negative(v: float) -> float:
    return float(v) if v > 0.0 else 0.0


def evaluate_exit_policy(
    *,
    price: Optional[float],
    avg_price: Optional[float],
    qty: int,
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
        },
    }

    q = max(0, int(qty or 0))
    if q <= 0:
        out["reason"] = "no_position"
        return out

    px = _to_float(price, 0.0) if price is not None else 0.0
    apx = _to_float(avg_price, 0.0) if avg_price is not None else 0.0
    if px <= 0.0 or apx <= 0.0:
        out["reason"] = "price_unavailable"
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

    out["reason"] = "hold"
    return out

