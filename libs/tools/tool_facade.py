from __future__ import annotations

import os
import uuid
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, List

from libs.skills.runner import CompositeSkillRunner
from libs.supervisor.two_phase import TwoPhaseSupervisor
from libs.supervisor.intent_store import IntentStore

from libs.agent.intent_parser import parse_nl
from libs.agent.router import route


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _mode() -> str:
    return (os.getenv("KIWOOM_MODE", "real") or "real").strip().lower()


def _auto_approve_enabled() -> bool:
    v = (os.getenv("AUTO_APPROVE", "false") or "false").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _unwrap_intent(row: Any) -> Optional[Dict[str, Any]]:
    """Accept either a raw intent dict or a wrapped record {ts,intent_id,intent:{...}}."""
    if not isinstance(row, dict):
        return None
    if "intent" in row and isinstance(row.get("intent"), dict):
        return row["intent"]
    return row


class ToolFacade:
    def __init__(
        self,
        *,
        catalog: str = "data/specs/api_catalog.jsonl",
        event_log: str = "data/logs/events.jsonl",
        intent_store: str = "data/logs/intents.jsonl",
    ):
        self.runner = CompositeSkillRunner(catalog_path=catalog, event_log_path=event_log)
        self.supervisor = TwoPhaseSupervisor()
        self.intent_store = IntentStore(intent_store)
        self.intent_store_path = Path(intent_store)

    # ---------- helpers ----------

    def _load_all_rows(self) -> List[Dict[str, Any]]:
        if not self.intent_store_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with self.intent_store_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows

    def _last_intent(self) -> Optional[Dict[str, Any]]:
        rows = self._load_all_rows()
        if not rows:
            return None
        return _unwrap_intent(rows[-1])

    # ---------- core tools ----------

    def market_quote(self, symbol: str) -> Dict[str, Any]:
        out = self.runner.run(run_id=_new_run_id(), skill="market.quote", args={"symbol": symbol})
        return asdict(out)

    def order_place_intent(
        self,
        *,
        side: str,
        symbol: str,
        qty: int,
        order_type: str = "market",
        price: Optional[int] = None,
        rationale: str = "",
    ) -> Dict[str, Any]:
        raw_intent = {
            "action": "BUY" if str(side).lower() == "buy" else "SELL",
            "symbol": symbol,
            "qty": int(qty),
            "order_type": order_type,
            "price": price,
            "rationale": rationale,
        }

        decision = self.supervisor.create_intent(raw_intent)
        decision_dict = asdict(decision)

        intent = decision_dict.get("intent")
        if isinstance(intent, dict):
            self.intent_store.save(intent)

        if _auto_approve_enabled() and _mode() == "mock":
            exec_res = self.order_execute(intent=intent or raw_intent)
            return {"decision": decision_dict, "execution": exec_res}

        return {"decision": decision_dict}

    def approve_intent(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        if not intent_id:
            intent = self._last_intent()
            if not intent:
                return {"ok": False, "message": "No stored intents."}
            intent_id = str(intent.get("intent_id") or "")
        else:
            loaded = self.intent_store.load(intent_id)
            intent = _unwrap_intent(loaded)

        if not intent:
            return {"ok": False, "message": f"intent_id not found: {intent_id}"}

        exec_res = self.order_execute(intent=intent)
        return {"ok": True, "intent_id": intent_id, "execution": exec_res}

    def list_intents(self, limit: int = 5) -> Dict[str, Any]:
        rows = self._load_all_rows()
        recent = rows[-limit:]
        out: List[Dict[str, Any]] = []
        for r in recent:
            intent = _unwrap_intent(r) or {}
            out.append(
                {
                    "intent_id": intent.get("intent_id") or r.get("intent_id"),
                    "action": intent.get("action"),
                    "symbol": intent.get("symbol"),
                    "qty": intent.get("qty"),
                    "order_type": intent.get("order_type"),
                    "price": intent.get("price"),
                    "created_epoch": intent.get("created_epoch"),
                    "ts": r.get("ts"),
                }
            )
        return {"ok": True, "count": len(out), "intents": out}

    def order_execute(self, *, intent: Dict[str, Any]) -> Dict[str, Any]:
        intent = _unwrap_intent(intent) or {}
        action = str(intent.get("action") or "").upper()
        skill_args = {
            "side": "buy" if action == "BUY" else "sell",
            "symbol": intent.get("symbol"),
            "qty": int(intent.get("qty") or 1),
            "order_type": intent.get("order_type") or "market",
            "price": intent.get("price"),
        }
        out = self.runner.run(run_id=_new_run_id(), skill="order.place", args=skill_args)
        return asdict(out)

    # ---------- natural language ----------

    def run(self, text: str) -> Dict[str, Any]:
        t = text.strip()

        if t == "승인":
            return self.approve_intent()

        if t.startswith("승인 "):
            return self.approve_intent(intent_id=t.split(" ", 1)[1].strip())

        if t in ("최근주문", "대기주문"):
            return self.list_intents()

        intent = parse_nl(text)
        call = route(intent)

        fn = getattr(self, call.tool, None)
        if fn is None:
            return {"ok": False, "message": f"Unknown tool: {call.tool}"}

        return fn(**call.kwargs)
