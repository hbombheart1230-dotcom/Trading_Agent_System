from __future__ import annotations

from typing import Any, Dict


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


def _extract_order_status_summary(state: Dict[str, Any]) -> Dict[str, Any] | None:
    root = _get_skill_root(state)
    raw = root.get("order.status")
    if raw is None:
        raw = root.get("order_status")
    if raw is None:
        raw = state.get("order_status")
    if not isinstance(raw, dict):
        return None

    row = dict(raw)
    if isinstance(row.get("result"), dict):
        data = row.get("result", {}).get("data")
        if isinstance(data, dict):
            row = dict(data)

    symbol = _norm_symbol(row.get("symbol") or row.get("stk_cd"))
    return {
        "ord_no": row.get("ord_no"),
        "symbol": symbol or None,
        "status": row.get("status") or row.get("acpt_tp"),
        "filled_qty": row.get("filled_qty") or row.get("cntr_qty"),
        "order_qty": row.get("order_qty") or row.get("ord_qty"),
        "filled_price": row.get("filled_price") or row.get("cntr_uv"),
        "order_price": row.get("order_price") or row.get("ord_uv"),
    }


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

    cancelled_keys = ("CANCEL", "CANCELED", "CANCELLED", "취소")
    rejected_keys = ("REJECT", "DENY", "거부", "실패")
    filled_keys = ("FILLED", "DONE", "체결완료", "체결")
    partial_keys = ("PARTIAL", "부분", "체결중")

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

    책임: **OrderIntent만 생성**.
    - 후보 평가/계산/선정은 Scanner에서 끝낸다.
    - Monitor는 selected 1개를 바탕으로 intent draft를 만든다.

    Writes:
      - state['intents'] : list[dict] (0 또는 1개)
      - state['monitor'] : dict (관측용)
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

    order_status = _extract_order_status_summary(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    state["intents"] = intents
    state["monitor"] = {
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
        "order_lifecycle_loaded": bool(order_lifecycle),
        "order_lifecycle": order_lifecycle,
    }
    return state
