from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.entrypoint_common import to_int
from libs.runtime.live_loop_lock import pid_exists
from libs.runtime.live_loop_process_query import query_live_loop_processes, read_lock_owner_pid


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _tail_text(path: Path, *, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[-max(1, int(max_chars)) :]


def _runtime_python(root: Path) -> str:
    candidate = root / "venv" / "Scripts" / "python.exe"
    if candidate.exists():
        return str(candidate)
    return sys.executable or "python"


def _session_status(root: Path, lock_path: Path) -> Dict[str, Any]:
    lock_payload = _read_json(lock_path)
    lock_pid = read_lock_owner_pid(lock_path)
    processes = query_live_loop_processes(root, lock_path)
    return {
        "lock_path": str(lock_path),
        "lock_exists": lock_path.exists(),
        "lock_pid": int(lock_pid),
        "lock_pid_alive": bool(lock_pid and pid_exists(lock_pid)),
        "heartbeat_epoch": to_int(lock_payload.get("heartbeat_epoch"), 0),
        "heartbeat_ts": str(lock_payload.get("heartbeat_ts") or ""),
        "session_process_count": len(processes),
        "session_pids": [int(row.get("pid") or 0) for row in processes],
        "session_processes": processes,
    }


def _stop_pid(pid: int) -> Dict[str, Any]:
    if int(pid or 0) <= 0:
        return {"pid": int(pid or 0), "ok": False, "reason": "invalid_pid"}
    if os.name == "nt":
        cmd = ["taskkill", "/PID", str(int(pid)), "/F"]
    else:
        cmd = ["kill", "-TERM", str(int(pid))]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {
            "pid": int(pid),
            "ok": int(cp.returncode) == 0 or not pid_exists(pid),
            "returncode": int(cp.returncode),
            "stdout": (cp.stdout or "").strip()[-500:],
            "stderr": (cp.stderr or "").strip()[-500:],
        }
    except Exception as ex:
        return {"pid": int(pid), "ok": not pid_exists(pid), "error": f"{type(ex).__name__}: {ex}"}


def _stop_existing_session(root: Path, lock_path: Path, *, wait_sec: int) -> Dict[str, Any]:
    before = _session_status(root, lock_path)
    processes = before.get("session_processes") if isinstance(before.get("session_processes"), list) else []
    pids = [int(row.get("pid") or 0) for row in processes if int(row.get("pid") or 0) > 0]
    pids = [pid for pid in dict.fromkeys(pids) if pid != os.getpid()]
    parent_by_pid = {
        int(row.get("pid") or 0): int(row.get("parent_pid") or 0)
        for row in processes
        if int(row.get("pid") or 0) > 0
    }
    pids.sort(key=lambda pid: (parent_by_pid.get(pid) in set(pids), pid), reverse=True)

    stop_results = [_stop_pid(pid) for pid in pids]
    deadline = time.time() + max(1, int(wait_sec))
    remaining: List[Dict[str, Any]] = []
    while time.time() < deadline:
        remaining = query_live_loop_processes(root, lock_path)
        if not remaining:
            break
        time.sleep(0.5)

    lock_removed = False
    lock_remove_reason = ""
    lock_pid = read_lock_owner_pid(lock_path)
    stopped_pids = {int(row.get("pid") or 0) for row in stop_results}
    if lock_path.exists() and (
        lock_pid <= 0
        or lock_pid in stopped_pids
        or not pid_exists(lock_pid)
        or not query_live_loop_processes(root, lock_path)
    ):
        try:
            lock_path.unlink()
            lock_removed = True
            lock_remove_reason = "old_session_stopped"
        except Exception as ex:
            lock_remove_reason = f"unlink_failed:{type(ex).__name__}"

    return {
        "before": before,
        "stop_results": stop_results,
        "remaining_processes": remaining,
        "lock_removed": lock_removed,
        "lock_remove_reason": lock_remove_reason,
    }


def _start_session(args: argparse.Namespace, root: Path, lock_path: Path) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_tag = str(args.log_tag or "clean_restart").strip() or "clean_restart"
    log_base = f"run_session_live_intraday_{log_tag}_{timestamp}"
    log_dir = root / "reports" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{log_base}.out.log"
    stderr_path = log_dir / f"{log_base}.err.log"

    cmd = [
        _runtime_python(root),
        str(root / "scripts" / "run_session.py"),
        "--mode",
        "live",
        "--phase",
        "intraday",
        "--env-path",
        str(root / str(args.env_path or ".env")),
        "--tick-pipeline",
        str(args.tick_pipeline),
        "--sleep-sec",
        str(int(args.sleep_sec)),
        "--lock-path",
        str(lock_path),
        "--lock-stale-sec",
        str(int(args.lock_stale_sec)),
    ]
    if bool(args.allow_offhours):
        cmd.append("--allow-offhours")
    if bool(args.session_hard_gate):
        cmd.append("--session-hard-gate")

    stdout_file = stdout_path.open("ab")
    stderr_file = stderr_path.open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        stdout_file.close()
        stderr_file.close()

    return {
        "launcher_pid": int(proc.pid),
        "command": cmd,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _wait_for_healthy_start(
    root: Path,
    lock_path: Path,
    *,
    launcher_pid: int,
    stderr_path: Path,
    wait_sec: int,
) -> Dict[str, Any]:
    deadline = time.time() + max(1, int(wait_sec))
    last_status: Dict[str, Any] = {}
    while time.time() < deadline:
        last_status = _session_status(root, lock_path)
        lock_pid = int(last_status.get("lock_pid") or 0)
        if lock_pid > 0 and bool(last_status.get("lock_pid_alive")) and int(last_status.get("session_process_count") or 0) > 0:
            break
        if launcher_pid > 0 and not pid_exists(launcher_pid):
            break
        time.sleep(0.5)
    stderr_size = stderr_path.stat().st_size if stderr_path.exists() else 0
    last_status = last_status or _session_status(root, lock_path)
    return {
        "healthy": bool(
            int(last_status.get("lock_pid") or 0) > 0
            and bool(last_status.get("lock_pid_alive"))
            and int(last_status.get("session_process_count") or 0) > 0
            and int(stderr_size) == 0
        ),
        "status": last_status,
        "stderr_size": int(stderr_size),
        "stderr_tail": _tail_text(stderr_path) if int(stderr_size) > 0 else "",
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stop stale live loop state and start one clean live intraday session.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--lock-path", default=os.getenv("M13_LIVE_LOCK_PATH", "data/state/m13_live_loop.lock"))
    p.add_argument("--lock-stale-sec", type=int, default=to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800))
    p.add_argument("--tick-pipeline", choices=["legacy_m10", "integrated_chain"], default="integrated_chain")
    p.add_argument("--sleep-sec", type=int, default=30)
    p.add_argument("--allow-offhours", dest="allow_offhours", action="store_true", default=True)
    p.add_argument("--no-allow-offhours", dest="allow_offhours", action="store_false")
    p.add_argument("--session-hard-gate", action="store_true")
    p.add_argument("--stop-wait-sec", type=int, default=15)
    p.add_argument("--start-wait-sec", type=int, default=20)
    p.add_argument("--log-tag", default="clean_restart")
    p.add_argument("--status-only", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _render_text(result: Dict[str, Any]) -> str:
    if result.get("status_only"):
        status = result.get("status") if isinstance(result.get("status"), dict) else {}
        return "\n".join(
            [
                f"live_status={'running' if status.get('lock_pid_alive') else 'not_running'}",
                f"lock_pid={status.get('lock_pid')}",
                f"heartbeat_ts={status.get('heartbeat_ts') or '-'}",
                f"session_pids={status.get('session_pids')}",
            ]
        )
    start = result.get("start") if isinstance(result.get("start"), dict) else {}
    health = result.get("health") if isinstance(result.get("health"), dict) else {}
    status = health.get("status") if isinstance(health.get("status"), dict) else {}
    return "\n".join(
        [
            f"ok={bool(result.get('ok'))}",
            f"lock_pid={status.get('lock_pid')}",
            f"heartbeat_ts={status.get('heartbeat_ts') or '-'}",
            f"session_pids={status.get('session_pids')}",
            f"stdout={start.get('stdout_path')}",
            f"stderr={start.get('stderr_path')} size={health.get('stderr_size')}",
        ]
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    root = ROOT
    lock_path = Path(str(args.lock_path or "data/state/m13_live_loop.lock"))
    if not lock_path.is_absolute():
        lock_path = root / lock_path

    if bool(args.status_only):
        result = {"ok": True, "status_only": True, "status": _session_status(root, lock_path)}
        print(json.dumps(result, ensure_ascii=False, indent=2) if bool(args.json) else _render_text(result))
        return 0

    stop = _stop_existing_session(root, lock_path, wait_sec=int(args.stop_wait_sec))
    if stop.get("remaining_processes"):
        result = {"ok": False, "error": "live_session_processes_still_running", "stop": stop}
        print(json.dumps(result, ensure_ascii=False, indent=2) if bool(args.json) else _render_text(result))
        return 2

    start = _start_session(args, root, lock_path)
    health = _wait_for_healthy_start(
        root,
        lock_path,
        launcher_pid=int(start.get("launcher_pid") or 0),
        stderr_path=Path(str(start.get("stderr_path") or "")),
        wait_sec=int(args.start_wait_sec),
    )
    result = {"ok": bool(health.get("healthy")), "stop": stop, "start": start, "health": health}
    print(json.dumps(result, ensure_ascii=False, indent=2) if bool(args.json) else _render_text(result))
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
