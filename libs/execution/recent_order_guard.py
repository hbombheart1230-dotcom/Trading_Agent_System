from __future__ import annotations

from typing import Any, Dict, Tuple


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def prune_expired_orders(orders: Dict[str, Any], *, now_epoch: int) -> Dict[str, Any]:
    out = dict(orders or {})
    for sym, record in list(out.items()):
        if not isinstance(record, dict) or _coerce_int(record.get("expires_epoch"), 0) <= int(now_epoch):
            out.pop(sym, None)
    return out


def evaluate_recent_buy_duplicate_guard(
    *,
    enabled: bool,
    action: str,
    symbol: str,
    record: Dict[str, Any],
    now_epoch: int,
    ttl_sec: int,
    path: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    normalized_action = str(action or "").strip().upper()
    details: Dict[str, Any] = {
        "enabled": bool(enabled),
        "action": normalized_action,
        "guard_applied": False,
    }
    if normalized_action != "BUY" or not details["enabled"]:
        return True, "", details

    details["symbol"] = str(symbol or "")
    details["guard_applied"] = True
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    expires_epoch = _coerce_int(record.get("expires_epoch"), 0)
    last_buy_epoch = _coerce_int(record.get("last_buy_epoch"), 0)
    details.update(
        {
            "path": str(path or ""),
            "now_epoch": int(now_epoch),
            "ttl_sec": int(ttl_sec),
            "last_buy_epoch": int(last_buy_epoch),
            "expires_epoch": int(expires_epoch),
            "recent_order_found": bool(record),
        }
    )
    if record and expires_epoch > 0 and now_epoch <= expires_epoch:
        details["remaining_sec"] = int(max(0, expires_epoch - now_epoch))
        details["order_id"] = str(record.get("order_id") or "")
        details["run_id"] = str(record.get("run_id") or "")
        details["pending_management_status"] = str(record.get("pending_management_status") or "recent_buy_pending")
        details["filled_qty"] = _coerce_int(record.get("filled_qty"), -1)
        details["remaining_qty"] = _coerce_int(record.get("remaining_qty"), -1)
        return False, "duplicate_buy_recent_order_exists", details
    return True, "", details


def evaluate_recent_buy_settle_sell_guard(
    *,
    enabled: bool,
    action: str,
    symbol: str,
    record: Dict[str, Any],
    order_qty: int,
    position_qty_hint: int,
    exit_reason: str,
    now_epoch: int,
    ttl_sec: int,
    path: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    normalized_action = str(action or "").strip().upper()
    details: Dict[str, Any] = {
        "enabled": bool(enabled),
        "action": normalized_action,
        "guard_applied": False,
    }
    if normalized_action != "SELL" or not details["enabled"]:
        return True, "", details

    details["symbol"] = str(symbol or "")
    details["guard_applied"] = True
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    expires_epoch = _coerce_int(record.get("expires_epoch"), 0)
    buy_qty = _coerce_int(record.get("qty"), 0)
    normalized_exit_reason = str(exit_reason or "").strip().lower()
    emergency_reasons = {"emergency_halt", "news_shock", "hard_stop", "stop_loss", "eod_flat"}
    partial_position_after_recent_buy = bool(
        record
        and expires_epoch > 0
        and now_epoch <= expires_epoch
        and buy_qty > 0
        and (
            (position_qty_hint > 0 and position_qty_hint < buy_qty)
            or (position_qty_hint <= 0 and order_qty > 0 and order_qty < buy_qty)
        )
    )
    details.update(
        {
            "path": str(path or ""),
            "now_epoch": int(now_epoch),
            "ttl_sec": int(ttl_sec),
            "last_buy_epoch": _coerce_int(record.get("last_buy_epoch"), 0),
            "expires_epoch": int(expires_epoch),
            "remaining_sec": int(max(0, expires_epoch - now_epoch)) if expires_epoch > 0 else 0,
            "recent_order_found": bool(record),
            "recent_buy_qty": int(buy_qty),
            "order_qty": int(order_qty),
            "position_qty_hint": int(position_qty_hint),
            "exit_reason": str(normalized_exit_reason),
            "partial_position_after_recent_buy": bool(partial_position_after_recent_buy),
        }
    )
    if partial_position_after_recent_buy and normalized_exit_reason not in emergency_reasons:
        return False, "sell_guard_recent_buy_fill_settle_partial_position", details
    return True, "", details


def evaluate_recent_sell_duplicate_guard(
    *,
    enabled: bool,
    action: str,
    symbol: str,
    record: Dict[str, Any],
    order_qty: int,
    now_epoch: int,
    ttl_sec: int,
    path: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    normalized_action = str(action or "").strip().upper()
    details: Dict[str, Any] = {
        "enabled": bool(enabled),
        "action": normalized_action,
        "guard_applied": False,
    }
    if normalized_action != "SELL" or not details["enabled"]:
        return True, "", details

    details["symbol"] = str(symbol or "")
    details["guard_applied"] = True
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    expires_epoch = _coerce_int(record.get("expires_epoch"), 0)
    remaining_qty_hint = _coerce_int(record.get("remaining_qty_hint"), -1)
    details.update(
        {
            "path": str(path or ""),
            "now_epoch": int(now_epoch),
            "ttl_sec": int(ttl_sec),
            "order_qty": int(order_qty),
            "remaining_qty_hint": int(remaining_qty_hint),
            "expires_epoch": int(expires_epoch),
            "recent_order_found": bool(record),
        }
    )
    if not record or expires_epoch <= 0 or now_epoch > expires_epoch:
        return True, "", details
    details["remaining_sec"] = int(max(0, expires_epoch - now_epoch))
    details["last_sell_epoch"] = _coerce_int(record.get("last_sell_epoch"), 0)
    details["last_sell_qty"] = _coerce_int(record.get("last_sell_qty"), 0)
    details["last_position_qty"] = _coerce_int(record.get("position_qty_hint"), 0)
    if remaining_qty_hint <= 0:
        return False, "duplicate_sell_recent_full_exit_exists", details
    if order_qty > 0 and order_qty > remaining_qty_hint:
        return False, "sell_qty_exceeds_recent_remaining_position", details
    return True, "", details
