from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from libs.supervisor.intent_store import IntentStore
from libs.execution.intent_identity import physical_order_fingerprint
from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    INTENT_STATE_FAILED,
    INTENT_STATE_PENDING,
    INTENT_STATE_REJECTED,
    SQLiteIntentStateStore,
)


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

    def __init__(
        self,
        store: IntentStore,
        *,
        state_store: Optional[SQLiteIntentStateStore] = None,
    ):
        self.store = store
        self.state_store = state_store
        if self.state_store is None:
            # Step5C Fix1: previously fell back to store.path.with_suffix(
            # ".db") (data/logs/intents.db) whenever INTENT_STATE_DB_PATH was
            # unset -- a different physical file than the canonical intent
            # ownership DB (data/state/intent_state.db) used by the
            # automated execute_from_packet path, so the two execution
            # entry points could each independently "own" the same real
            # order. No local fallback is computed here anymore; the
            # canonical resolver inside SQLiteIntentStateStore (shared by
            # every consumer) is the single source of truth.
            try:
                self.state_store = SQLiteIntentStateStore()
            except Exception:
                self.state_store = None

    # ---------- low-level journal helpers ----------

    def _safe_state_ensure(self, *, intent_id: str) -> Optional[str]:
        if self.state_store is None:
            return None
        try:
            self.state_store.ensure_intent(intent_id, initial_state=INTENT_STATE_PENDING)
            return None
        except Exception as e:
            return f"intent state ensure failed: {e}"

    def _safe_state_transition(
        self,
        *,
        intent_id: str,
        to_state: str,
        expected_from_state: Optional[str] = None,
        reason: str = "",
        meta: Optional[Dict[str, Any]] = None,
        execution: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if self.state_store is None:
            return None
        try:
            self.state_store.transition(
                intent_id=intent_id,
                to_state=to_state,
                expected_from_state=expected_from_state,
                reason=reason,
                meta=meta or {},
                execution=execution,
            )
            return None
        except Exception as e:
            return f"intent state transition failed ({to_state}): {e}"

    @staticmethod
    def _execution_order(intent: Dict[str, Any]) -> Dict[str, Any]:
        order_type = str(intent.get("order_type") or "market").strip().lower()
        return {
            "action": str(intent.get("action") or "").strip().upper(),
            "symbol": intent.get("symbol"),
            "qty": intent.get("qty"),
            "price": intent.get("price"),
            "order_type": order_type,
            "trde_tp": "3" if order_type in ("market", "mkt") else "0",
            "orig_ord_no": intent.get("orig_ord_no"),
            "cncl_qty": intent.get("cncl_qty"),
            "mdfy_qty": intent.get("mdfy_qty"),
            "mdfy_uv": intent.get("mdfy_uv"),
        }

    def admit_pre_approved_intent(self, intent: Dict[str, Any], *, source: str = "automatic_policy") -> Optional[str]:
        """Persist intent_id into the canonical store as approved, without
        going through the manual approve() gate.

        Step5C Fix4: claim_execution() never self-admits an intent_id; a
        caller-supplied or deterministic identity does not carry execution
        authority by itself. A legitimate "auto" path (APPROVAL_MODE=auto in
        ExecutorAgent.submit_order_intent / ToolFacade.order_place_intent,
        which never goes through approve()'s own PENDING->APPROVED
        transition) must explicitly persist this intent as approved through
        this authorized call BEFORE reaching execute_owned_order, exactly
        as creation authority is separate from execution authority: the
        risk-gate decision inside TwoPhaseSupervisor.create_intent, plus
        the caller's own APPROVAL_MODE=auto + EXECUTION_ENABLED=true
        configuration, is what authorizes this -- not the runner
        self-admitting an arbitrary identity it has never seen before.
        Idempotent: a no-op (returns None) if already approved/beyond.
        """
        iid = str((intent or {}).get("intent_id") or "").strip()
        if not iid or self.state_store is None:
            return "intent_id and a configured state_store are required"
        try:
            order = self._execution_order(intent)
            fingerprint = physical_order_fingerprint({}, order)
            if fingerprint is None:
                return "intent admission failed: invalid physical order"
            admitted = self.state_store.admit_intent(iid, fingerprint=fingerprint, source=source)
            if not admitted.get("admitted"):
                return f"intent admission failed: {admitted.get('reason')}"
            return None
        except Exception as e:
            return f"intent admission failed: {e}"

    def _state_status(self, intent_id: str) -> str:
        if self.state_store is None:
            return ""
        try:
            row = self.state_store.get_state(intent_id)
        except Exception:
            return ""
        if not isinstance(row, dict):
            return ""
        return str(row.get("state") or "").strip().lower()

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
            state_err = self._safe_state_ensure(intent_id=intent_id)
            if state_err:
                return None, None, state_err
            return intent_id, last, None

        loaded = self.store.load(intent_id)
        intent = _unwrap_intent(loaded)
        if not intent:
            # It might still exist as a marker row only; try scanning journal
            latest = self._latest_row(intent_id)
            intent = _unwrap_intent(latest) if latest else None
        if not intent:
            return intent_id, None, f"intent_id not found: {intent_id}"
        state_err = self._safe_state_ensure(intent_id=str(intent_id))
        if state_err:
            return None, None, state_err
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
        status = self._state_status(iid) or str(latest.get("status") or "pending_approval")
        return {
            "ok": True,
            "intent_id": iid,
            "status": status,
            "reason": latest.get("reason"),
            "intent": intent,
            "execution": latest.get("execution"),
        }

    def reject(self, *, intent_id: Optional[str] = None, reason: str = "rejected") -> Dict[str, Any]:
        iid, intent, err = self._resolve_intent(intent_id)
        if err or not iid or not intent:
            return {"ok": False, "message": err or "Unknown error"}

        latest = self._latest_row(iid)
        latest_status = str((latest.get("status") or "")).lower() if latest else ""
        state_status = self._state_status(iid)
        effective_status = state_status or latest_status
        if effective_status == "executed":
            return {"ok": False, "intent_id": iid, "message": "Already executed. Reject is not allowed."}
        if effective_status == "approved":
            return {"ok": False, "intent_id": iid, "message": "Already approved. Reject is not allowed."}
        if effective_status == "executing":
            return {"ok": False, "intent_id": iid, "message": "Execution in progress. Reject is not allowed."}
        if effective_status == "failed":
            return {"ok": False, "intent_id": iid, "message": "Failed intent cannot be rejected."}
        if effective_status == "rejected":
            return {"ok": False, "intent_id": iid, "message": "Already rejected."}

        state_err = self._safe_state_transition(
            intent_id=iid,
            to_state=INTENT_STATE_REJECTED,
            expected_from_state=INTENT_STATE_PENDING,
            reason=reason,
            meta={"source": "approval_service", "op": "reject"},
        )
        if state_err:
            return {"ok": False, "intent_id": iid, "message": state_err}

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
        latest_status = str(latest.get("status") or "").lower() if latest else ""
        state_status = self._state_status(iid)
        effective_status = state_status or latest_status

        if effective_status:
            if effective_status == "rejected":
                return {
                    "ok": False,
                    "intent_id": iid,
                    "message": "Intent is rejected.",
                    "reason": latest.get("reason"),
                }
            if effective_status == "executed":
                return {
                    "ok": True,
                    "intent_id": iid,
                    "status": "executed",
                    "execution": latest.get("execution"),
                    "note": "Already executed. Returned cached execution.",
                }
            if effective_status == "failed":
                return {
                    "ok": False,
                    "intent_id": iid,
                    "message": "Intent previously failed. Create a new intent for retry.",
                    "reason": latest.get("reason"),
                }
            if effective_status == "executing":
                return {
                    "ok": False,
                    "intent_id": iid,
                    "message": "Intent is executing.",
                }
            if effective_status == "approved" and not execution_enabled:
                return {
                    "ok": True,
                    "intent_id": iid,
                    "status": "approved",
                    "note": "Already approved. Execution is still disabled.",
                }

        # Step5C Fix5 (item 9/20): admission is created here ONLY as the
        # first-ever transition into "approved" -- via admit_intent's own
        # pending->approved promotion, triggered by this explicit approve()
        # call using the intent's own persisted payload. A row that is
        # ALREADY "approved" with no admission (a genuinely legacy state --
        # e.g. one set via a direct transition() call bypassing admission
        # entirely) is deliberately NOT repaired here: that would be exactly
        # the kind of implicit authority-creation this Fix closes inside
        # claim_execution() itself, just relocated one layer up. Such a row
        # falls through unchanged and fails closed downstream at
        # claim_execution() (ADMISSION_NOT_FOUND, broker calls 0) --
        # correct, since nothing ever explicitly admitted it.
        if effective_status in ("", INTENT_STATE_PENDING):
            state_err = self.admit_pre_approved_intent(intent, source="manual_approval")
            if state_err:
                return {"ok": False, "intent_id": iid, "message": state_err}
        if effective_status != "approved":
            # Mark approved first (audit trail)
            self._append_marker(intent_id=iid, status="approved", reason="manual approve", intent=intent)

        if not execution_enabled:
            return {
                "ok": True,
                "intent_id": iid,
                "status": "approved",
                "note": "Execution is disabled (EXECUTION_ENABLED=false).",
            }

        # Step5C Fix2 (HIGH1 root cause): this service used to perform its
        # own separate approved->executing CAS transition here, before
        # calling execute_fn. That gave the intent TWO independent claiming
        # mechanisms -- this one, and libs/execution/intent_execution_owner.
        # py's claim_execution() inside the runner -- with no ownership
        # capability check tying them together, which is exactly what let
        # Codex's audit reproduce two concurrent runner invocations both
        # seeing state==executing and both dispatching to the broker. There
        # is now exactly one place that ever claims execution:
        # execute_owned_order(), reached inside execute_fn's own call chain
        # (ToolFacade.order_execute / ExecutorAgent.execute_order ->
        # CompositeSkillRunner.run()). The intent is intentionally left in
        # "approved" state here; execute_fn's own downstream CAS is what
        # atomically claims it (and is what a second, concurrent approve()
        # call for the same intent_id will lose against).
        self._append_marker(intent_id=iid, status="executing", reason="execution started", intent=intent)

        try:
            exec_res = execute_fn(intent)
        except Exception as e:
            fail_reason = str(e)
            # Step5C Fix3 (MEDIUM2): the JSON read-model marker must never
            # contradict the canonical SQLite lifecycle. Only mark FAILED
            # here (both canonical state AND this marker) when we know for
            # certain no canonical claim was ever taken (state is still
            # "approved") -- there is no ambiguity about a broker dispatch
            # in that case. If a claim WAS taken (state is "executing"),
            # this is exactly the crash/exception-during-normalization
            # boundary execute_owned_order's own contract already governs
            # (EXECUTING stays durable, no implicit replay) -- do not
            # second-guess it, and do not let the read-model claim "failed"
            # when canonical truth says otherwise.
            if self._state_status(iid) == INTENT_STATE_APPROVED:
                self._safe_state_transition(
                    intent_id=iid,
                    to_state=INTENT_STATE_FAILED,
                    expected_from_state=INTENT_STATE_APPROVED,
                    reason=fail_reason,
                    meta={"source": "approval_service", "op": "execute_fail_pre_claim"},
                )
                self._append_marker(intent_id=iid, status="failed", reason=fail_reason, intent=intent)
            else:
                self._append_marker(intent_id=iid, status="executing",
                                     reason=f"reconciliation_required: {fail_reason}", intent=intent)
            raise

        # The canonical intent_state row (written by execute_owned_order's
        # claim_execution/finish_execution, not by this service) is the sole
        # source of truth for what actually happened -- never force a
        # status here that outruns it (Fix2 MEDIUM1: an UNKNOWN broker
        # outcome must never be recorded as "executed").
        final_status = self._state_status(iid)
        execution_owner = None
        try:
            execution_owner = self.state_store.get_owner(iid) if self.state_store else None
        except Exception:
            execution_owner = None

        if final_status == INTENT_STATE_EXECUTED:
            self._append_marker(intent_id=iid, status="executed", reason=None, intent=intent, execution=exec_res)
            return {"ok": True, "intent_id": iid, "status": "executed",
                    "execution": exec_res, "execution_owner": execution_owner}
        if final_status == INTENT_STATE_FAILED:
            self._append_marker(intent_id=iid, status="failed", reason="execution_failed", intent=intent, execution=exec_res)
            return {"ok": False, "intent_id": iid, "status": "failed",
                    "execution": exec_res, "execution_owner": execution_owner,
                    "message": "Execution failed or was blocked."}
        if final_status == INTENT_STATE_EXECUTING:
            # UNKNOWN / crash / terminal-persistence-failure boundary
            # (Step5C contract, unchanged): stays non-terminal, durably
            # locked against replay, and explicitly reconciliation-required
            # -- never silently promoted to "executed".
            self._append_marker(intent_id=iid, status="executing", reason="reconciliation_required",
                                 intent=intent, execution=exec_res)
            return {"ok": False, "intent_id": iid, "status": "executing",
                    "execution": exec_res, "execution_owner": execution_owner,
                    "reconciliation_required": True,
                    "message": "Execution outcome is unknown; reconciliation required."}
        # The ownership claim itself was denied before any real dispatch
        # (e.g. a losing concurrent approve() call, a physical-order
        # conflict, or the CAS backend being unavailable) -- state is
        # whatever it already was (typically still "approved"); broker call
        # count for this call is zero.
        self._append_marker(intent_id=iid, status="execute_denied", reason=None, intent=intent, execution=exec_res)
        return {"ok": False, "intent_id": iid, "status": final_status or "approved",
                "execution": exec_res, "execution_owner": execution_owner,
                "message": "Execution was not dispatched."}

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
