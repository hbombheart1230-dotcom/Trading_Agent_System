from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from libs.supervisor.intent_store import IntentStore


def _unwrap_intent(row: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    if "intent" in row and isinstance(row.get("intent"), dict):
        return row["intent"]
    return row


@dataclass(frozen=True)
class ApprovalResult:
    ok: bool
    intent_id: str
    status: str  # pending_approval | approved | rejected | executed
    message: Optional[str] = None
    reason: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None
    execution: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class ApprovalService:
    """
    M16: Formal approval API (programmatic service).

    - preview(intent_id)
    - approve(intent_id): marks approved; executes only if execution_enabled=True
    - reject(intent_id)
    - list_intents()

    Key invariants:
    - Idempotent execution: same intent_id must not execute twice.
    - Guards still apply in execution layer; this service never bypasses guards.
    """

    def __init__(self, store: IntentStore):
        self.store = store

    # ---------- low-level journal helpers ----------

    def _append_marker(
        self,
        *,
        intent_id: str,
        status: str,
        reason: Optional[str],
        intent: Dict[str, Any],
        execution: Optional[Dict[str, Any]] = None,
    ) -> None:
        row: Dict[str, Any] = {
            "ts": int(time.time()),
            "intent_id": intent_id,
            "status": status,
            "reason": reason,
            "intent": intent,
        }
        if execution is not None:
            row["execution"] = execution
        self.store.append_row(row)

    def _latest_row(self, intent_id: str) -> Optional[Dict[str, Any]]:
        rows = self.store.load_all_rows()
        latest: Optional[Dict[str, Any]] = None
        for r in rows:
            rid = r.get("intent_id") or (_unwrap_intent(r) or {}).get("intent_id")
            if str(rid) != str(intent_id):
                continue
            ts = int(r.get("ts") or 0)
            if (latest is None) or (ts >= int(latest.get("ts") or 0)):
                latest = r
        return latest

    def _resolve_intent(self, intent_id: Optional[str]) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        if not intent_id:
            last = self.last_intent()
            if not last:
                return None, None, "No stored intents."
            intent_id = str(last.get("intent_id") or "")
            return intent_id, last, None

        loaded = self.store.load(intent_id)
        intent = _unwrap_intent(loaded)
        if not intent:
            # It might still exist as a marker row only; try scanning journal
            latest = self._latest_row(intent_id)
            intent = _unwrap_intent(latest) if latest else None
        if not intent:
            return intent_id, None, f"intent_id not found: {intent_id}"
        return str(intent_id), intent, None

    # ---------- public API ----------

    def last_intent(self) -> Optional[Dict[str, Any]]:
        rows = self.store.load_all_rows()
        best: Optional[Dict[str, Any]] = None
        for r in rows:
            intent = _unwrap_intent(r) or {}
            ts = int(r.get("ts") or 0)
            if not intent.get("intent_id"):
                continue
            if (best is None) or (ts >= int(best.get("ts") or 0)):
                best = {"ts": ts, "intent": intent, **r}
        return _unwrap_intent(best) if best else None

    def preview(self, *, intent_id: Optional[str] = None) -> Dict[str, Any]:
        iid, intent, err = self._resolve_intent(intent_id)
        if err or not iid or not intent:
            return {"ok": False, "message": err or "Unknown error"}
        latest = self._latest_row(iid) or {}
        return {
            "ok": True,
            "intent_id": iid,
            "status": (latest.get("status") or "pending_approval"),
            "reason": latest.get("reason"),
            "intent": intent,
            "execution": latest.get("execution"),
        }

    def reject(self, *, intent_id: Optional[str] = None, reason: str = "rejected") -> Dict[str, Any]:
        iid, intent, err = self._resolve_intent(intent_id)
        if err or not iid or not intent:
            return {"ok": False, "message": err or "Unknown error"}

        latest = self._latest_row(iid)
        if latest and str((latest.get("status") or "")).lower() == "executed":
            return {"ok": False, "intent_id": iid, "message": "Already executed. Reject is not allowed."}

        self._append_marker(intent_id=iid, status="rejected", reason=reason, intent=intent)
        return {"ok": True, "intent_id": iid, "status": "rejected", "reason": reason}

    def approve(
        self,
        *,
        intent_id: Optional[str] = None,
        execution_enabled: bool,
        execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        iid, intent, err = self._resolve_intent(intent_id)
        if err or not iid or not intent:
            return {"ok": False, "message": err or "Unknown error"}

        latest = self._latest_row(iid)
        if latest:
            status = str(latest.get("status") or "").lower()
            if status == "rejected":
                return {
                    "ok": False,
                    "intent_id": iid,
                    "message": "Intent is rejected.",
                    "reason": latest.get("reason"),
                }
            if status == "executed":
                return {
                    "ok": True,
                    "intent_id": iid,
                    "status": "executed",
                    "execution": latest.get("execution"),
                    "note": "Already executed. Returned cached execution.",
                }
            if status == "approved" and not execution_enabled:
                return {
                    "ok": True,
                    "intent_id": iid,
                    "status": "approved",
                    "note": "Already approved. Execution is still disabled.",
                }

        # Mark approved first (audit trail)
        self._append_marker(intent_id=iid, status="approved", reason="manual approve", intent=intent)

        if not execution_enabled:
            return {
                "ok": True,
                "intent_id": iid,
                "status": "approved",
                "note": "Execution is disabled (EXECUTION_ENABLED=false).",
            }

        exec_res = execute_fn(intent)

        self._append_marker(intent_id=iid, status="executed", reason=None, intent=intent, execution=exec_res)
        return {"ok": True, "intent_id": iid, "status": "executed", "execution": exec_res}

    def list_intents(self, limit: int = 10) -> Dict[str, Any]:
        rows = self.store.load_all_rows()

        latest_by_id: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            intent = _unwrap_intent(r) or {}
            iid = intent.get("intent_id") or r.get("intent_id")
            if not iid:
                continue
            ts = int(r.get("ts") or 0)
            prev = latest_by_id.get(str(iid))
            if (prev is None) or (ts >= int(prev.get("ts") or 0)):
                latest_by_id[str(iid)] = {**r, "intent": intent, "ts": ts, "intent_id": str(iid)}

        items = sorted(latest_by_id.values(), key=lambda x: int(x.get("ts") or 0), reverse=True)[: max(1, int(limit))]
        # compact output
        out: List[Dict[str, Any]] = []
        for it in items:
            intent = it.get("intent") or {}
            out.append(
                {
                    "ts": it.get("ts"),
                    "intent_id": it.get("intent_id"),
                    "status": it.get("status") or "pending_approval",
                    "reason": it.get("reason"),
                    "action": intent.get("action"),
                    "symbol": intent.get("symbol"),
                    "qty": intent.get("qty"),
                    "order_type": intent.get("order_type"),
                    "price": intent.get("price"),
                    "rationale": intent.get("rationale"),
                }
            )
        return {"ok": True, "count": len(out), "items": out, "intents": out}
