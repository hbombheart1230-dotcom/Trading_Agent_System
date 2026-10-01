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


# --- Process creation-time identity (2026-09-30 closeout strict-owner fix) --
#
# PID alone is not a safe long-term ownership proof -- PIDs are reused by
# the OS once a process exits. A real, OS-provided process creation
# timestamp (not a self-recorded wall-clock approximation, which could
# drift or be forged) lets a later reader distinguish "the same process
# that acquired the lock" from "a different process that happens to have
# been assigned the same PID afterward". This uses the same category of
# low-level OS facility already relied on by pid_exists() above (raw
# ctypes on Windows, no new dependency -- psutil is not installed in this
# venv, confirmed in conftest.py) plus the standard POSIX /proc technique
# for portability; if neither can be read, the identity is UNVERIFIABLE
# and callers must fail closed rather than guess.


def _process_start_identity(pid: int) -> str | None:
    if int(pid or 0) <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                process_query_limited_information,
                False,
                int(pid),
            )
            if not handle:
                return None
            try:
                creation_time = wintypes.FILETIME()
                exit_time = wintypes.FILETIME()
                kernel_time = wintypes.FILETIME()
                user_time = wintypes.FILETIME()
                ok = ctypes.windll.kernel32.GetProcessTimes(  # type: ignore[attr-defined]
                    handle,
                    ctypes.byref(creation_time),
                    ctypes.byref(exit_time),
                    ctypes.byref(kernel_time),
                    ctypes.byref(user_time),
                )
                if not ok:
                    return None
                value = (int(creation_time.dwHighDateTime) << 32) | int(creation_time.dwLowDateTime)
                if value <= 0:
                    return None
                return f"win:{value}"
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        except Exception:
            return None
    try:
        stat_path = f"/proc/{int(pid)}/stat"
        with open(stat_path, "r", encoding="utf-8") as file:
            content = file.read()
        # comm (field 2) may itself contain spaces/parens; everything after
        # the LAST ')' is state(3) ppid(4) ... starttime(22) ... in order.
        after_comm = content.rsplit(")", 1)[-1].split()
        starttime = after_comm[19]  # field 22 overall -> index 19 here
        if not str(starttime).strip():
            return None
        return f"posix:{starttime}"
    except Exception:
        return None


def _read_json_object(path: Path) -> Dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _is_strict_lock_well_formed(obj: Dict[str, Any]) -> bool:
    pid = to_int(obj.get("pid"), 0)
    identity = str(obj.get("process_start_identity") or "").strip()
    token = str(obj.get("owner_token") or "").strip()
    return pid > 0 and bool(identity) and bool(token)


