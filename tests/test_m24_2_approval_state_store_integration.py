from __future__ import annotations

from pathlib import Path

import pytest

from libs.approval.service import ApprovalService
from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_FAILED,
    INTENT_STATE_REJECTED,
    SQLiteIntentStateStore,
)
from libs.supervisor.intent_store import IntentStore


def _make_services(tmp_path: Path):
    jsonl = tmp_path / "intents.jsonl"
    db = tmp_path / "intent_state.db"
    journal = IntentStore(str(jsonl))
    state = SQLiteIntentStateStore(str(db))
    svc = ApprovalService(journal, state_store=state)
    return journal, state, svc


def _seed_intent(store: IntentStore, *, intent_id: str) -> None:
    store.save(
        {
            "intent_id": intent_id,
            "action": "BUY",
            "symbol": "005930",
            "qty": 1,
            "order_type": "market",
            "price": None,
            "rationale": "m24_2_test",
        }
    )


def test_m24_2_approve_updates_sqlite_state_machine(tmp_path: Path):
    store, state, svc = _make_services(tmp_path)
    iid = "i-m24-2-a"
    _seed_intent(store, intent_id=iid)

    out = svc.approve(intent_id=iid, execution_enabled=True, execute_fn=lambda it: {"ok": True, "id": "ex-1"})
    assert out["ok"] is True
    assert out["status"] == "executed"

    cur = state.get_state(iid)
    assert cur is not None
    assert cur["state"] == INTENT_STATE_EXECUTED

    rows = state.list_journal(iid, limit=20)
    to_states = [r["to_state"] for r in rows]
    assert to_states == ["pending_approval", "approved", "executing", "executed"]


def test_m24_2_reject_updates_sqlite_state_machine(tmp_path: Path):
    store, state, svc = _make_services(tmp_path)
    iid = "i-m24-2-r"
    _seed_intent(store, intent_id=iid)

    out = svc.reject(intent_id=iid, reason="manual reject")
    assert out["ok"] is True
    assert out["status"] == "rejected"

    cur = state.get_state(iid)
    assert cur is not None
    assert cur["state"] == INTENT_STATE_REJECTED


def test_m24_2_execution_error_marks_failed_and_raises(tmp_path: Path):
    store, state, svc = _make_services(tmp_path)
    iid = "i-m24-2-f"
    _seed_intent(store, intent_id=iid)

    def _boom(intent):  # type: ignore[no-untyped-def]
        raise RuntimeError("exec boom")

    with pytest.raises(RuntimeError):
        svc.approve(intent_id=iid, execution_enabled=True, execute_fn=_boom)

    cur = state.get_state(iid)
    assert cur is not None
    assert cur["state"] == INTENT_STATE_FAILED

    rows = state.list_journal(iid, limit=20)
    assert rows[-1]["to_state"] == "failed"
    assert rows[-1]["reason"] == "exec boom"


def test_m24_2_reject_after_approved_is_blocked_by_strict_state(tmp_path: Path):
    store, state, svc = _make_services(tmp_path)
    iid = "i-m24-2-s"
    _seed_intent(store, intent_id=iid)

    out = svc.approve(intent_id=iid, execution_enabled=False, execute_fn=lambda it: {"ok": True})
    assert out["ok"] is True
    assert out["status"] == INTENT_STATE_APPROVED

    blocked = svc.reject(intent_id=iid, reason="late reject")
    assert blocked["ok"] is False
    assert "Reject is not allowed" in str(blocked.get("message"))

    cur = state.get_state(iid)
    assert cur is not None
    assert cur["state"] == INTENT_STATE_APPROVED
