"""Regression coverage for scripts/check_daily_uef_run_status.py (HOST OPS
FINAL FIX, B3 -- missed-run visibility).

Read-only, operator-facing classifier: cross-references
scripts/run_daily_uef_evaluation.py's own durable START/END lifecycle events
(data/logs/events.jsonl) against a best-effort Windows Task Scheduler
cross-check to report one of SCHEDULED_AND_RAN / SCHEDULED_BUT_NOT_STARTED /
STARTED_AND_FAILED / STARTED_AND_COMPLETED. Never infers success from a
task merely being Enabled -- see module docstring.

All tests mock `_scheduler_cross_check` directly (no real PowerShell/Task
Scheduler dependency) and write directly to a tmp_path event log file.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_daily_uef_run_status import classify


def _write_events(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def _entrypoint_event(*, ts: str, event: str, target_day: str, **payload_extra) -> dict:
    return {
        "ts": ts,
        "stage": "daily_uef_evaluation_entrypoint",
        "event": event,
        "payload": {"target_day": target_day, **payload_extra},
    }


def _no_scheduler(monkeypatch):
    import scripts.check_daily_uef_run_status as mod

    monkeypatch.setattr(mod, "_scheduler_cross_check", lambda task_name, day: {"available": False, "reason": "test-mocked"})


def test_started_and_completed(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [
        _entrypoint_event(ts="2026-10-01T07:45:00+00:00", event="process_start", target_day="2026-10-01", pid=111),
        _entrypoint_event(ts="2026-10-01T07:46:00+00:00", event="process_end", target_day="2026-10-01", result="ok", exit_code=0),
    ])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "STARTED_AND_COMPLETED"


def test_started_and_failed_explicit_failure(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [
        _entrypoint_event(ts="2026-10-01T07:45:00+00:00", event="process_start", target_day="2026-10-01", pid=111),
        _entrypoint_event(ts="2026-10-01T07:46:00+00:00", event="process_end", target_day="2026-10-01", result="failed", exit_code=1, failure_reason="freshness check failed"),
    ])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "STARTED_AND_FAILED"


def test_started_and_failed_crash_no_end_event(tmp_path, monkeypatch):
    """Started but never reached its own end-of-run logging -- a crash or
    hang, not distinguishable from each other by this evidence alone, but
    both are correctly NOT STARTED_AND_COMPLETED."""
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [
        _entrypoint_event(ts="2026-10-01T07:45:00+00:00", event="process_start", target_day="2026-10-01", pid=111),
    ])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "STARTED_AND_FAILED"
    assert result["entrypoint_evidence"]["process_end"] is None


def test_scheduled_but_not_started_no_evidence_anywhere(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "SCHEDULED_BUT_NOT_STARTED"


def test_scheduled_but_not_started_missing_log_file(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    missing_path = tmp_path / "does_not_exist.jsonl"
    result = classify(day="2026-10-01", event_log_path=missing_path, task_name="x")
    assert result["status"] == "SCHEDULED_BUT_NOT_STARTED"


def test_scheduled_and_ran_when_scheduler_confirms_but_no_entrypoint_events(tmp_path, monkeypatch):
    """Exactly today's real-world case: the task fired and Task Scheduler
    recorded a clean exit, but the entrypoint's own durable logging was
    deployed only after that run already happened, so there is no
    entrypoint-level evidence yet. Must not be reported as
    SCHEDULED_BUT_NOT_STARTED (that would be misleading) nor as
    STARTED_AND_COMPLETED (that would overstate the entrypoint evidence
    actually available) -- SCHEDULED_AND_RAN names exactly this case."""
    import scripts.check_daily_uef_run_status as mod

    monkeypatch.setattr(
        mod, "_scheduler_cross_check",
        lambda task_name, day: {
            "available": True, "last_run_time": f"{day}T17:42:15+09:00",
            "last_run_matches_day": True, "last_task_result": 0, "last_task_result_ok": True,
            "next_run_time": "2026-10-02T16:45:00+09:00", "number_of_missed_runs": 0,
        },
    )
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "SCHEDULED_AND_RAN"


def test_latest_attempt_wins_when_a_day_has_a_failed_retry_then_success(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [
        _entrypoint_event(ts="2026-10-01T07:40:00+00:00", event="process_start", target_day="2026-10-01", pid=100),
        _entrypoint_event(ts="2026-10-01T07:40:30+00:00", event="process_end", target_day="2026-10-01", result="failed", exit_code=1),
        _entrypoint_event(ts="2026-10-01T07:50:00+00:00", event="process_start", target_day="2026-10-01", pid=200),
        _entrypoint_event(ts="2026-10-01T07:50:45+00:00", event="process_end", target_day="2026-10-01", result="ok", exit_code=0),
    ])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "STARTED_AND_COMPLETED"
    assert result["entrypoint_evidence"]["process_start"]["pid"] == 200


def test_other_days_events_are_ignored(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    _write_events(log_path, [
        _entrypoint_event(ts="2026-09-30T07:45:00+00:00", event="process_start", target_day="2026-09-30", pid=1),
        _entrypoint_event(ts="2026-09-30T07:46:00+00:00", event="process_end", target_day="2026-09-30", result="ok", exit_code=0),
    ])
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "SCHEDULED_BUT_NOT_STARTED"


def test_non_entrypoint_lines_and_malformed_lines_are_skipped_safely(tmp_path, monkeypatch):
    _no_scheduler(monkeypatch)
    log_path = tmp_path / "events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"stage": "closeout_maintenance", "event": "stage_start", "payload": {}}) + "\n")
        f.write("{not valid json at all\n")
        f.write(json.dumps(_entrypoint_event(ts="2026-10-01T07:45:00+00:00", event="process_start", target_day="2026-10-01", pid=1)) + "\n")
        f.write(json.dumps(_entrypoint_event(ts="2026-10-01T07:46:00+00:00", event="process_end", target_day="2026-10-01", result="ok", exit_code=0)) + "\n")
    result = classify(day="2026-10-01", event_log_path=log_path, task_name="x")
    assert result["status"] == "STARTED_AND_COMPLETED"