def acquire_live_loop_lock(
    lock_path: Path,
    *,
    lock_stale_sec: int,
    current_pid: int | None = None,
    strict_owner_identity: bool = False,
    owner_token: str | None = None,
    trigger: str | None = None,
    target_day: str | None = None,
) -> Tuple[bool, str]:
    if not strict_owner_identity:
        # --- Existing m13 live-loop semantics, UNCHANGED -----------------
        # A lock held past lock_stale_sec is reclaimed even if its PID is
        # technically still alive. This age-based reclaim is intentionally
        # NOT applied when strict_owner_identity=True (see the strict
        # branch below) -- the 2026-09-30 closeout audit found this exact
        # behavior would let a genuinely still-running closeout lose its
        # own lock to a second trigger purely because it took longer than
        # the staleness window, which is unacceptable for closeout but is
        # left untouched here for the m13 live loop pending its own,
        # separate regression review.
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

    # --- Strict owner-identity mode (2026-09-30 closeout critical fix) ---
    #
    # Required invariant: a valid, identity-confirmed live owner must NEVER
    # lose the lock merely because elapsed time exceeds lock_stale_sec.
    # Ownership is proven by (pid, process_start_identity), not age. A lock
    # is only ever reclaimed when its owner is conclusively dead (pid no
    # longer exists) or conclusively a DIFFERENT process (pid reused, start
    # identity differs) -- never on a timer. If ownership cannot be
    # verified at all, this fails closed (rejects) rather than guessing.
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner_pid = int(current_pid or os.getpid())
    resolved_token = str(owner_token or "").strip()
    if not resolved_token:
        import uuid

        resolved_token = uuid.uuid4().hex
    my_identity = _process_start_identity(owner_pid)
    if not my_identity:
        # Cannot even establish our OWN process identity -- never claim an
        # ownership record we could not later prove or safely release.
        return False, "IDENTITY_UNVERIFIABLE"

    def _new_payload() -> Dict[str, Any]:
        now_epoch = int(time.time())
        return {
            "pid": owner_pid,
            "process_start_identity": my_identity,
            "owner_token": resolved_token,
            "acquired_at": now_epoch,
            "acquired_ts": datetime.now(timezone.utc).isoformat(),
            "target_day": str(target_day or ""),
            "trigger": str(trigger or ""),
        }

    if not lock_path.exists():
        try:
            with open(lock_path, "x", encoding="utf-8") as file:
                file.write(json.dumps(_new_payload(), ensure_ascii=False))
            return True, "ACQUIRED"
        except FileExistsError:
            return False, "lock_active"
        except Exception:
            return False, "lock_create_failed"

    obj = _read_json_object(lock_path)
    if obj is None or not _is_strict_lock_well_formed(obj):
        # Malformed/incomplete ownership record: FAIL CLOSED. Never
        # silently delete or reinterpret state we cannot conclusively
        # attribute to a live or dead owner.
        return False, "LOCK_METADATA_INVALID"

    existing_pid = to_int(obj.get("pid"), 0)
    existing_identity = str(obj.get("process_start_identity") or "")

    if not pid_exists(existing_pid):
        reclaim_reason = "DEAD_OWNER_RECLAIMED"
    else:
        current_identity = _process_start_identity(existing_pid)
        if current_identity is None:
            # PID is alive but its identity could not be verified -- do
            # not assume it is safe to steal; fail closed.
            return False, "IDENTITY_UNVERIFIABLE"
        if current_identity != existing_identity:
            # Same PID, different process (PID reuse) -- the original
            # owner is conclusively gone.
            reclaim_reason = "PID_REUSE_RECLAIMED"
        else:
            # Confirmed live, identity-matched owner. Age is diagnostic
            # only and never authorizes reclaim here.
            return False, "lock_active"

    # Reclaim path (dead owner or confirmed PID reuse). Serialize the
    # check-then-act sequence against a genuinely concurrent reclaim
    # attempt using the same exclusive-create atomicity this module
    # already relies on elsewhere, applied to a short-lived guard file --
    # not a new locking mechanism, the same primitive, used transiently.
    guard_path = lock_path.with_name(lock_path.name + ".reclaim-guard")
    try:
        guard_fh = open(guard_path, "x", encoding="utf-8")
    except FileExistsError:
        # Another process is deciding this exact reclaim right now --
        # do not race it; favor safety over liveness.
        return False, "lock_active"
    except Exception:
        return False, "lock_create_failed"
    try:
        # Re-read under the guard: the picture may have changed since our
        # first (unguarded) read above.
        obj2 = _read_json_object(lock_path)
        if obj2 is None or not _is_strict_lock_well_formed(obj2):
            return False, "LOCK_METADATA_INVALID"
        if obj2 != obj:
            return False, "lock_active"
        new_payload = _new_payload()
        tmp_path = lock_path.with_name(lock_path.name + f".tmp-{resolved_token}")
        try:
            tmp_path.write_text(json.dumps(new_payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, lock_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return True, reclaim_reason
    finally:
        try:
            guard_fh.close()
        except Exception:
            pass
        try:
            guard_path.unlink()
        except Exception:
            pass


def refresh_live_loop_lock(
    lock_path: Path,
    *,
    current_pid: int | None = None,
    strict_owner_identity: bool = False,
    owner_token: str | None = None,
) -> Tuple[bool, str]:
    if not strict_owner_identity:
        # --- Existing m13 live-loop semantics, UNCHANGED ------------------
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

    # --- Strict owner-identity mode (2026-10-02 M13/Docker PID-1 fix) -----
    #
    # Heartbeat recency plays NO role in strict mode's own reclaim decision
    # (acquire_live_loop_lock's strict branch only ever reclaims on a
    # conclusively dead pid or confirmed pid reuse -- never on age), so this
    # is best-effort observability only, never required for correctness.
    # Unlike the non-strict path above, a missing lock file is NOT silently
    # recreated here: under strict mode that would mean ownership was
    # already lost (reclaimed by a confirmed-dead/pid-reuse takeover, or
    # removed by this process's own release) and blindly re-establishing a
    # claim here could race a legitimate new owner. The caller's own
    # SQLite ownership-lease refresh (a separate, independent authority --
    # see run_live_loop's own comments) is what actually detects and acts
    # on a lost claim; this heartbeat is diagnostic metadata layered on an
    # already-held lock, never a second path to acquiring one.
    owner_pid = int(current_pid or os.getpid())
    resolved_token = str(owner_token or "").strip()
    if not lock_path.exists():
        return False, "LOCK_MISSING"
    obj = _read_json_object(lock_path)
    if obj is None or not _is_strict_lock_well_formed(obj):
        return False, "LOCK_METADATA_INVALID"
    existing_pid = to_int(obj.get("pid"), 0)
    existing_token = str(obj.get("owner_token") or "")
    existing_identity = str(obj.get("process_start_identity") or "")
    if not resolved_token or existing_pid != owner_pid or existing_token != resolved_token:
        return False, "non_owner_refresh_rejected"
    my_identity = _process_start_identity(owner_pid)
    if not my_identity or not existing_identity or my_identity != existing_identity:
        return False, "IDENTITY_UNVERIFIABLE"
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = dict(obj)
    payload["heartbeat_epoch"] = int(time.time())
    payload["heartbeat_ts"] = now_iso
    try:
        lock_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True, "lock_heartbeat_updated"
    except Exception:
        return False, "lock_refresh_failed"


def release_live_loop_lock(
    lock_path: Path,
    *,
    current_pid: int | None = None,
    strict_owner_identity: bool = False,
    owner_token: str | None = None,
) -> Tuple[bool, str]:
    if not strict_owner_identity:
        # --- Existing m13 live-loop semantics, UNCHANGED ------------------
        owner_pid = int(current_pid or os.getpid())
        try:
            if not lock_path.exists():
                return True, "noop_no_lock"
            existing_pid = 0
            try:
                obj = json.loads(lock_path.read_text(encoding="utf-8"))
                existing_pid = to_int(obj.get("pid"), 0)
            except Exception:
                existing_pid = 0
            if existing_pid > 0 and existing_pid != owner_pid and pid_exists(existing_pid):
                return False, "non_owner_release_rejected"
            lock_path.unlink()
            return True, "released"
        except Exception:
            return False, "release_failed"

    # --- Strict owner-identity mode ---------------------------------------
    # Release must prove ownership of the exact lock generation (pid +
    # process_start_identity + owner_token). A non-owner -- including a
    # reused PID, or a caller missing/mismatching its own owner_token --
    # must never delete another owner's lock, even if the lock file itself
    # changed between this caller's acquire and release.
    owner_pid = int(current_pid or os.getpid())
    resolved_token = str(owner_token or "").strip()
    try:
        if not lock_path.exists():
            return True, "noop_no_lock"
        obj = _read_json_object(lock_path)
        if obj is None:
            # Cannot verify ownership of unreadable/malformed content --
            # never touch it.
            return False, "non_owner_release_rejected"
        existing_pid = to_int(obj.get("pid"), 0)
        existing_token = str(obj.get("owner_token") or "")
        existing_identity = str(obj.get("process_start_identity") or "")
        if not resolved_token or existing_pid != owner_pid or existing_token != resolved_token:
            return False, "non_owner_release_rejected"
        my_identity = _process_start_identity(owner_pid)
        # Fail closed: release requires a POSITIVE, verified match of pid +
        # process_start_identity + owner_token. If either identity value is
        # missing/unverifiable (my_identity is None -- the OS facility
        # could not be read right now -- or existing_identity is absent
        # from the lock record), that is NOT proof of ownership and must
        # never be treated as a pass-through allowing unlink.
        if not my_identity or not existing_identity or my_identity != existing_identity:
            return False, "non_owner_release_rejected"
        lock_path.unlink()
        return True, "released"
    except Exception:
        return False, "release_failed"
