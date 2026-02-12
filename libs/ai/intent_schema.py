from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

ALLOWED_ACTIONS = {"BUY", "SELL", "NOOP"}

def _to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default

def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def normalize_action(intent: Dict[str, Any]) -> str:
    raw = intent.get("action") or intent.get("intent") or intent.get("type") or "NOOP"
    act = str(raw).upper().strip()
    if act not in ALLOWED_ACTIONS:
        # map common variants
        if act in ("HOLD", "WAIT", "NONE"):
            act = "NOOP"
        elif act in ("BUY_LIMIT", "BUY_MARKET"):
            act = "BUY"
        elif act in ("SELL_LIMIT", "SELL_MARKET"):
            act = "SELL"
        else:
            act = "NOOP"
    return act

def normalize_intent(intent: Dict[str, Any], *, default_symbol: Optional[str] = None, default_price: Any = None) -> Tuple[Dict[str, Any], str]:
    """Normalize strategist/rule intent to the project's canonical shape.

    Returns (normalized_intent, rationale).
    """
    intent = dict(intent or {})
    action = normalize_action(intent)

    symbol = intent.get("symbol") or intent.get("code") or default_symbol
    symbol = str(symbol) if symbol is not None else None

    qty = intent.get("qty") or intent.get("quantity") or 0
    qty_i = max(_to_int(qty, 0), 0)

    price = intent.get("price")
    if price is None:
        price = default_price
    price_f = _to_float(price, 0.0) if price is not None else None

    order_type = (intent.get("order_type") or intent.get("type") or "limit")
    order_type = str(order_type).lower().strip() if order_type is not None else "limit"
    if order_type not in ("limit", "market"):
        order_type = "limit"

    order_api_id = intent.get("order_api_id") or intent.get("api_id") or intent.get("orderApiId") or "ORDER_SUBMIT"

    rationale = intent.get("rationale") or intent.get("reason") or ""

    # Canonical
    out: Dict[str, Any] = {
        "action": action,
        "symbol": symbol,
        "qty": qty_i if action in ("BUY", "SELL") else 0,
        "price": price_f if action in ("BUY", "SELL") else None,
        "order_type": order_type,
        "order_api_id": order_api_id,
        "rationale": str(rationale or ""),
    }

    # Minimal validity rules
    if action in ("BUY", "SELL"):
        if not symbol or qty_i <= 0:
            out["action"] = "NOOP"
            out["reason"] = "invalid_intent_missing_symbol_or_qty"
        # allow market orders without price
        if out["order_type"] == "limit" and (out["price"] is None or out["price"] <= 0):
            out["action"] = "NOOP"
            out["reason"] = "invalid_intent_missing_price_for_limit"
    return out, out.get("rationale", "")
