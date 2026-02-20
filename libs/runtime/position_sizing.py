from __future__ import annotations

from math import floor
from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return float(lo)
    if v > hi:
        return float(hi)
    return float(v)


def evaluate_position_size(
    *,
    price: Optional[float],
    cash: Optional[float],
    policy: Dict[str, Any] | None = None,
    risk_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return deterministic position sizing decision.

    Default-friendly behavior:
    - If inputs are missing/invalid -> qty=0 with reason.
    - Policy defaults are conservative.
    """
    p = dict(policy or {})
    rc = dict(risk_context or {})

    px = _to_float(price, 0.0) if price is not None else 0.0
    c = _to_float(cash, 0.0) if cash is not None else 0.0

    out: Dict[str, Any] = {
        "evaluated": True,
        "qty": 0,
        "reason": "",
        "price": px if px > 0.0 else None,
        "cash": c if c >= 0.0 else None,
        "mode": "risk_budget",
        "inputs": {},
    }

    if px <= 0.0:
        out["reason"] = "price_unavailable"
        return out
    if c <= 0.0:
        out["reason"] = "cash_unavailable"
        return out

    risk_per_trade_ratio = _to_float(
        p.get("risk_per_trade_ratio"),
        _to_float(rc.get("per_trade_risk_ratio"), 0.01),
    )
    risk_per_trade_ratio = _clamp(risk_per_trade_ratio, 0.0, 1.0)

    stop_loss_pct = _to_float(
        p.get("stop_loss_pct"),
        _to_float((p.get("exit_policy") or {}).get("stop_loss_pct") if isinstance(p.get("exit_policy"), dict) else 0.03, 0.03),
    )
    stop_loss_pct = _clamp(stop_loss_pct, 0.0, 1.0)

    notional_ratio = _to_float(p.get("position_notional_ratio"), 0.10)
    notional_ratio = _clamp(notional_ratio, 0.0, 1.0)

    max_qty = max(0, _to_int(p.get("max_position_qty"), 0))
    min_qty = max(1, _to_int(p.get("min_position_qty"), 1))
    lot_size = max(1, _to_int(p.get("lot_size"), 1))

    risk_budget = float(c * risk_per_trade_ratio)
    notional_budget = float(c * notional_ratio)
    if risk_budget <= 0.0 and notional_budget <= 0.0:
        out["reason"] = "budget_zero"
        out["inputs"] = {
            "risk_per_trade_ratio": risk_per_trade_ratio,
            "position_notional_ratio": notional_ratio,
        }
        return out

    if stop_loss_pct > 0.0:
        qty_risk = int(floor(risk_budget / float(px * stop_loss_pct)))
    else:
        qty_risk = int(floor(risk_budget / float(px))) if risk_budget > 0.0 else 0
    qty_notional = int(floor(notional_budget / float(px))) if notional_budget > 0.0 else 0

    candidates = [q for q in (qty_risk, qty_notional) if q > 0]
    qty = min(candidates) if candidates else 0

    if max_qty > 0 and qty > max_qty:
        qty = max_qty

    if qty > 0:
        qty = int((qty // lot_size) * lot_size)
    if qty > 0 and qty < min_qty:
        qty = 0

    out["qty"] = int(max(0, qty))
    out["inputs"] = {
        "risk_per_trade_ratio": float(risk_per_trade_ratio),
        "stop_loss_pct": float(stop_loss_pct),
        "position_notional_ratio": float(notional_ratio),
        "risk_budget": float(risk_budget),
        "notional_budget": float(notional_budget),
        "qty_by_risk": int(max(0, qty_risk)),
        "qty_by_notional": int(max(0, qty_notional)),
        "lot_size": int(lot_size),
        "min_qty": int(min_qty),
        "max_qty": int(max_qty),
    }

    if out["qty"] <= 0:
        out["reason"] = "computed_qty_zero"
    else:
        out["reason"] = "ok"
    return out

