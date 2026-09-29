"""P0-B -- Step5D crash reconciliation (MANUAL_REQUIRED, audited).

Covers the CRITICAL crash window this closes:
  CAS CLAIM -> BROKER DISPATCH -> ***CRASH*** -> RESULT PERSIST

Verifies:
  - an orphaned physical_order_claim (claimed, never finished) is detected
    by report() once past the grace period, never before
  - resolve() requires explicit operator-confirmed evidence (never guesses)
  - resolve() refuses to touch a claim it doesn't actually hold
  - resolve() performs the exact same finish_execution/release_physical_order
    calls Step5C's own execute_owned_order uses on a genuine terminal
    outcome -- no new transition logic, no Step5C schema change
  - every resolution is durably audited
"""

from __future__ import annotations

import json

import scripts.step5d_crash_reconciliation as step5d
from libs.supervisor.intent_state_store import INTENT_STATE_EXECUTED, INTENT_STATE_EXECUTING, SQLiteIntentStateStore


def _simulate_crash_during_dispatch(db_path, *, intent_id="crash-intent-1", physical_key="phys-key-1", owner="owner-1"):
    """Reproduces the exact CAS sequence execute_owned_order performs up to
    (but not including) finish_execution -- i.e. a crash right after the
    broker dispatch, before the result was persisted."""
    store = SQLiteIntentStateStore(str(db_path))
    store.ensure_intent(intent_id)
    store.admit_intent(intent_id, fingerprint=physical_key, source="test_simulated_dispatch")
    claim = store.claim_execution(intent_id, fingerprint=physical_key, owner=owner)
    assert claim["claimed"] is True
    phys = store.claim_physical_order(physical_key, intent_id=intent_id, owner=owner)
    assert phys["claimed"] is True
    # No finish_execution() call -- this is the crash.
    return store


def test_report_finds_no_orphans_before_grace_period(tmp_path):
    db_path = tmp_path / "intent_state.db"
    _simulate_crash_during_dispatch(db_path)
    result = step5d.report(db_path=str(db_path), grace_sec=3600, limit=50)
    assert result["ok"] is True
    assert result["orphan_count"] == 0
    assert result["manual_reconciliation_required"] is False


def test_report_finds_the_orphan_once_past_grace_period(tmp_path):
    db_path = tmp_path / "intent_state.db"
    _simulate_crash_during_dispatch(db_path, intent_id="crash-intent-2", physical_key="phys-key-2")
    result = step5d.report(db_path=str(db_path), grace_sec=0, limit=50)
    assert result["ok"] is True
    assert result["orphan_count"] == 1
    assert result["manual_reconciliation_required"] is True
    orphan = result["orphans"][0]
    assert orphan["intent_id"] == "crash-intent-2"
    assert orphan["physical_order_key"] == "phys-key-2"
    assert orphan["intent_state"] == INTENT_STATE_EXECUTING


def test_resolve_requires_confirmed_by_and_evidence(tmp_path):
    db_path = tmp_path / "intent_state.db"
    _simulate_crash_during_dispatch(db_path, intent_id="crash-intent-3", physical_key="phys-key-3")

    missing_confirmer = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-3", intent_id="crash-intent-3",
        outcome="executed", confirmed_by="", evidence="checked kt00007", audit_log=None,
    )
    assert missing_confirmer["ok"] is False

    missing_evidence = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-3", intent_id="crash-intent-3",
        outcome="executed", confirmed_by="operator-a", evidence="", audit_log=None,
    )
    assert missing_evidence["ok"] is False

    # Neither rejected attempt may have mutated anything -- the claim is
    # still held and still EXECUTING.
    result = step5d.report(db_path=str(db_path), grace_sec=0, limit=50)
    assert result["orphan_count"] == 1


def test_resolve_refuses_to_touch_a_claim_it_does_not_hold(tmp_path):
    db_path = tmp_path / "intent_state.db"
    _simulate_crash_during_dispatch(db_path, intent_id="real-holder", physical_key="phys-key-4")

    out = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-4", intent_id="wrong-intent-id",
        outcome="executed", confirmed_by="operator-a", evidence="checked kt00007 order history",
        audit_log=None,
    )
    assert out["ok"] is False
    assert out["holder_intent_id"] == "real-holder"


def test_resolve_executed_transitions_state_and_releases_lease_and_audits(tmp_path, monkeypatch):
    db_path = tmp_path / "intent_state.db"
    audit_log = tmp_path / "step5d_audit.jsonl"
    _simulate_crash_during_dispatch(db_path, intent_id="crash-intent-5", physical_key="phys-key-5", owner="owner-5")

    out = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-5", intent_id="crash-intent-5",
        outcome="executed", confirmed_by="operator-a",
        evidence="kt00007 order history 2026-09-17 10:15 confirms BUY 005930 accepted (ord_no 12345)",
        audit_log=str(audit_log),
    )
    assert out["ok"] is True
    assert out["resolved_state"] == INTENT_STATE_EXECUTED

    store = SQLiteIntentStateStore(str(db_path))
    assert store.get_state("crash-intent-5")["state"] == INTENT_STATE_EXECUTED
    assert store.get_physical_claim("phys-key-5") is None  # lease released on terminal outcome

    # Orphan is gone now.
    result = step5d.report(db_path=str(db_path), grace_sec=0, limit=50)
    assert result["orphan_count"] == 0

    # Durable, human-readable audit trail exists.
    lines = audit_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["intent_id"] == "crash-intent-5"
    assert record["confirmed_by"] == "operator-a"
    assert "kt00007" in record["evidence"]


def test_resolve_failed_transitions_state_and_releases_lease(tmp_path):
    db_path = tmp_path / "intent_state.db"
    audit_log = tmp_path / "step5d_audit.jsonl"
    _simulate_crash_during_dispatch(db_path, intent_id="crash-intent-6", physical_key="phys-key-6", owner="owner-6")

    out = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-6", intent_id="crash-intent-6",
        outcome="failed", confirmed_by="operator-b",
        evidence="kt00007 order history 2026-09-17 shows no matching order -- never reached the broker",
        audit_log=str(audit_log),
    )
    assert out["ok"] is True
    from libs.supervisor.intent_state_store import INTENT_STATE_FAILED

    assert out["resolved_state"] == INTENT_STATE_FAILED
    store = SQLiteIntentStateStore(str(db_path))
    assert store.get_physical_claim("phys-key-6") is None


def test_resolve_rejects_invalid_outcome_value(tmp_path):
    db_path = tmp_path / "intent_state.db"
    _simulate_crash_during_dispatch(db_path, intent_id="crash-intent-7", physical_key="phys-key-7")
    out = step5d.resolve(
        db_path=str(db_path), physical_order_key="phys-key-7", intent_id="crash-intent-7",
        outcome="maybe", confirmed_by="operator-a", evidence="unsure", audit_log=None,
    )
    assert out["ok"] is False
