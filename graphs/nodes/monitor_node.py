from __future__ import annotations

from typing import Any, Dict


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

    state["intents"] = intents
    state["monitor"] = {
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
    }
    return state
