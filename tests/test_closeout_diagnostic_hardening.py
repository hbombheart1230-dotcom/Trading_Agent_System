"""Regression coverage for the 2026-09-30 closeout diagnostic hardening.

Observability-only change (no behavioral fix): a caught exception inside
the tick-loop market-status-closeout path, and any exception inside the
scheduled-fallback CLI entrypoint, must now leave a durable trace (full
traceback, target day, and identifying context) via the existing
EventLogger (data/logs/events.jsonl) -- the previous behavior left no
trace at all, because the tick loop only ever stored the error in
state["market_status_closeout_error"], a field save_state() never
persists. Diagnostic logging itself must never raise a secondary
exception, and must never touch any broker/order/execution path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def _read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- Tick-loop path: caught exceptions retain a durable traceback ----------


def test_market_status_closeout_action_exception_logs_durable_traceback(tmp_path, monkeypatch):
    import libs.runtime.market_status_closeout as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    monkeypatch.setattr(
        mod, "load_market_status",
        lambda: {
            "current": {},
            "events": [
                {
                    "event_id": "evt-1",
                    "received_at": "2026-09-29T06:30:00+00:00",
                    "code": "4",  # REGULAR_CLOSE_CODES
                }
            ],
        },
    )

    def _boom_run_closeout_maintenance(**_kwargs):
        raise RuntimeError("simulated closeout maintenance failure")

    monkeypatch.setattr(
        "libs.reporting.closeout_maintenance.run_closeout_maintenance", _boom_run_closeout_maintenance
    )

    class _FixedNow:
        @staticmethod
        def now(_tz=None):
            import datetime as _dt

            return _dt.datetime(2026, 9, 29, 15, 30, tzinfo=mod.KST)

    monkeypatch.setattr(mod, "datetime", _FixedNow)

    state = {"persisted_state": {}}
    with pytest.raises(RuntimeError, match="simulated closeout maintenance failure"):
        mod.apply_market_status_closeout_events(state)

    events = _read_events(log_path)
    exception_events = [e for e in events if e["stage"] == "market_status_closeout" and e["event"] == "exception"]
    assert len(exception_events) == 1
    payload = exception_events[0]["payload"]
    assert payload["exception_type"] == "RuntimeError"
    assert "simulated closeout maintenance failure" in payload["exception_message"]
    assert "Traceback" in payload["traceback"] or "raise RuntimeError" in payload["traceback"]
    assert payload["event_id"] == "evt-1"
    assert payload["code"] == "4"
    assert payload["function"] == "apply_market_status_closeout_events"


def test_tick_loop_backstop_logs_exception_and_preserves_existing_error_field(tmp_path, monkeypatch):
    from graphs.pipelines.m13_live_loop import run_m13_once

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    def _boom_market_status_fn(state):
        raise ValueError("simulated market-status-closeout failure")

    calls = {"tick": 0, "eod": 0, "save": 0}

    def _load_state_fn(state):
        return state

    def _tick_fn(state, dt=None):
        calls["tick"] += 1
        return state

    def _eod_fn(state, dt=None):
        calls["eod"] += 1
        return state

    def _save_state_fn(state):
        calls["save"] += 1
        return state

    out_state = run_m13_once(
        {"run_id": "test-run-1"},
        load_state_fn=_load_state_fn,
        save_state_fn=_save_state_fn,
        tick_fn=_tick_fn,
        eod_fn=_eod_fn,
        market_status_fn=_boom_market_status_fn,
    )

    # Existing containment preserved: the tick loop itself never crashes,
    # and continues to tick/eod/save normally.
    assert calls == {"tick": 1, "eod": 1, "save": 1}
    assert "ValueError" in out_state.get("market_status_closeout_error", "")

    events = _read_events(log_path)
    tick_exceptions = [e for e in events if e["stage"] == "market_status_closeout" and e["event"] == "tick_exception"]
    assert len(tick_exceptions) == 1
    assert tick_exceptions[0]["payload"]["exception_type"] == "ValueError"
    assert "simulated market-status-closeout failure" in tick_exceptions[0]["payload"]["exception_message"]


# --- Fallback CLI entrypoint: lifecycle + failure logging -------------------


def test_fallback_entrypoint_logs_lifecycle_on_success(tmp_path, monkeypatch):
    from libs.reporting.closeout_maintenance import log_closeout_stage

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    log_closeout_stage(run_id="test-run", day="2026-09-29", stage="account_snapshot", phase="start")
    log_closeout_stage(run_id="test-run", day="2026-09-29", stage="run_closeout_maintenance", phase="end", detail={"ok": True})

    events = _read_events(log_path)
    assert any(e["event"] == "stage_start" and e["payload"]["closeout_stage"] == "account_snapshot" for e in events)
    assert any(e["event"] == "stage_end" and e["payload"]["ok"] is True for e in events)


def test_fallback_entrypoint_logs_lifecycle_helper(tmp_path, monkeypatch):
    import scripts.run_closeout_maintenance as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))

    mod._log_lifecycle(run_id="cli-test", day="2026-09-29", event="process_start", detail={"trigger": "test"})
    mod._log_lifecycle(
        run_id="cli-test", day="2026-09-29", event="process_exception", level="error",
        detail={"exception_type": "RuntimeError", "exception_message": "boom", "traceback": "Traceback...\nRuntimeError: boom"},
    )

    events = _read_events(log_path)
    assert any(e["event"] == "process_start" for e in events)
    exc_events = [e for e in events if e["event"] == "process_exception"]
    assert len(exc_events) == 1
    assert exc_events[0]["level"] == "error"
    assert exc_events[0]["payload"]["exception_type"] == "RuntimeError"
    assert "boom" in exc_events[0]["payload"]["traceback"]


def test_fallback_entrypoint_main_logs_process_exception_and_reraises(tmp_path, monkeypatch):
    import scripts.run_closeout_maintenance as mod

    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENT_LOG_PATH", str(log_path))
    monkeypatch.setattr(sys, "argv", ["run_closeout_maintenance.py", "--day", "2026-09-29"])

    def _boom(**_kwargs):
        raise RuntimeError("simulated fallback failure")

    monkeypatch.setattr(mod, "run_closeout_maintenance_with_lock", _boom)

    with pytest.raises(RuntimeError, match="simulated fallback failure"):
        mod.main()

    events = _read_events(log_path)
    assert any(e["event"] == "process_start" for e in events)
    assert any(e["event"] == "closeout_start" for e in events)
    exc_events = [e for e in events if e["event"] == "process_exception"]
    assert len(exc_events) == 1
    assert exc_events[0]["payload"]["exception_type"] == "RuntimeError"
    assert "simulated fallback failure" in exc_events[0]["payload"]["exception_message"]
    assert "traceback" in exc_events[0]["payload"]
    exit_events = [e for e in events if e["event"] == "process_exit"]
    assert len(exit_events) == 1
    assert exit_events[0]["payload"]["exit_code"] == 1
    assert exit_events[0]["payload"]["reason"] == "exception"


# --- Diagnostic logging never raises secondary exceptions -------------------


def test_log_closeout_stage_never_raises_even_if_event_logger_broken(monkeypatch):
    from libs.reporting.closeout_maintenance import log_closeout_stage

    def _boom_event_logger(*_a, **_k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("libs.core.event_logger.EventLogger", _boom_event_logger)

    # Must not raise, regardless of the underlying logger being broken.
    log_closeout_stage(run_id="x", day="2026-09-29", stage="account_snapshot", phase="start")


def test_market_status_closeout_exception_logger_never_raises_even_if_broken(monkeypatch):
    from libs.runtime.market_status_closeout import _log_market_status_closeout_exception

    def _boom_event_logger(*_a, **_k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("libs.core.event_logger.EventLogger", _boom_event_logger)

    _log_market_status_closeout_exception(
        RuntimeError("inner"), day="2026-09-29", event_id="e1", code="4", action_key="2026-09-29:regular_close",
        trigger="test",
    )


def test_fallback_lifecycle_logger_never_raises_even_if_broken(monkeypatch):
    import scripts.run_closeout_maintenance as mod

    def _boom_event_logger(*_a, **_k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("libs.core.event_logger.EventLogger", _boom_event_logger)

    mod._log_lifecycle(run_id="x", day="2026-09-29", event="process_start")


# --- No broker/order path invoked by diagnostics -----------------------------


def test_diagnostic_helpers_never_import_execution_or_broker_modules():
    import ast
    import inspect

    import libs.reporting.closeout_maintenance as closeout_mod
    import libs.runtime.market_status_closeout as market_status_mod
    import scripts.run_closeout_maintenance as cli_mod

    forbidden = ("libs.execution", "libs.read.kiwoom_order", "libs.runtime.live_loop_runner")
    for source_mod, fn_name in (
        (closeout_mod, "log_closeout_stage"),
        (market_status_mod, "_log_market_status_closeout_exception"),
        (cli_mod, "_log_lifecycle"),
    ):
        tree = ast.parse(inspect.getsource(getattr(source_mod, fn_name)))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            assert not name.startswith(forbidden), f"{fn_name} must never import {name!r}"
