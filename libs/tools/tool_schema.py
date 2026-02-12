from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from libs.core.event_logger import new_run_id
from libs.core.settings import Settings
from libs.skills.runner import CompositeSkillRunner
from libs.supervisor.two_phase import TwoPhaseSupervisor


class ToolFacade:
    """Single entry point for LLM tool-calls.

    The LLM should only see *meaningful* operations (Composite Skills),
    not raw api_id/path/headers.

    This facade wires:
      - CompositeSkillRunner (read/write skills)
      - TwoPhaseSupervisor (order intents)
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or Settings.from_env()
        self.runner = CompositeSkillRunner(settings=self.s)
        self.supervisor = TwoPhaseSupervisor(settings=self.s)

    # ---------- Market ----------
    def market_quote(self, *, symbol: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        rid = run_id or new_run_id()
        out = self.runner.run(run_id=rid, skill="market.quote", args={"symbol": symbol})
        return {"run_id": rid, "result": _dump(out)}

    # ---------- Orders (2-phase) ----------
    def order_place_intent(self, *, side: str, symbol: str, qty: int, order_type: str = "market", price: Any = None) -> Dict[str, Any]:
        decision = self.supervisor.create_intent({
            "action": "BUY" if side.lower() == "buy" else "SELL",
            "symbol": symbol,
            "qty": qty,
            "order_type": order_type,
            "price": price,
        })
        return {"decision": asdict(decision)}

    def order_execute(self, *, intent: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute an approved intent.
        Caller (human/supervisor agent) must ensure approval. We still run risk gate in TwoPhaseSupervisor at creation.
        """
        rid = run_id or new_run_id()
        side = "buy" if str(intent.get("action","BUY")).upper() == "BUY" else "sell"
        args = {
            "side": side,
            "symbol": intent.get("symbol"),
            "qty": int(intent.get("qty") or 0),
            "price": "" if intent.get("order_type") == "market" else intent.get("price") or "",
            "trde_tp": "3" if intent.get("order_type") == "market" else "0",
        }
        out = self.runner.run(run_id=rid, skill="order.place", args=args)
        return {"run_id": rid, "result": _dump(out)}

    def order_status(self, *, ord_no: str, symbol: str, ord_dt: str, qry_tp: str = "3", run_id: Optional[str] = None) -> Dict[str, Any]:
        rid = run_id or new_run_id()
        out = self.runner.run(run_id=rid, skill="order.status", args={"ord_no": ord_no, "symbol": symbol, "ord_dt": ord_dt, "qry_tp": qry_tp})
        return {"run_id": rid, "result": _dump(out)}


def _dump(obj: Any) -> Any:
    try:
        from dataclasses import asdict as _asdict
        return _asdict(obj)
    except Exception:
        return obj
