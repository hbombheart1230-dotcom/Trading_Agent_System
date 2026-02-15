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
    state["intents"] = intents
    state["monitor"] = {
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
    }
    return state
