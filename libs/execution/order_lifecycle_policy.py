from __future__ import annotations

from typing import Any, Dict, Tuple


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def extract_fill_quantity_snapshot(execution: Dict[str, Any], order: Dict[str, Any]) -> Dict[str, Any]:
    payload = execution.get("payload") if isinstance(execution.get("payload"), dict) else {}
    response_payload = payload.get("response_payload") if isinstance(payload.get("response_payload"), dict) else {}
    broker_result = payload.get("broker_result") if isinstance(payload.get("broker_result"), dict) else {}
    containers = [
        execution,
        payload,
        response_payload,
        execution.get("order_status") if isinstance(execution.get("order_status"), dict) else {},
        payload.get("order_status") if isinstance(payload.get("order_status"), dict) else {},
        execution.get("broker_result") if isinstance(execution.get("broker_result"), dict) else {},
        broker_result,
    ]

    def first_value(*keys: str) -> Tuple[Any, str]:
        for container in containers:
            if not isinstance(container, dict):
                continue
            for key in keys:
                if container.get(key) not in (None, ""):
                    return container.get(key), key
        return None, ""

    filled_raw, filled_key = first_value("filled_qty", "cntr_qty", "exec_qty", "cnfm_qty")
    remaining_raw, remaining_key = first_value("remaining_qty", "ord_remnq", "rmnd_qty", "unfilled_qty", "unfilled")
    order_raw, order_key = first_value("order_qty", "ord_qty", "qty")
    order_qty = max(0, _coerce_int(order_raw, 0)) if order_raw not in (None, "") else max(0, _coerce_int(order.get("qty"), 0))
    filled_qty = max(0, _coerce_int(filled_raw, 0)) if filled_raw not in (None, "") else None
    remaining_qty = max(0, _coerce_int(remaining_raw, 0)) if remaining_raw not in (None, "") else None
    has_fill_truth = bool(filled_raw not in (None, "") or remaining_raw not in (None, ""))
    pending_unfilled = bool(remaining_qty is not None and remaining_qty > 0)
    fully_filled = bool(has_fill_truth and (remaining_qty == 0 or (order_qty > 0 and (filled_qty or 0) >= order_qty)))
    return {
        "has_fill_truth": bool(has_fill_truth),
        "filled_qty": filled_qty,
        "remaining_qty": remaining_qty,
        "order_qty": int(order_qty),
        "filled_qty_source": filled_key,
        "remaining_qty_source": remaining_key,
        "order_qty_source": order_key,
        "pending_unfilled": bool(pending_unfilled),
        "fully_filled": bool(fully_filled),
    }


def evaluate_unfilled_order_recovery_start(
    *,
    action: str,
    order_api_id: Any,
    execution_allowed: bool,
    execution_ok: bool,
    fill_snapshot: Dict[str, Any],
    order_id: str,
) -> Dict[str, Any]:
    normalized_action = str(action or "").strip().upper()
    result: Dict[str, Any] = {
        "action": normalized_action,
        "guard_applied": True,
        "attempted": False,
        "requires_cancel": False,
        "cancel_reason": "",
    }
    if normalized_action not in ("BUY", "SELL"):
        result["reason"] = "unsupported_action"
        return result
    if str(order_api_id or "").strip().lower() == "kt10003":
        result["reason"] = "cancel_order_not_recovered"
        return result
    if not bool(execution_allowed) or not bool(execution_ok):
        result["reason"] = "execution_not_accepted"
        return result
    if not bool(fill_snapshot.get("has_fill_truth")):
        result["reason"] = "fill_truth_missing"
        return result
    if not bool(fill_snapshot.get("pending_unfilled")):
        result["reason"] = "not_pending_unfilled"
        return result
    if not str(order_id or "").strip():
        result["reason"] = "missing_order_id"
        return result

    result.update(
        {
            "attempted": True,
            "requires_cancel": True,
            "remaining_qty": max(0, _coerce_int(fill_snapshot.get("remaining_qty"), 0)),
            "cancel_reason": (
                "buy_unfilled_auto_cancel"
                if normalized_action == "BUY"
                else "sell_unfilled_cancel_before_market_replacement"
            ),
        }
    )
    return result


def evaluate_unfilled_order_recovery_after_cancel(
    *,
    action: str,
    cancel_ok: bool,
    remaining_qty: int,
    regular_session_open: bool,
) -> Dict[str, Any]:
    normalized_action = str(action or "").strip().upper()
    if normalized_action == "BUY":
        return {
            "continue_recovery": False,
            "reason": "buy_unfilled_cancelled",
            "requires_market_replacement": False,
        }
    if not bool(cancel_ok):
        return {
            "continue_recovery": False,
            "reason": "sell_cancel_failed_no_replacement",
            "requires_market_replacement": False,
        }
    if int(remaining_qty or 0) <= 0:
        return {
            "continue_recovery": False,
            "reason": "sell_remaining_qty_missing",
            "requires_market_replacement": False,
        }
    if not bool(regular_session_open):
        return {
            "continue_recovery": False,
            "reason": "regular_session_closed_after_hours_policy_required",
            "requires_market_replacement": False,
            "after_hours_policy_required": True,
        }
    return {
        "continue_recovery": True,
        "reason": "sell_unfilled_market_replacement_required",
        "requires_market_replacement": True,
        "market_replacement_reason": "sell_unfilled_market_replacement",
    }
