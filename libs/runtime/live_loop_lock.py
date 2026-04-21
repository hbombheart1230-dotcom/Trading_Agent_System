from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from libs.runtime.entrypoint_common import to_int


def pid_exists(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
    except Exception:
        return False
    return True


def acquire_live_loop_lock(lock_path: Path, *, lock_stale_sec: int, current_pid: int | None = None) -> Tuple[bool, str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    stale = max(1, int(lock_stale_sec))
    owner_pid = int(current_pid or os.getpid())

    if lock_path.exists():
        obj: Dict[str, Any] = {}
        try:
            obj = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {}

        existing_pid = to_int(obj.get("pid"), 0)
        started_epoch = to_int(obj.get("started_epoch"), 0)
        if existing_pid > 0 and not pid_exists(existing_pid):
            try:
                lock_path.unlink()
            except Exception:
                return False, "lock_owner_dead_unlink_failed"
        else:
            age = max(0, now - started_epoch) if started_epoch > 0 else stale + 1
            if age <= stale:
                return False, "lock_active"
            try:
                lock_path.unlink()
            except Exception:
                return False, "lock_stale_unlink_failed"

    payload = {
        "pid": owner_pid,
        "started_epoch": now,
        "started_ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(lock_path, "x", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False))
        return True, ""
    except FileExistsError:
        return False, "lock_active"
    except Exception:
        return False, "lock_create_failed"


def refresh_live_loop_lock(lock_path: Path, *, current_pid: int | None = None) -> Tuple[bool, str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    owner_pid = int(current_pid or os.getpid())
    now_iso = datetime.now(timezone.utc).isoformat()
    current_payload = {
        "pid": owner_pid,
        "started_epoch": now,
        "started_ts": now_iso,
        "heartbeat_epoch": now,
        "heartbeat_ts": now_iso,
    }

    if not lock_path.exists():
        try:
            lock_path.write_text(json.dumps(current_payload, ensure_ascii=False), encoding="utf-8")
            return True, "lock_recreated"
        except Exception:
            return False, "lock_recreate_failed"

    existing: Dict[str, Any] = {}
    try:
        existing = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        existing = {}

    existing_pid = to_int(existing.get("pid"), 0)
    if existing_pid > 0 and existing_pid != owner_pid and pid_exists(existing_pid):
        return False, "lock_owned_by_other_process"

    payload = dict(existing or {})
    if existing_pid <= 0 or existing_pid != owner_pid:
        payload["pid"] = owner_pid
    if to_int(payload.get("started_epoch"), 0) <= 0:
        payload["started_epoch"] = now
    if not str(payload.get("started_ts") or "").strip():
        payload["started_ts"] = now_iso
    payload["heartbeat_epoch"] = now
    payload["heartbeat_ts"] = now_iso
    try:
        lock_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True, "lock_heartbeat_updated"
    except Exception:
        return False, "lock_refresh_failed"


def release_live_loop_lock(lock_path: Path, *, current_pid: int | None = None) -> None:
    owner_pid = int(current_pid or os.getpid())
    try:
        if not lock_path.exists():
            return
        existing_pid = 0
        try:
            obj = json.loads(lock_path.read_text(encoding="utf-8"))
            existing_pid = to_int(obj.get("pid"), 0)
        except Exception:
            existing_pid = 0
        if existing_pid > 0 and existing_pid != owner_pid and pid_exists(existing_pid):
            return
        lock_path.unlink()
    except Exception:
        return
