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
from pathlib import Path

import pytest

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
