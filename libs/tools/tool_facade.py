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
from libs.approval.service import ApprovalService

from libs.agent.intent_parser import parse_nl
from libs.agent.router import route


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _mode() -> str:
    # server mode (mock/real)
    return (os.getenv("KIWOOM_MODE", "real") or "real").strip().lower()


def _execution_enabled() -> bool:
    v = (os.getenv("EXECUTION_ENABLED", "false") or "false").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _approval_mode() -> str:
    """Return approval mode: 'manual' or 'auto'.

    Priority:
      1) APPROVAL_MODE env (manual|auto)
      2) AUTO_APPROVE env:
         - if set to 'manual'|'auto' => treated as mode (new-style)
         - if set to boolean true/false => backward-compatible (true => auto)
      3) default: manual
    """
    v = (os.getenv("APPROVAL_MODE", "") or "").strip().lower()
    if v in ("manual", "auto"):
        return v

    legacy = (os.getenv("AUTO_APPROVE", "") or "").strip().lower()
    if legacy in ("manual", "auto"):
        return legacy
    if legacy in ("1", "true", "yes", "y", "on"):
        return "auto"
    return "manual"



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
        self.approvals = ApprovalService(self.intent_store)

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

    def _last_row(self) -> Optional[Dict[str, Any]]:
        rows = self._load_all_rows()
        return rows[-1] if rows else None

    def _last_intent(self) -> Optional[Dict[str, Any]]:
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

        # approval policy:
        # - APPROVAL_MODE=manual: always return needs_approval (no auto execution)
        # - APPROVAL_MODE=auto: execute immediately ONLY if EXECUTION_ENABLED=true
        if _approval_mode() == "auto":
            if not _execution_enabled():
                # keep consistent: auto mode but execution disabled => still require manual approval/enable switch
                return {
                    "decision": decision_dict,
                    "note": "APPROVAL_MODE=auto but EXECUTION_ENABLED=false, so execution is blocked.",
                }
            exec_res = self.order_execute(intent=intent or raw_intent)
            return {"decision": decision_dict, "execution": exec_res}

        return {"decision": decision_dict}

    def approve_intent(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        return self.approvals.approve(
            intent_id=intent_id,
            execution_enabled=_execution_enabled(),
            execute_fn=lambda it: self.order_execute(intent=it),
        )

    def preview_intent(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        return self.approvals.preview(intent_id=intent_id)

    def reject_intent(self, *, intent_id: Optional[str] = None, reason: str = "rejected") -> Dict[str, Any]:
        return self.approvals.reject(intent_id=intent_id, reason=reason)

    def _append_intent_marker(
        self,
        *,
        intent_id: str,
        status: str,
        reason: Optional[str],
        intent: Dict[str, Any],
        execution: Optional[Dict[str, Any]] = None,
    ) -> None:
        marker = {
            "ts": int(__import__("time").time()),
            "intent_id": intent_id,
            "status": status,
            "reason": reason,
            "intent": intent,
        }
        if execution is not None:
            marker["execution"] = execution

        self.intent_store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.intent_store_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(marker, ensure_ascii=False) + "\n")

    def _latest_row(self, intent_id: str) -> Optional[Dict[str, Any]]:
        # Find the latest row for this intent_id (stable retry semantics).
        rows = self._load_all_rows()
        latest: Optional[Dict[str, Any]] = None
        for r in rows:
            rid = r.get("intent_id") or (_unwrap_intent(r) or {}).get("intent_id")
            if str(rid) != str(intent_id):
                continue
            ts = int(r.get("ts") or 0)
            if (latest is None) or (ts >= int(latest.get("ts") or 0)):
                latest = r
        return latest


    def list_intents(self, limit: int = 5) -> Dict[str, Any]:
        # Rows contain both stored intents and status markers (e.g., rejected). We want
        # a stable "최근주문" view, so we aggregate by intent_id where the latest row wins.
        rows = self._load_all_rows()

        latest_by_id = {}
        for r in rows:
            intent = _unwrap_intent(r) or {}
            intent_id = intent.get("intent_id") or r.get("intent_id")
            if not intent_id:
                continue
            ts = int(r.get("ts") or 0)
            prev = latest_by_id.get(intent_id)
            if (prev is None) or (ts >= int(prev.get("ts") or 0)):
                latest_by_id[intent_id] = {**r, "intent": intent, "ts": ts, "intent_id": intent_id}

        # newest first
        uniq = sorted(latest_by_id.values(), key=lambda x: int(x.get("ts") or 0), reverse=True)
        uniq = uniq[: max(1, int(limit))]

        out = []
        for r in uniq:
            intent = r.get("intent") or {}
            status = r.get("status") or "stored"
            out.append(
                {
                    "intent_id": r.get("intent_id"),
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

        # preview
        if t in ("승인?", "미리보기", "프리뷰", "주문확인"):
            return self.preview_intent()

        if t.startswith("미리보기 "):
            return self.preview_intent(intent_id=t.split(" ", 1)[1].strip())

        # reject
        if t in ("거절", "취소"):
            return self.reject_intent()

        if t.startswith("거절 "):
            return self.reject_intent(intent_id=t.split(" ", 1)[1].strip())

        # approve
        if t == "승인":
            return self.approve_intent()

        if t.startswith("승인 "):
            return self.approve_intent(intent_id=t.split(" ", 1)[1].strip())

        # list
        if t in ("최근주문", "대기주문"):
            return self.list_intents()

        intent = parse_nl(text)
        call = route(intent)

        fn = getattr(self, call.tool, None)
        if fn is None:
            return {"ok": False, "message": f"Unknown tool: {call.tool}"}

        return fn(**call.kwargs)