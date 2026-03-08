from __future__ import annotations

import json
import os
from pathlib import Path

import scripts.run_m13_live_loop as live


def test_m13_lock_acquire_and_release(tmp_path: Path):
    lock = tmp_path / "m13.lock"
    ok, reason = live._acquire_lock(lock, lock_stale_sec=60)
    assert ok is True
    assert reason == ""
    assert lock.exists()

    live._release_lock(lock)
    assert lock.exists() is False


def test_m13_lock_active_blocks_second_owner(monkeypatch, tmp_path: Path):
    lock = tmp_path / "m13.lock"
    lock.write_text(
        json.dumps({"pid": 99999, "started_epoch": 1000, "started_ts": "2026-03-05T00:00:00Z"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(live.time, "time", lambda: 1010.0)
    monkeypatch.setattr(live, "_pid_exists", lambda pid: True)

    ok, reason = live._acquire_lock(lock, lock_stale_sec=1800)
    assert ok is False
    assert reason == "lock_active"


def test_m13_lock_reclaims_dead_pid(monkeypatch, tmp_path: Path):
    lock = tmp_path / "m13.lock"
    lock.write_text(
        json.dumps({"pid": 77777, "started_epoch": 1000, "started_ts": "2026-03-05T00:00:00Z"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(live.time, "time", lambda: 1001.0)
    monkeypatch.setattr(live, "_pid_exists", lambda pid: False)

    ok, reason = live._acquire_lock(lock, lock_stale_sec=1800)
    assert ok is True
    assert reason == ""
    obj = json.loads(lock.read_text(encoding="utf-8"))
    assert int(obj.get("pid") or 0) == int(os.getpid())


def test_m13_session_hard_gate_defaults_true(monkeypatch):
    monkeypatch.delenv("M31_MOCK_EXAM_SESSION_HARD_GATE", raising=False)
    assert live._session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=False) is True


def test_m13_session_hard_gate_can_be_disabled_for_offhours(monkeypatch):
    monkeypatch.setenv("M31_MOCK_EXAM_SESSION_HARD_GATE", "true")
    assert live._session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=True) is False
