import json
from pathlib import Path

from libs.runtime.live_loop_lock import (
    acquire_live_loop_lock,
    refresh_live_loop_lock,
    release_live_loop_lock,
)


def test_acquire_live_loop_lock_creates_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "loop.lock"
    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=30, current_pid=1234)
    assert acquired is True
    assert reason == ""
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == 1234


def test_refresh_live_loop_lock_updates_heartbeat(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "loop.lock"
    acquire_live_loop_lock(lock_path, lock_stale_sec=30, current_pid=1234)
    refreshed, reason = refresh_live_loop_lock(lock_path, current_pid=1234)
    assert refreshed is True
    assert reason == "lock_heartbeat_updated"
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == 1234
    assert "heartbeat_ts" in payload


def test_release_live_loop_lock_removes_owned_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "loop.lock"
    acquire_live_loop_lock(lock_path, lock_stale_sec=30, current_pid=1234)
    release_live_loop_lock(lock_path, current_pid=1234)
    assert not lock_path.exists()
