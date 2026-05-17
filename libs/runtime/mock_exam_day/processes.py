from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from libs.runtime.live_loop_process_query import query_live_loop_processes
from libs.runtime.mock_exam_day.common import to_int, utc_now_iso
from libs.runtime.runtime_output_helpers import tail_text

ROOT = Path(__file__).resolve().parents[3]


def run_subprocess(
    *,
    step_id: str,
    command: Sequence[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: int = 1800,
) -> Dict[str, Any]:
    started_at = utc_now_iso()
    t0 = time.time()
    out: Dict[str, Any] = {
        "step_id": str(step_id),
        "command": [str(x) for x in command],
        "cwd": str(cwd),
        "started_at": started_at,
        "rc": 1,
        "ok": False,
        "stdout_tail": "",
        "stderr_tail": "",
        "error": "",
        "duration_sec": 0.0,
    }
    try:
        cp = subprocess.run(
            [str(x) for x in command],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_sec)),
        )
        out["rc"] = int(cp.returncode)
        out["ok"] = int(cp.returncode) == 0
        out["stdout_tail"] = tail_text(cp.stdout or "", max_chars=4000)
        out["stderr_tail"] = tail_text(cp.stderr or "", max_chars=4000)
    except subprocess.TimeoutExpired as ex:
        out["rc"] = 124
        out["ok"] = False
        out["stdout_tail"] = tail_text(ex.stdout or "", max_chars=4000)
        out["stderr_tail"] = tail_text(ex.stderr or "", max_chars=4000)
        out["error"] = f"timeout:{int(timeout_sec)}s"
    except Exception as ex:
        out["rc"] = 1
        out["ok"] = False
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["finished_at"] = utc_now_iso()
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out


