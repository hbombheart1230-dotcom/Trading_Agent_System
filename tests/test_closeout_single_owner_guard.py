"""Regression coverage for the 2026-09-30 closeout single-owner guard.

Bounded safety fix (independent of the still-unknown 09/28 hang and 09/29
abnormal-termination causes, neither of which is claimed fixed here): the
tick-loop closeout trigger (libs/runtime/market_status_closeout.py) and the
scheduled-fallback CLI (scripts/run_closeout_maintenance.py) both used to
call run_closeout_maintenance() directly, with no coordination -- nothing
prevented both from executing concurrently and writing the same dated
report/artifact paths at once. run_closeout_maintenance_with_lock() (in
libs/reporting/closeout_maintenance.py) adds a single-owner guard by
reusing this repository's existing PID-based lock primitive
(libs/runtime/live_loop_lock.py, already proven for the m13 live loop's
own single-instance guard) -- not a new locking framework.

All synchronization here is deterministic (pre-acquiring the lock with an
explicit current_pid, or pre-writing a lock file by hand) -- no sleep-based
timing tests, per explicit instruction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from libs.reporting.closeout_maintenance import run_closeout_maintenance_with_lock
from libs.runtime.live_loop_lock import acquire_live_loop_lock


def _read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ownership_events(log_path: Path) -> list[dict]:
    """log_closeout_stage() always writes stage="closeout_maintenance" at
    the top level (the EventLogger's own stage field); the caller-supplied
    stage name lands in payload["closeout_stage"], and the phase lands in
    the event name as f"stage_{phase}"."""
    return [e for e in _read_events(log_path) if e.get("payload", {}).get("closeout_stage") == "closeout_ownership"]


def _phase(event: dict) -> str:
    return str(event.get("event") or "").removeprefix("stage_")


# --- Concurrent triggers: exactly one enters closeout -----------------------


def test_second_concurrent_trigger_is_rejected_as_already_running(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    # Deterministically simulate a genuinely concurrent owner (a different
    # pid) already holding the lock -- no threading/sleep required.
    other_pid = os.getpid() + 1
    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=1800, current_pid=other_pid)
    assert acquired is True
    assert reason == ""

    calls = {"n": 0}

    def _boom_if_called(**_kwargs):
        calls["n"] += 1
        raise AssertionError("run_closeout_maintenance must not be called when ownership is not acquired")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_if_called)

    result = run_closeout_maintenance_with_lock(
        day="2026-09-30", trigger="kiwoom_market_status_4", run_id="tick-2026-09-30", lock_path=lock_path,
    )

    assert calls["n"] == 0
    assert result["skipped"] is True
    assert result["skip_reason"] == "ALREADY_RUNNING"
    assert result["ok"] is False
    assert result["steps"] == {}

    events = _ownership_events(log_path)
    reject_events = [e for e in events if _phase(e) == "reject"]
    assert len(reject_events) == 1
    assert reject_events[0]["payload"]["trigger"] == "kiwoom_market_status_4"
    assert reject_events[0]["payload"]["skip_reason"] == "ALREADY_RUNNING"
    assert reject_events[0]["payload"]["active_owner_pid"] == other_pid


def test_no_execution_side_effect_when_ownership_rejected(tmp_path, monkeypatch):
    """No broker/order/execution side effect anywhere in the rejected path."""
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"
    acquire_live_loop_lock(lock_path, lock_stale_sec=1800, current_pid=os.getpid() + 1)

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path)
    assert result["skipped"] is True
    # A rejected run never even imports the underlying closeout function's
    # module-level dependencies beyond what this module already imports at
    # load time -- confirmed structurally by the import-scan test below.


# --- Normal completion releases the lock -------------------------------------


def test_normal_completion_releases_lock(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    def _fake_run_closeout_maintenance(**kwargs):
        return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}

    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance", _fake_run_closeout_maintenance
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", trigger="kiwoom_market_status_4", lock_path=lock_path)

    assert result["ok"] is True
    assert not result.get("skipped")
    assert not lock_path.exists()

    # A subsequent acquire succeeds immediately -- the lock is genuinely free.
    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=1800)
    assert acquired is True
    assert reason == ""

    events = _ownership_events(log_path)
    phases = [_phase(e) for e in events]
    assert phases == ["acquire", "release"]
    assert events[0]["payload"]["owner_pid"] == os.getpid()
    assert events[1]["payload"]["owner_pid"] == os.getpid()


# --- Exception during the guarded call still releases the lock --------------


def test_exception_during_closeout_still_releases_lock(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    def _boom(**_kwargs):
        raise RuntimeError("simulated closeout maintenance failure")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom)

    with pytest.raises(RuntimeError, match="simulated closeout maintenance failure"):
        run_closeout_maintenance_with_lock(day="2026-09-30", trigger="kiwoom_market_status_4", lock_path=lock_path)

    assert not lock_path.exists()

    events = _ownership_events(log_path)
    phases = [_phase(e) for e in events]
    assert phases == ["acquire", "release"]


# --- Later explicit retry after an earlier failure is permitted -------------


def test_later_explicit_retry_after_failure_is_permitted(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    def _boom(**_kwargs):
        raise RuntimeError("simulated closeout maintenance failure")

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom)
    with pytest.raises(RuntimeError):
        run_closeout_maintenance_with_lock(day="2026-09-30", trigger="manual_retry_1", lock_path=lock_path)

    def _succeed(**kwargs):
        return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance", _succeed)
    result = run_closeout_maintenance_with_lock(day="2026-09-30", trigger="manual_retry_2", lock_path=lock_path)

    assert result["ok"] is True
    assert not result.get("skipped")
    assert not lock_path.exists()


# --- Dead/stale owner is recoverable -----------------------------------------


def test_dead_owner_lock_is_reclaimed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    # A pid essentially guaranteed not to correspond to a live process.
    dead_pid = 999999
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": dead_pid, "started_epoch": 0, "started_ts": "1970-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )

    def _fake_run_closeout_maintenance(**kwargs):
        return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}

    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance", _fake_run_closeout_maintenance
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path)

    assert result["ok"] is True
    assert not result.get("skipped")


def test_stale_owner_lock_past_staleness_window_is_reclaimed(tmp_path, monkeypatch):
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    lock_path = tmp_path / "closeout_maintenance.lock"

    # A live pid (this test process itself) but started far in the past --
    # exercises the staleness-window reclaim path even though the pid is
    # technically still alive.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": os.getpid(), "started_epoch": 0, "started_ts": "1970-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )

    def _fake_run_closeout_maintenance(**kwargs):
        return {"schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": True, "steps": {}}

    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance", _fake_run_closeout_maintenance
    )

    result = run_closeout_maintenance_with_lock(day="2026-09-30", lock_path=lock_path, lock_stale_sec=1800)

    assert result["ok"] is True
    assert not result.get("skipped")


# --- Callers skip report writing on ownership rejection (race avoidance) ----


def test_market_status_trigger_skips_report_write_when_ownership_rejected(tmp_path, monkeypatch):
    """When another owner holds the closeout lock, the tick-loop trigger must
    not write a report itself -- that could race against whatever the real
    owner is concurrently writing to the same dated path."""
    import libs.runtime.market_status_closeout as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    monkeypatch.setattr(
        mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {"event_id": "evt-skip-1", "received_at": "2026-09-30T06:30:00+00:00", "code": "4"}
            ],
        },
    )

    def _fake_with_lock(**kwargs):
        return {
            "schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": False,
            "skipped": True, "skip_reason": "ALREADY_RUNNING", "steps": {},
        }

    monkeypatch.setattr("libs.reporting.closeout_maintenance.run_closeout_maintenance_with_lock", _fake_with_lock)

    report_calls = {"n": 0}
    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.write_closeout_maintenance_report",
        lambda *a, **k: report_calls.__setitem__("n", report_calls["n"] + 1) or {},
    )

    state = {"persisted_state": {}}
    out_state = mod.apply_market_status_closeout_events(state)

    assert report_calls["n"] == 0
    persisted = out_state["persisted_state"]
    assert "evt-skip-1" in persisted["processed_market_status_event_ids"]
    # The action itself was not recorded as processed -- a genuine concurrent
    # skip must not permanently prevent a later legitimate retry.
    assert persisted.get("processed_market_status_action_keys") == []


def test_fallback_cli_skips_report_write_when_ownership_rejected(tmp_path, monkeypatch):
    """Same race-avoidance rule applies to the scheduled-fallback CLI: a
    skipped (ALREADY_RUNNING) run must not write a report, and must exit
    cleanly (0), since this is an expected outcome of the guard, not a
    failure."""
    import scripts.run_closeout_maintenance as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    monkeypatch.setattr(sys, "argv", ["run_closeout_maintenance.py", "--day", "2026-09-30"])

    def _fake_with_lock(**kwargs):
        return {
            "schema_version": "closeout_maintenance.v1", "day": kwargs["day"], "ok": False,
            "skipped": True, "skip_reason": "ALREADY_RUNNING", "steps": {},
        }

    monkeypatch.setattr(mod, "run_closeout_maintenance_with_lock", _fake_with_lock)

    report_calls = {"n": 0}
    monkeypatch.setattr(
        mod, "write_closeout_maintenance_report",
        lambda *a, **k: report_calls.__setitem__("n", report_calls["n"] + 1) or {},
    )

    exit_code = mod.main()

    assert exit_code == 0
    assert report_calls["n"] == 0


# --- No broker/order/execution side effect -----------------------------------


def test_single_owner_guard_never_imports_execution_or_broker_modules():
    import ast
    import inspect

    import libs.reporting.closeout_maintenance as closeout_mod

    forbidden = ("libs.execution", "libs.read.kiwoom_order", "libs.runtime.live_loop_runner")
    tree = ast.parse(inspect.getsource(closeout_mod.run_closeout_maintenance_with_lock))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert not name.startswith(forbidden), f"run_closeout_maintenance_with_lock must never import {name!r}"
