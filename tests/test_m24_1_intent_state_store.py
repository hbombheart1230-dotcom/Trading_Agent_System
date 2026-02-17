from __future__ import annotations

import pytest

from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    INTENT_STATE_FAILED,
    INTENT_STATE_PENDING,
    INTENT_STATE_REJECTED,
    IntentStateMachine,
    SQLiteIntentStateStore,
)


def test_m24_1_state_machine_happy_path():
    r1 = IntentStateMachine.apply(INTENT_STATE_PENDING, INTENT_STATE_APPROVED)
    r2 = IntentStateMachine.apply(INTENT_STATE_APPROVED, INTENT_STATE_EXECUTING)
    r3 = IntentStateMachine.apply(INTENT_STATE_EXECUTING, INTENT_STATE_EXECUTED)

    assert r1.ok is True and r1.changed is True
    assert r2.ok is True and r2.changed is True
    assert r3.ok is True and r3.changed is True


def test_m24_1_state_machine_blocks_invalid_transition():
    bad = IntentStateMachine.apply(INTENT_STATE_PENDING, INTENT_STATE_EXECUTING)
    assert bad.ok is False
    assert bad.reason == "invalid_transition"

    same = IntentStateMachine.apply(INTENT_STATE_APPROVED, INTENT_STATE_APPROVED)
    assert same.ok is False
    assert same.reason == "no_state_change"


def test_m24_1_state_machine_allows_terminal_idempotent_retry():
    idem = IntentStateMachine.apply(INTENT_STATE_EXECUTED, INTENT_STATE_EXECUTED)
    assert idem.ok is True
    assert idem.changed is False
    assert idem.reason == "idempotent_terminal"


def test_m24_1_sqlite_store_transitions_and_journal(tmp_path):
    db = tmp_path / "intent_state.db"
    store = SQLiteIntentStateStore(str(db))
    iid = "i-001"

    s0 = store.ensure_intent(iid)
    assert s0["state"] == INTENT_STATE_PENDING

    s1 = store.transition(intent_id=iid, to_state=INTENT_STATE_APPROVED, reason="manual approve")
    assert s1["state"] == INTENT_STATE_APPROVED

    s2 = store.transition(intent_id=iid, to_state=INTENT_STATE_EXECUTING, reason="start execute")
    assert s2["state"] == INTENT_STATE_EXECUTING

    s3 = store.transition(
        intent_id=iid,
        to_state=INTENT_STATE_EXECUTED,
        reason="done",
        execution={"ok": True, "order_id": "o-1"},
    )
    assert s3["state"] == INTENT_STATE_EXECUTED

    rows = store.list_journal(iid, limit=20)
    assert len(rows) == 4
    assert rows[0]["to_state"] == INTENT_STATE_PENDING
    assert rows[1]["to_state"] == INTENT_STATE_APPROVED
    assert rows[2]["to_state"] == INTENT_STATE_EXECUTING
    assert rows[3]["to_state"] == INTENT_STATE_EXECUTED
    assert rows[3]["execution"]["order_id"] == "o-1"


def test_m24_1_sqlite_store_rejects_invalid_transition(tmp_path):
    db = tmp_path / "intent_state.db"
    store = SQLiteIntentStateStore(str(db))
    iid = "i-002"
    store.ensure_intent(iid)

    with pytest.raises(ValueError):
        store.transition(intent_id=iid, to_state=INTENT_STATE_FAILED, reason="invalid_direct_fail")


def test_m24_1_sqlite_store_supports_pending_to_rejected(tmp_path):
    db = tmp_path / "intent_state.db"
    store = SQLiteIntentStateStore(str(db))
    iid = "i-003"

    store.ensure_intent(iid)
    out = store.transition(intent_id=iid, to_state=INTENT_STATE_REJECTED, reason="manual reject")
    assert out["state"] == INTENT_STATE_REJECTED
