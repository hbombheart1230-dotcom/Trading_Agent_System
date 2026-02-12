from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.skills.runner import CompositeSkillRunner
from libs.supervisor.two_phase import TwoPhaseSupervisor
from libs.supervisor.intent_store import IntentStore


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _unwrap_intent(row: Any) -> Optional[Dict[str, Any]]:
    """
    Accept either:
      - raw intent dict: {"intent_id":..., "action":..., ...}
      - wrapped record: {"ts":..., "intent_id":..., "intent":{...}, "status":..., ...}
    """
    if not isinstance(row, dict):
        return None
    if "intent" in row and isinstance(row.get("intent"), dict):
        return row["intent"]
    return row


class ExecutorAgent:
    """
    Execution-facing agent:
      - submit intent (two-phase)
      - preview / approve / reject
      - list intents (audit trail)

    This is intentionally "dumb": it does not decide strategy.
    It just enforces the two-phase gate and calls execution skills.
    """

    def __init__(
        self,
        *,
        runner: CompositeSkillRunner,
        supervisor: TwoPhaseSupervisor,
        intent_store: IntentStore,
        intent_store_path: str | Path,
    ):
        self.runner = runner
        self.supervisor = supervisor
        self.intent_store = intent_store
        self.intent_store_path = Path(intent_store_path)

    # ---------- store helpers ----------

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

    def _last_row(self) -> Optional[Dict[str, Any]]:
        rows = self._load_all_rows()
        return rows[-1] if rows else None

    def last_intent(self) -> Optional[Dict[str, Any]]:
        row = self._last_row()
        return _unwrap_intent(row) if row else None

    def _summarize_intent(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        intent = _unwrap_intent(intent) or {}
        return {
            "intent_id": intent.get("intent_id"),
            "action": intent.get("action"),
            "symbol": intent.get("symbol"),
            "qty": intent.get("qty"),
            "order_type": intent.get("order_type"),
            "price": intent.get("price"),
            "rationale": intent.get("rationale", ""),
            "created_epoch": intent.get("created_epoch"),
        }

    # ---------- core: intent -> execute ----------

    def submit_order_intent(
        self,
        *,
        side: str,
        symbol: str,
        qty: int,
        order_type: str = "market",
        price: Optional[int] = None,
        rationale: str = "",
        approval_mode: str = "manual",          # "manual" | "auto"
        execution_enabled: bool = False,        # gate for real execution
    ) -> Dict[str, Any]:
        """
        Creates an order intent via supervisor.
        If approval_mode=auto and execution_enabled=True, executes immediately.
        Otherwise returns needs_approval decision.
        """
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

        if str(approval_mode).lower() == "auto":
            if not execution_enabled:
                return {
                    "decision": decision_dict,
                    "note": "APPROVAL_MODE=auto but EXECUTION_ENABLED=false, so execution is blocked.",
                }
            exec_res = self.execute_order(intent=intent or raw_intent)
            return {"decision": decision_dict, "execution": exec_res}

        return {"decision": decision_dict}

    def execute_order(self, *, intent: Dict[str, Any]) -> Dict[str, Any]:
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

    def approve(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        if not intent_id:
            intent = self.last_intent()
            if not intent:
                return {"ok": False, "message": "No stored intents."}
            intent_id = str(intent.get("intent_id") or "")
        else:
            loaded = self.intent_store.load(intent_id)
            intent = _unwrap_intent(loaded)

        if not intent:
            return {"ok": False, "message": f"intent_id not found: {intent_id}"}

        exec_res = self.execute_order(intent=intent)
        return {"ok": True, "intent_id": intent_id, "execution": exec_res}

    def preview(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        if not intent_id:
            intent = self.last_intent()
            if not intent:
                return {"ok": False, "message": "No stored intents."}
        else:
            loaded = self.intent_store.load(intent_id)
            intent = _unwrap_intent(loaded)
            if not intent:
                return {"ok": False, "message": f"intent_id not found: {intent_id}"}
        return {"ok": True, "intent": self._summarize_intent(intent)}

    def reject(self, *, intent_id: Optional[str] = None, reason: str = "rejected") -> Dict[str, Any]:
        if not intent_id:
            intent = self.last_intent()
            if not intent:
                return {"ok": False, "message": "No stored intents."}
            intent_id = str(intent.get("intent_id") or "")
        else:
            loaded = self.intent_store.load(intent_id)
            intent = _unwrap_intent(loaded)
            if not intent:
                return {"ok": False, "message": f"intent_id not found: {intent_id}"}

        marker = {
            "ts": int(time.time()),
            "intent_id": intent_id,
            "status": "rejected",
            "reason": reason,
            "intent": intent,
        }
        self.intent_store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.intent_store_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(marker, ensure_ascii=False) + "\n")

        return {"ok": True, "intent_id": intent_id, "status": "rejected", "reason": reason}

    def list_intents(self, limit: int = 5) -> Dict[str, Any]:
        rows = self._load_all_rows()
        recent = rows[-limit:]
        out: List[Dict[str, Any]] = []

        for r in recent:
            intent = _unwrap_intent(r) or {}
            status = r.get("status") or "stored"
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
                    "status": status,
                    "reason": r.get("reason"),
                }
            )

        return {"ok": True, "count": len(out), "intents": out}
