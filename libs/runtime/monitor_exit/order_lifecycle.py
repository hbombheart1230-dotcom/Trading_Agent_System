from __future__ import annotations

from typing import Any, Dict


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def derive_order_lifecycle(order_status: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(order_status, dict):
        return None

    status = normalize_status(order_status.get("status"))
    filled_qty = max(0, _to_int(order_status.get("filled_qty")))
    order_qty = max(0, _to_int(order_status.get("order_qty")))
    remaining_raw = order_status.get("remaining_qty")
    if remaining_raw in (None, ""):
        remaining_raw = order_status.get("ord_remnq")
    if remaining_raw in (None, ""):
        remaining_raw = order_status.get("rmnd_qty")
    remaining_qty = None if remaining_raw in (None, "") else max(0, _to_int(remaining_raw))

    if order_qty > 0:
        progress = min(1.0, float(filled_qty) / float(order_qty))
    else:
        progress = 0.0

    cancelled_keys = ("CANCEL", "CANCELED", "CANCELLED")
    rejected_keys = ("REJECT", "DENY", "BLOCK")
    filled_keys = ("FILLED", "DONE")
    partial_keys = ("PARTIAL", "WORKING_PARTIAL")

    stage = "working"
    terminal = False

    if any(key in status for key in cancelled_keys):
        stage = "cancelled"
        terminal = True
    elif any(key in status for key in rejected_keys):
        stage = "rejected"
        terminal = True
    elif remaining_qty is not None and remaining_qty > 0 and filled_qty <= 0:
        stage = "pending_unfilled"
        terminal = False
        progress = 0.0
    elif remaining_qty is not None and remaining_qty > 0 and filled_qty > 0:
        stage = "partial_fill"
        terminal = False
    elif (order_qty > 0 and filled_qty >= order_qty) or any(key in status for key in filled_keys):
        stage = "filled"
        terminal = True
        progress = 1.0
    elif (filled_qty > 0 and order_qty > 0 and filled_qty < order_qty) or any(key in status for key in partial_keys):
        stage = "partial_fill"
        terminal = False
    elif not status:
        stage = "unknown"
        terminal = False

    return {
        "ord_no": order_status.get("ord_no"),
        "symbol": order_status.get("symbol"),
        "status_raw": order_status.get("status"),
        "stage": stage,
        "terminal": terminal,
        "filled_qty": filled_qty,
        "order_qty": order_qty,
        "remaining_qty": remaining_qty,
        "progress": float(progress),
    }
