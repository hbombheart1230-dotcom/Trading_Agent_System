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


def test_m13_refresh_lock_recreates_missing_lock(tmp_path: Path):
    lock = tmp_path / "m13.lock"
    ok, reason = live._refresh_lock(lock)
    assert ok is True
    assert reason == "lock_recreated"
    obj = json.loads(lock.read_text(encoding="utf-8"))
    assert int(obj.get("pid") or 0) == int(os.getpid())
    assert int(obj.get("heartbeat_epoch") or 0) > 0


def test_m13_refresh_lock_updates_heartbeat_for_current_owner(monkeypatch, tmp_path: Path):
    lock = tmp_path / "m13.lock"
    lock.write_text(
        json.dumps({"pid": int(os.getpid()), "started_epoch": 1000, "started_ts": "2026-04-08T00:00:00Z"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(live.time, "time", lambda: 1015.0)
    ok, reason = live._refresh_lock(lock)
    assert ok is True
    assert reason == "lock_heartbeat_updated"
    obj = json.loads(lock.read_text(encoding="utf-8"))
    assert int(obj.get("pid") or 0) == int(os.getpid())
    assert int(obj.get("heartbeat_epoch") or 0) == 1015


def test_m13_release_lock_does_not_remove_foreign_live_owner(monkeypatch, tmp_path: Path):
    lock = tmp_path / "m13.lock"
    lock.write_text(
        json.dumps({"pid": 77777, "started_epoch": 1000, "started_ts": "2026-04-08T00:00:00Z"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(live, "_pid_exists", lambda pid: pid == 77777)
    live._release_lock(lock)
    assert lock.exists() is True


def test_m13_session_hard_gate_defaults_true(monkeypatch):
    monkeypatch.delenv("M31_MOCK_EXAM_SESSION_HARD_GATE", raising=False)
    assert live._session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=False) is True


def test_m13_session_hard_gate_can_be_disabled_for_offhours(monkeypatch):
    monkeypatch.setenv("M31_MOCK_EXAM_SESSION_HARD_GATE", "true")
    assert live._session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=True) is False


def test_m13_initial_state_keeps_tick_pipeline():
    st = live._build_initial_state("005930", tick_pipeline="integrated_chain")
    assert st["symbol"] == "005930"
    assert st["m13_tick_pipeline"] == "integrated_chain"
    assert st["auto_skill_runner"] is True


def test_m13_initial_state_normalizes_unknown_pipeline_to_legacy():
    st = live._build_initial_state("005930", tick_pipeline="unknown")
    assert st["m13_tick_pipeline"] == "legacy_m10"


def test_m13_initial_state_propagates_use_exit_policy_from_env(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    st = live._build_initial_state("005930", tick_pipeline="integrated_chain")
    assert st["use_exit_policy"] is True


def test_m13_resolve_env_path_prefers_cli_value(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENV_PATH", str(tmp_path / "ignored.env"))
    env_path = live._resolve_env_path(["--env-path", str(tmp_path / "custom.env")])
    assert env_path == (tmp_path / "custom.env")


def test_m13_resolve_env_path_uses_env_path_variable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENV_PATH", str(tmp_path / "from_env.env"))
    env_path = live._resolve_env_path([])
    assert env_path == (tmp_path / "from_env.env")
