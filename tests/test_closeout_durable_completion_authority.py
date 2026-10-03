"""Regression coverage for the 2026-10-01 closeout durable-completion
authority (HOST runtime pivot follow-up).

Separate concern from tests/test_closeout_single_owner_guard.py: that file
covers the strict-identity LOCK (mutual exclusion while an attempt is in
flight). This file covers libs/reporting/closeout_completion_authority.py
-- a durable SUCCESS-only marker, consulted by
run_closeout_maintenance_with_lock() BEFORE it ever attempts the lock, so
that a day already known to have completed successfully is never
re-run just because the lock itself (which is released on both success
and crash/failure) can no longer prove that by itself.

Test matrix (per the HOST RUNTIME PIVOT task spec):
  A. first owner completes -> writes a durable SUCCESS marker
  B. a second market-status-style trigger, after completion -> NOOP
  C. the scheduled-fallback trigger, after completion -> NOOP (proves the
     marker is shared across trigger identities/processes, not scoped to
     one caller's own in-memory state)
  D. crash before run_closeout_maintenance() returns ok=True -> no marker
     written, a later retry is still permitted
  E. a genuinely still-active live owner -> blocked by the EXISTING lock,
     unaffected by this addition (completion-authority check runs first,
     but must not change lock behavior when there is no prior completion)
  F. first attempt fails (ok=False), second attempt succeeds -> exactly
     one SUCCESS record ends up on disk for that day

All synchronization is deterministic (pre-seeding the completion-authority
file or lock file directly, never sleep/thread timing), matching this
repository's existing closeout test conventions.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_KST = timezone(timedelta(hours=9))


def _today_kst_iso() -> str:
    """libs/runtime/market_status_closeout.py::apply_market_status_closeout_events
    only dispatches an event whose own KST calendar day matches
    datetime.now(KST)'s current day -- a hardcoded historical date in a
    fixture event's received_at would silently stop matching once real
    wall-clock time moves past it. Computed fresh per test run instead."""
    return datetime.now(_KST).date().isoformat()

from libs.reporting.closeout_completion_authority import (
    COMPLETION_ACTION_KEY,
    read_closeout_completion,
    write_closeout_completion_success,
)
from libs.reporting.closeout_maintenance import run_closeout_maintenance_with_lock
from libs.runtime.live_loop_lock import acquire_live_loop_lock


def _stub_ok(**kwargs):
    return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}


def _stub_fail(**kwargs):
    return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": False, "steps": {
        "some_step": {"ok": False, "error": "injected failure"},
    }}


def _counting_stub(result_fn, calls: dict):
    def _inner(**kwargs):
        calls["n"] = calls.get("n", 0) + 1
        return result_fn(**kwargs)

    return _inner


# =============================================================================
# A -- first owner completes -> durable SUCCESS marker written
# =============================================================================


def test_a_first_owner_completes_writes_success_marker(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)

    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_regular_close",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )

    assert result["ok"] is True
    assert result.get("skipped") is not True

    record = read_closeout_completion("2026-10-01", COMPLETION_ACTION_KEY, path=completion_path)
    assert record is not None
    assert record["completion_status"] == "SUCCESS"
    assert record["target_day"] == "2026-10-01"
    assert record["trigger"] == "kiwoom_market_status_regular_close"
    assert completion_path.exists()


# =============================================================================
# B -- second market-status-style trigger after completion -> NOOP
# =============================================================================


def test_b_second_market_status_trigger_after_completion_is_noop(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    write_closeout_completion_success(
        "2026-10-01",
        COMPLETION_ACTION_KEY,
        run_id="prior-run",
        trigger="kiwoom_market_status_regular_close",
        owner_pid=999999,
        path=completion_path,
    )

    calls: dict = {}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        _counting_stub(_stub_ok, calls),
    )

    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_final_refresh",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )

    assert calls.get("n", 0) == 0, "run_closeout_maintenance must not be called when the day is already complete"
    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_COMPLETE"
    assert result["ok"] is True
    assert result["prior_completion"]["run_id"] == "prior-run"
    assert not lock_path.exists(), "a day already known complete must never even attempt the lock"


# =============================================================================
# C -- scheduled-fallback trigger after completion -> NOOP
# =============================================================================


def test_c_scheduled_fallback_after_completion_is_noop(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    write_closeout_completion_success(
        "2026-10-01",
        COMPLETION_ACTION_KEY,
        run_id="tick-loop-run",
        trigger="kiwoom_market_status_regular_close",
        owner_pid=888888,
        path=completion_path,
    )

    calls: dict = {}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        _counting_stub(_stub_ok, calls),
    )

    # Mirrors scripts/run_closeout_maintenance.py's own default CLI trigger
    # label -- a completely different process/invocation from the one that
    # wrote the marker above, proving the marker is shared, durable state,
    # not per-process in-memory dedup.
    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="manual_closeout_maintenance",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )

    assert calls.get("n", 0) == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_COMPLETE"
    assert result["prior_completion"]["trigger"] == "kiwoom_market_status_regular_close"


# =============================================================================
# D -- crash before ok=True -> no marker written, retry still permitted
# =============================================================================


def test_d_crash_before_success_leaves_no_marker_and_permits_retry(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    def _raise(**kwargs):
        raise RuntimeError("simulated crash mid-closeout")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _raise)

    with pytest.raises(RuntimeError, match="simulated crash mid-closeout"):
        run_closeout_maintenance_with_lock(
            day="2026-10-01",
            trigger="kiwoom_market_status_regular_close",
            lock_path=lock_path,
            completion_authority_path=completion_path,
        )

    # The crash must still release the lock (existing finally-block
    # guarantee) and must leave no completion record behind.
    assert not lock_path.exists()
    assert read_closeout_completion("2026-10-01", COMPLETION_ACTION_KEY, path=completion_path) is None

    # A later retry, from any trigger, must proceed normally (not be
    # mistaken for already-complete).
    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)
    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="manual_closeout_maintenance",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )
    assert result["ok"] is True
    assert result.get("skipped") is not True
    assert read_closeout_completion("2026-10-01", COMPLETION_ACTION_KEY, path=completion_path) is not None


# =============================================================================
# E -- genuinely active live owner still blocks (unaffected by this addition)
# =============================================================================


def test_e_active_live_owner_still_blocks_when_not_yet_complete(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=1800, strict_owner_identity=True, owner_token="owner-A",
    )
    assert acquired is True
    assert reason == "ACQUIRED"

    def _boom_if_called(**_kwargs):
        raise AssertionError("run_closeout_maintenance must not be called while another owner holds the lock")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_if_called)

    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_final_refresh",
        lock_path=lock_path,
        lock_stale_sec=1800,
        completion_authority_path=completion_path,
    )

    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_RUNNING_VALID_OWNER"
    assert result["ok"] is False
    assert read_closeout_completion("2026-10-01", COMPLETION_ACTION_KEY, path=completion_path) is None


# =============================================================================
# F -- failed attempt then successful retry -> exactly one SUCCESS record
# =============================================================================


def test_f_retry_after_failure_yields_exactly_one_success_record(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_fail)
    first = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_regular_close",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )
    assert first["ok"] is False
    assert first.get("skipped") is not True
    assert read_closeout_completion("2026-10-01", COMPLETION_ACTION_KEY, path=completion_path) is None

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)
    second = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_final_refresh",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )
    assert second["ok"] is True
    assert second.get("skipped") is not True

    raw = json.loads(completion_path.read_text(encoding="utf-8"))
    success_records = [
        rec for rec in raw.get("completions", {}).values()
        if rec.get("target_day") == "2026-10-01" and rec.get("completion_status") == "SUCCESS"
    ]
    assert len(success_records) == 1
    assert success_records[0]["trigger"] == "kiwoom_market_status_final_refresh"

    # A third trigger must now be a clean NOOP -- canonical report
    # duplication=0 beyond this point.
    calls: dict = {}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        _counting_stub(_stub_ok, calls),
    )
    third = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="manual_closeout_maintenance",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )
    assert calls.get("n", 0) == 0
    assert third["skip_reason"] == "ALREADY_COMPLETE"


# =============================================================================
# Isolation -- a different target_day is never short-circuited by another
# day's completion record
# =============================================================================


def test_different_day_is_not_short_circuited_by_another_days_completion(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    write_closeout_completion_success(
        "2026-09-30",
        COMPLETION_ACTION_KEY,
        run_id="yesterday-run",
        trigger="kiwoom_market_status_regular_close",
        owner_pid=777777,
        path=completion_path,
    )

    calls: dict = {}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance",
        _counting_stub(_stub_ok, calls),
    )

    result = run_closeout_maintenance_with_lock(
        day="2026-10-01",
        trigger="kiwoom_market_status_regular_close",
        lock_path=lock_path,
        completion_authority_path=completion_path,
    )

    assert calls.get("n", 0) == 1
    assert result["ok"] is True
    assert result.get("skipped") is not True


# =============================================================================
# This module never touches broker/execution surfaces -- trading mutation=0
# by construction (no import from libs.execution anywhere in the module
# under test), verified structurally rather than behaviorally.
# =============================================================================


def test_completion_authority_module_has_no_execution_imports():
    import libs.reporting.closeout_completion_authority as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "libs.execution" not in source
    assert "broker" not in source.lower()


# =============================================================================
# G -- end-to-end through the REAL production entrypoints: a market-status
# trigger that completes successfully is never followed by a duplicate
# report write, whether the duplicate attempt comes from another
# market-status event or the scheduled-fallback CLI. This exercises
# libs/runtime/market_status_closeout.py and scripts/run_closeout_maintenance.py
# themselves (unmodified), not just run_closeout_maintenance_with_lock in
# isolation -- proving the existing `if result.get("skipped"): <no report
# write>` branch in both callers correctly treats ALREADY_COMPLETE the same
# way it already treats ALREADY_RUNNING_VALID_OWNER.
# =============================================================================


def test_g_no_duplicate_report_write_across_both_real_trigger_paths(tmp_path, monkeypatch):
    import sys

    import libs.runtime.market_status_closeout as market_status_mod
    import scripts.run_closeout_maintenance as cli_mod
    from libs.reporting import closeout_maintenance as closeout_mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    completion_path = tmp_path / "closeout_completion_authority.json"

    # Both real callers resolve these through module-level defaults when no
    # explicit override is passed at their own call sites -- patch those
    # defaults (same technique tests/test_closeout_single_owner_guard.py
    # already uses for _DEFAULT_CLOSEOUT_LOCK_PATH) so this test stays
    # isolated from the real repository and from other tests in this
    # session, while still exercising the real, unmodified production call
    # chain end to end.
    monkeypatch.setattr(closeout_mod, "_DEFAULT_CLOSEOUT_LOCK_PATH", lock_path)
    import libs.reporting.closeout_completion_authority as authority_mod

    monkeypatch.setattr(authority_mod, "_DEFAULT_COMPLETION_AUTHORITY_PATH", completion_path)

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _stub_ok)

    report_calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.write_closeout_maintenance_report",
        lambda *a, **k: report_calls.__setitem__("n", report_calls["n"] + 1) or {"report_json_path": "x", "report_md_path": "y"},
    )
    monkeypatch.setattr(
        "libs.reporting.scheduled_intelligence.materialize_closeout_intelligence",
        lambda **_k: {"status": "SKIPPED_IN_TEST"},
    )

    today = _today_kst_iso()

    # First: a real market-status regular_close event completes successfully.
    monkeypatch.setattr(
        market_status_mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {"event_id": "evt-g1", "received_at": f"{today}T06:30:00+00:00", "code": "4"}
            ],
        },
    )
    state = {"persisted_state": {}}
    out_state = market_status_mod.apply_market_status_closeout_events(state)
    assert report_calls["n"] == 1
    assert "evt-g1" in out_state["persisted_state"]["processed_market_status_event_ids"]

    # Second: a DIFFERENT market-status code (final_refresh, code "9") on the
    # same day -- the tick-loop's own existing per-action_key dedup would
    # not catch this on its own (different action_key: "...:final_refresh"
    # vs "...:regular_close"), but the completion authority must, since the
    # day's closeout already fully succeeded.
    monkeypatch.setattr(
        market_status_mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {"event_id": "evt-g2", "received_at": f"{today}T07:00:00+00:00", "code": "9"}
            ],
        },
    )
    state2 = {"persisted_state": {}}
    market_status_mod.apply_market_status_closeout_events(state2)
    assert report_calls["n"] == 1, "a second market-status action on an already-complete day must not write a second report"

    # Third: the scheduled-fallback CLI, a wholly separate entrypoint/trigger
    # identity, for the same day.
    monkeypatch.setattr(sys, "argv", ["run_closeout_maintenance.py", "--day", today])
    exit_code = cli_mod.main()
    assert exit_code == 0
    assert report_calls["n"] == 1, "the scheduled fallback must not re-run maintenance or write a report once the day is already complete"
