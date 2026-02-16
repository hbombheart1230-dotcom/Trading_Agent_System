from __future__ import annotations

from typing import Any, Dict

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_order_status,
)


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _normalize_status(v: Any) -> str:
    return str(v or "").strip().upper()


def _derive_order_lifecycle(order_status: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(order_status, dict):
        return None

    status = _normalize_status(order_status.get("status"))
    filled_qty = max(0, _to_int(order_status.get("filled_qty")))
    order_qty = max(0, _to_int(order_status.get("order_qty")))

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

    if any(k in status for k in cancelled_keys):
        stage = "cancelled"
        terminal = True
    elif any(k in status for k in rejected_keys):
        stage = "rejected"
        terminal = True
    elif (order_qty > 0 and filled_qty >= order_qty) or any(k in status for k in filled_keys):
        stage = "filled"
        terminal = True
        progress = 1.0
    elif (filled_qty > 0 and order_qty > 0 and filled_qty < order_qty) or any(k in status for k in partial_keys):
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
        "progress": float(progress),
    }


def monitor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Monitor.

    Responsibility:
      - emit at most one intent from selected candidate
      - attach optional order status/lifecycle observation from skill DTOs
    """
    selected = state.get("selected")
    plan = state.get("plan") or {}

    intents = []
    if isinstance(selected, dict) and selected.get("symbol"):
        symbol = str(selected.get("symbol"))
        intent = {
            "symbol": symbol,
            "side": "BUY",
            "qty": 1,
            "thesis": str(plan.get("thesis") or ""),
            "meta": {
                "score": selected.get("score"),
                "risk_score": selected.get("risk_score"),
                "confidence": selected.get("confidence"),
            },
        }
        intents = [intent]

    order_status, order_status_meta = extract_order_status(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    fallback_reasons = list(order_status_meta.get("errors") or [])

    state["intents"] = intents
    state["monitor"] = {
        "skill_contract_version": SKILL_CONTRACT_VERSION,
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
        "order_status_present": bool(order_status_meta.get("present")),
        "order_status_fallback": bool(fallback_reasons),
        "order_status_fallback_reasons": fallback_reasons,
        "order_status_error_count": len(fallback_reasons),
        "order_lifecycle_loaded": bool(order_lifecycle),
        "order_lifecycle": order_lifecycle,
    }
    return state
