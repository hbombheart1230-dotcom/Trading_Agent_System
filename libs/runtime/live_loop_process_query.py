from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from libs.runtime.entrypoint_common import to_int


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


def query_live_loop_processes(root: Path, lock_path: Path) -> List[Dict[str, Any]]:
    root_text = str(root.resolve())
    lock_text = str(lock_path.resolve())
    command = "\n".join(
        [
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
            '$rows = Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine',
            "if ($rows) { $rows | ConvertTo-Json -Compress }",
        ]
    )
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return []
    if int(cp.returncode) != 0:
        return []
    raw = str(cp.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    out: List[Dict[str, Any]] = []
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        cmd = str(row.get("CommandLine") or "")
        exe = str(row.get("ExecutablePath") or "")
        cmd_lower = cmd.lower()
        exe_lower = exe.lower()
        root_lower = root_text.lower()
        lock_lower = lock_text.lower()
        matches_session = (
            (
                ("scripts/run_session.py" in cmd_lower or "-m scripts.run_session" in cmd_lower)
                and "--phase intraday" in cmd_lower
            )
            or "scripts/run_m13_live_loop.py" in cmd_lower
            or "-m scripts.run_m13_live_loop" in cmd_lower
        )
        matches_scope = lock_lower in cmd_lower or root_lower in cmd_lower or exe_lower.startswith(root_lower)
        if not (matches_session and matches_scope):
            continue
        out.append(
            {
                "pid": to_int(row.get("ProcessId"), 0),
                "parent_pid": to_int(row.get("ParentProcessId"), 0),
                "executable_path": exe,
                "command_line": cmd,
            }
        )
    return [row for row in out if int(row.get("pid") or 0) > 0]