def background_creationflags() -> int:
    flags = 0
    for name in ("CREATE_NO_WINDOW", "DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= int(getattr(subprocess, name, 0) or 0)
    return flags


def start_live_loop_background(
    *,
    command: Sequence[str],
    env: Dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> Dict[str, Any]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    out: Dict[str, Any] = {
        "step_id": "session.live_loop",
        "command": [str(x) for x in command],
        "mode": "background",
        "rc": 1,
        "ok": False,
        "pid": 0,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stderr_tail": "",
        "error": "",
        "duration_sec": 0.0,
    }
    try:
        with stdout_path.open("a", encoding="utf-8") as out_f, stderr_path.open("a", encoding="utf-8") as err_f:
            proc = subprocess.Popen(
                [str(x) for x in command],
                cwd=str(ROOT),
                env=env,
                stdout=out_f,
                stderr=err_f,
                text=True,
                creationflags=background_creationflags(),
            )
        time.sleep(2.0)
        polled = proc.poll()
        if polled is None:
            out["rc"] = 0
            out["ok"] = True
            out["pid"] = int(proc.pid)
        else:
            out["rc"] = int(polled)
            out["ok"] = False
            out["error"] = "live_loop_exited_early"
            try:
                out["stderr_tail"] = tail_text(stderr_path.read_text(encoding="utf-8"), max_chars=4000)
            except Exception:
                out["stderr_tail"] = ""
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out


def start_background_command(
    *,
    step_id: str,
    command: Sequence[str],
    env: Dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> Dict[str, Any]:
    out = start_live_loop_background(
        command=command,
        env=env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    out["step_id"] = str(step_id)
    return out


def read_lock_owner_pid(lock_path: Path) -> int:
    if not lock_path.exists():
        return 0
    try:
        obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    return to_int(obj.get("pid"), 0)


def select_runtime_owner_row(rows: List[Dict[str, Any]], *, owner_pid: int) -> Dict[str, Any]:
    normalized = [dict(row) for row in rows if int(row.get("pid") or 0) > 0]
    if not normalized:
        return {}
    if owner_pid > 0:
        for row in normalized:
            if int(row.get("pid") or 0) == int(owner_pid):
                return row

    parent_pids = {int(row.get("parent_pid") or 0) for row in normalized if int(row.get("parent_pid") or 0) > 0}
    leaf_rows = [row for row in normalized if int(row.get("pid") or 0) not in parent_pids]
    candidates = leaf_rows or normalized
    candidates.sort(key=lambda row: int(row.get("pid") or 0), reverse=True)
    return candidates[0]


def collect_runtime_chain(rows: List[Dict[str, Any]], *, owner_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    normalized = [dict(row) for row in rows if int(row.get("pid") or 0) > 0]
    if not normalized or not owner_row:
        return []
    by_pid = {int(row.get("pid") or 0): row for row in normalized}
    owner_pid = int(owner_row.get("pid") or 0)
    if owner_pid <= 0:
        return []

    related: set[int] = {owner_pid}

    cur = owner_row
    while True:
        parent_pid = int(cur.get("parent_pid") or 0)
        if parent_pid <= 0 or parent_pid not in by_pid:
            break
        related.add(parent_pid)
        cur = by_pid[parent_pid]

    changed = True
    while changed:
        changed = False
        for row in normalized:
            pid = int(row.get("pid") or 0)
            parent_pid = int(row.get("parent_pid") or 0)
            if pid in related:
                continue
            if parent_pid in related:
                related.add(pid)
                changed = True

    chain = [by_pid[pid] for pid in related if pid in by_pid]
    chain.sort(key=lambda row: int(row.get("pid") or 0))
    return chain


def existing_live_loop_step(common: Dict[str, Any]) -> Dict[str, Any]:
    lock_path = Path(common["lock_path"])
    rows = query_live_loop_processes(Path(common["root"]), lock_path)
    if not rows:
        return {}
    owner_pid = read_lock_owner_pid(lock_path)
    owner_row = select_runtime_owner_row(rows, owner_pid=owner_pid)
    if not owner_row:
        return {}
    chain = collect_runtime_chain(rows, owner_row=owner_row)
    runtime_owner_pid = int(owner_row.get("pid") or 0)
    logical_instance_count = 1 if runtime_owner_pid > 0 else 0
    launcher_wrapper_detected = False
    if len(chain) == 2:
        chain_exe = [str(row.get("executable_path") or "").lower() for row in chain]
        if any("\\venv\\scripts\\python" in path for path in chain_exe) and any("pythoncore-" in path for path in chain_exe):
            launcher_wrapper_detected = True
    return {
        "step_id": "session.live_loop_existing",
        "mode": "existing",
        "rc": 0,
        "ok": True,
        "pid": runtime_owner_pid,
        "runtime_owner_pid": runtime_owner_pid,
        "logical_instance_count": int(logical_instance_count),
        "launcher_wrapper_detected": bool(launcher_wrapper_detected),
        "lock_owner_pid": int(owner_pid or 0),
        "launcher_pid": int(chain[0].get("pid") or 0) if chain else int(owner_row.get("pid") or 0),
        "runtime_chain_pids": [int(row.get("pid") or 0) for row in chain],
        "runtime_chain_count": len(chain) if chain else 1,
        "raw_process_count": len(rows),
        "command_line": str(owner_row.get("command_line") or ""),
        "command_line_source": "lock_owner" if owner_pid > 0 and int(owner_row.get("pid") or 0) == int(owner_pid) else "deduped_runtime_owner",
        "duration_sec": 0.0,
    }


def stop_live_loop_processes(common: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    rows = query_live_loop_processes(Path(common["root"]), Path(common["lock_path"]))
    out: Dict[str, Any] = {
        "step_id": "closeout.stop_session_loop",
        "mode": "process_cleanup",
        "ok": True,
        "rc": 0,
        "stopped_pids": [],
        "stderr_tail": "",
        "error": "",
        "duration_sec": 0.0,
    }
    stderr_chunks: List[str] = []
    for row in rows:
        pid = int(row.get("pid") or 0)
        if pid <= 0:
            continue
        try:
            cp = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                cwd=str(common["root"]),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if int(cp.returncode) == 0:
                out["stopped_pids"].append(pid)
            else:
                out["ok"] = False
                out["rc"] = int(cp.returncode)
                stderr_chunks.append(tail_text((cp.stdout or "") + "\n" + (cp.stderr or ""), max_chars=4000))
        except Exception as ex:
            out["ok"] = False
            out["rc"] = 1
            stderr_chunks.append(f"{type(ex).__name__}: {ex}")
    try:
        Path(common["lock_path"]).unlink(missing_ok=True)
    except Exception:
        pass
    out["stopped_total"] = len(out["stopped_pids"])
    out["stderr_tail"] = "\n".join(chunk for chunk in stderr_chunks if chunk).strip()
    if not out["ok"] and not out["error"]:
        out["error"] = "session_loop_stop_failed"
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out
