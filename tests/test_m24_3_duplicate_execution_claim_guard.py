from __future__ import annotations

from pathlib import Path

from libs.approval.service import ApprovalService
from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    SQLiteIntentStateStore,
)
from libs.supervisor.intent_store import IntentStore


def _seed_intent(store: IntentStore, *, intent_id: str) -> None:
    store.save(
        {
            "intent_id": intent_id,
            "action": "BUY",
            "symbol": "005930",
            "qty": 1,
            "order_type": "market",
            "price": None,
            "rationale": "m24_3_test",
        }
    )


def test_m24_3_sqlite_status_precedence_blocks_execute_when_state_is_executing(tmp_path: Path):
    jsonl = tmp_path / "intents.jsonl"
    db = tmp_path / "intent_state.db"
    store = IntentStore(str(jsonl))
    state = SQLiteIntentStateStore(str(db))
    svc = ApprovalService(store, state_store=state)

    iid = "i-m24-3-a"
    _seed_intent(store, intent_id=iid)

    a1 = svc.approve(intent_id=iid, execution_enabled=False, execute_fn=lambda it: {"ok": True})
    assert a1["ok"] is True
    assert a1["status"] == INTENT_STATE_APPROVED

    # Force sqlite state only (without adding JSONL executing marker) to simulate stale JSONL view.
    state.transition(
        intent_id=iid,
        to_state=INTENT_STATE_EXECUTING,
        expected_from_state=INTENT_STATE_APPROVED,
        reason="external executing claim",
    )

    a2 = svc.approve(intent_id=iid, execution_enabled=True, execute_fn=lambda it: {"ok": True})
    assert a2["ok"] is False
    assert "executing" in str(a2.get("message", "")).lower()


def test_m24_3_cas_blocks_duplicate_execution_claim_between_services(tmp_path: Path):
    jsonl = tmp_path / "intents.jsonl"
    db = tmp_path / "intent_state.db"
    store = IntentStore(str(jsonl))
    state = SQLiteIntentStateStore(str(db))
    svc1 = ApprovalService(store, state_store=state)
    svc2 = ApprovalService(store, state_store=state)

    iid = "i-m24-3-b"
    _seed_intent(store, intent_id=iid)
    first = svc1.approve(intent_id=iid, execution_enabled=False, execute_fn=lambda it: {"ok": True})
    assert first["ok"] is True
    assert first["status"] == INTENT_STATE_APPROVED

    captured: dict[str, object] = {}

    def _exec_main(intent):  # type: ignore[no-untyped-def]
        dup = svc2.approve(intent_id=iid, execution_enabled=True, execute_fn=lambda it: {"ok": True, "id": "dup"})
        captured["dup"] = dup
        return {"ok": True, "id": "main"}

    out = svc1.approve(intent_id=iid, execution_enabled=True, execute_fn=_exec_main)
    assert out["ok"] is True
    assert out["status"] == INTENT_STATE_EXECUTED

    dup = captured.get("dup")
    assert isinstance(dup, dict)
    assert dup.get("ok") is False
    assert "executing" in str(dup.get("message", "")).lower()

    rows = store.load_all_rows()
    executed_rows = [r for r in rows if str(r.get("intent_id")) == iid and str(r.get("status") or "") == "executed"]
    assert len(executed_rows) == 1
    cur = state.get_state(iid)
    assert cur is not None
    assert cur["state"] == INTENT_STATE_EXECUTED
