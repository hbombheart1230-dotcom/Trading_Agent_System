from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _norm_symbol(v: Any) -> str:
    s = str(v or "").strip()
    if s.startswith("A") and len(s) > 1 and s[1:].isdigit():
        return s[1:]
    return s


def _get_skill_root(state: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("skill_results", "skill_data", "skills"):
        v = state.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _pick_skill_value(state: Dict[str, Any], keys: Tuple[str, ...], *, state_key: str | None = None) -> Tuple[Any, bool]:
    root = _get_skill_root(state)
    for k in keys:
        if k in root:
            return root.get(k), True
    if state_key and state_key in state:
        return state.get(state_key), True
    return None, False


def _unwrap_skill_payload(raw: Any, *, skill_name: str) -> Tuple[Any, List[str]]:
    errors: List[str] = []
    if raw is None:
        return None, errors

    if isinstance(raw, dict):
        action = str(raw.get("action") or "").strip().lower()
        if action in ("error", "ask"):
            meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
            error_type = str(
                meta.get("error_type")
                or raw.get("error_type")
                or raw.get("reason")
                or raw.get("question")
                or "skill_not_ready"
            )
            errors.append(f"{skill_name}:{action}:{error_type}")
            return None, errors

        if raw.get("ok") is False:
            error_type = str(raw.get("error_type") or raw.get("reason") or "skill_error")
            errors.append(f"{skill_name}:error:{error_type}")
            return None, errors

        if isinstance(raw.get("result"), dict):
            result = raw.get("result") or {}
            result_action = str(result.get("action") or "").strip().lower()
            if result_action in ("error", "ask"):
                meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
                error_type = str(
                    meta.get("error_type")
                    or result.get("error_type")
                    or result.get("reason")
                    or result.get("question")
                    or "skill_not_ready"
                )
                errors.append(f"{skill_name}:{result_action}:{error_type}")
                return None, errors
            if "data" in result:
                return result.get("data"), errors

        if "data" in raw:
            return raw.get("data"), errors

    return raw, errors


def _extract_order_status_summary(state: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    raw, present = _pick_skill_value(state, ("order.status", "order_status"), state_key="order_status")
    unwrapped, errors = _unwrap_skill_payload(raw, skill_name="order.status")
    if not isinstance(unwrapped, dict):
        if present and not errors:
            errors.append("order.status:invalid_shape")
        return None, {"present": bool(present), "errors": errors, "used": False}

    row = dict(unwrapped)
    if isinstance(row.get("result"), dict):
        data = row.get("result", {}).get("data")
        if isinstance(data, dict):
            row = dict(data)

    symbol = _norm_symbol(row.get("symbol") or row.get("stk_cd"))
    summary = {
        "ord_no": row.get("ord_no"),
        "symbol": symbol or None,
        "status": row.get("status") or row.get("acpt_tp"),
        "filled_qty": row.get("filled_qty") or row.get("cntr_qty"),
        "order_qty": row.get("order_qty") or row.get("ord_qty"),
        "filled_price": row.get("filled_price") or row.get("cntr_uv"),
        "order_price": row.get("order_price") or row.get("ord_uv"),
    }
    return summary, {"present": bool(present), "errors": errors, "used": True}


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

    order_status, order_status_meta = _extract_order_status_summary(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    fallback_reasons = list(order_status_meta.get("errors") or [])

    state["intents"] = intents
    state["monitor"] = {
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
