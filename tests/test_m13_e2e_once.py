from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import os

from graphs.pipelines.m13_live_loop import run_m13_once

KST = timezone(timedelta(hours=9))


def test_m13_e2e_once(tmp_path: Path, monkeypatch):
    # isolate paths
    events = tmp_path / "events.jsonl"
    reports = tmp_path / "reports"
    state_store = tmp_path / "state.json"

    monkeypatch.setenv("EVENT_LOG_PATH", str(events))
    monkeypatch.setenv("REPORT_DIR", str(reports))
    monkeypatch.setenv("STATE_STORE_PATH", str(state_store))

    # inject deterministic fns
    calls = []
    def load_fn(state):
        calls.append("load")
        state["loaded"] = True
        return state

    def tick_fn(state, dt=None):
        calls.append("tick")
        # emulate a tick result
        state.setdefault("execution", {})
        state["execution"]["allowed"] = True
        # write a minimal event line as if execution happened
        events.parent.mkdir(parents=True, exist_ok=True)
        with open(events, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int((dt).timestamp()), "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}) + "\n")
        return state

    def eod_fn(state, dt=None):
        calls.append("eod")
        # emulate report generation marker
        reports.mkdir(parents=True, exist_ok=True)
        (reports/"2026-02-11.md").write_text("# report", encoding="utf-8")
        return state

    def save_fn(state):
        calls.append("save")
        with open(state_store, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return state

    dt = datetime(2026, 2, 11, 15, 36, tzinfo=KST)
    out = run_m13_once({}, dt=dt, load_state_fn=load_fn, save_state_fn=save_fn, tick_fn=lambda s, dt=None: tick_fn(s, dt=dt), eod_fn=lambda s, dt=None: eod_fn(s, dt=dt))

    assert calls == ["load", "tick", "eod", "save"]
    assert out["loaded"] is True
    assert state_store.exists()
    assert reports.exists()
