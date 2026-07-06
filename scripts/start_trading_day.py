from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.entrypoint_common import to_int
from libs.runtime.live_loop_lock import pid_exists
from libs.runtime.live_loop_process_query import query_live_loop_processes, read_lock_owner_pid


KST = ZoneInfo("Asia/Seoul")
RUNTIME_DIR = ROOT / "reports" / "runtime"
STATUS_DIR = ROOT / "reports" / "runtime" / "trading_day_status"
LOCK_PATH = ROOT / "data" / "state" / "m13_live_loop.lock"

SHADOW_LOOPS = {
    "q10_samsung_hynix": {
        "pattern": "run_baseline_samsung_hynix.py",
        "cmd": [
            "scripts/run_baseline_samsung_hynix.py",
            "--reports-root",
            "reports",
            "--state-path",
            "data/state.json",
            "--loop",
            "--interval-sec",
            "300",
            "--reconstruct-intraday",
        ],
    },
    "q11_opening_opportunity": {
        "pattern": "run_opportunity_engine_shadow.py",
        "cmd": [
            "scripts/run_opportunity_engine_shadow.py",
            "--symbols",
            "005930,000660,009150",
            "--reports-root",
            "reports",
            "--state-path",
            "data/state.json",
            "--loop",
            "--interval-sec",
            "300",
        ],
    },
    "q12_btc_woori": {
        "pattern": "run_baseline_btc_woori_tech.py",
        "cmd": [
            "scripts/run_baseline_btc_woori_tech.py",
            "--reports-root",
            "reports",
            "--state-path",
            "data/state.json",
            "--loop",
            "--interval-sec",
            "300",
        ],
    },
}


def _session_stack_window_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    current = current.astimezone(KST)
    minutes = current.hour * 60 + current.minute
    return (8 * 60 + 40) <= minutes <= (15 * 60 + 30)


def _runtime_python() -> str:
    candidate = ROOT / "venv" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else sys.executable


def _powershell_processes(patterns: list[str]) -> list[dict[str, Any]]:
    escaped = "|".join(pattern.replace("\\", "\\\\") for pattern in patterns)
    command = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -match '{escaped}' }} | "
        "Select-Object Name,ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 4"
    )
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if cp.returncode != 0 or not (cp.stdout or "").strip():
        return []
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    return [row for row in payload if isinstance(row, dict)]


def _loop_processes() -> dict[str, list[dict[str, Any]]]:
    rows = _powershell_processes([cfg["pattern"] for cfg in SHADOW_LOOPS.values()])
    out: dict[str, list[dict[str, Any]]] = {}
    for name, cfg in SHADOW_LOOPS.items():
        pattern = str(cfg["pattern"])
        matched = [
            row
            for row in rows
            if pattern in str(row.get("CommandLine") or "")
            and "powershell" not in str(row.get("Name") or "").lower()
        ]
        matched_pids = {to_int(row.get("ProcessId"), 0) for row in matched}
        # Some Windows Python launches show a parent/child pair with the same
        # command line. Count the top-level loop runner only; otherwise the
        # watchdog reports a false duplicate and may restart healthy loops.
        out[name] = [
            row
            for row in matched
            if to_int(row.get("ParentProcessId"), 0) not in matched_pids
        ]
    return out


def _has_day_arg(command_line: str, day: str) -> bool:
    text = str(command_line or "")
    return f"--day {day}" in text or f"--day={day}" in text


def _stop_pid(pid: int) -> dict[str, Any]:
    if pid <= 0:
        return {"pid": pid, "ok": False, "reason": "invalid_pid"}
    try:
        cp = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=10)
        return {
            "pid": pid,
            "ok": cp.returncode == 0 or not pid_exists(pid),
            "returncode": cp.returncode,
            "stdout": (cp.stdout or "").strip()[-500:],
            "stderr": (cp.stderr or "").strip()[-500:],
        }
    except Exception as exc:
        return {"pid": pid, "ok": not pid_exists(pid), "error": f"{type(exc).__name__}: {exc}"}


def _stop_stale_shadow_loops(day: str, *, replace: bool) -> list[dict[str, Any]]:
    stopped: list[dict[str, Any]] = []
    for name, rows in _loop_processes().items():
        for row in rows:
            cmd = str(row.get("CommandLine") or "")
            stale = not _has_day_arg(cmd, day)
            if replace or stale:
                pid = to_int(row.get("ProcessId"), 0)
                result = _stop_pid(pid)
                result["loop"] = name
                result["stale_day"] = stale
                stopped.append(result)
    return stopped


def _start_shadow_loop(name: str, day: str) -> dict[str, Any]:
    cfg = SHADOW_LOOPS[name]
    cmd = [_runtime_python(), *list(cfg["cmd"]), "--day", day]
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    stdout = RUNTIME_DIR / f"{name}_{day}_{stamp}.out.log"
    stderr = RUNTIME_DIR / f"{name}_{day}_{stamp}.err.log"
    out_f = stdout.open("ab")
    err_f = stderr.open("ab")
    creationflags = 0
    if sys.platform == "win32":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        out_f.close()
        err_f.close()
    return {"loop": name, "pid": proc.pid, "cmd": cmd, "stdout": str(stdout), "stderr": str(stderr)}


def _ensure_shadow_loops(day: str, *, replace_stale: bool = True) -> dict[str, Any]:
    stopped = _stop_stale_shadow_loops(day, replace=False) if replace_stale else []
    started: list[dict[str, Any]] = []
    processes = _loop_processes()
    for name, rows in processes.items():
        current_rows = [row for row in rows if _has_day_arg(str(row.get("CommandLine") or ""), day)]
        for duplicate in current_rows[1:]:
            result = _stop_pid(to_int(duplicate.get("ProcessId"), 0))
            result["loop"] = name
            result["stale_day"] = False
            result["duplicate_current_day"] = True
            stopped.append(result)
    processes = _loop_processes()
    for name, rows in processes.items():
        current_rows = [row for row in rows if _has_day_arg(str(row.get("CommandLine") or ""), day)]
        if current_rows:
            continue
        started.append(_start_shadow_loop(name, day))
    time.sleep(1.0)
    final = _loop_processes()
    return {
        "stopped": stopped,
        "started": started,
        "running": {
            name: {
                "process_count": len(rows),
                "pids": [to_int(row.get("ProcessId"), 0) for row in rows],
                "current_day_count": sum(1 for row in rows if _has_day_arg(str(row.get("CommandLine") or ""), day)),
                "stale_count": sum(1 for row in rows if not _has_day_arg(str(row.get("CommandLine") or ""), day)),
            }
            for name, rows in final.items()
        },
    }


def _live_status() -> dict[str, Any]:
    lock_pid = read_lock_owner_pid(LOCK_PATH)
    processes = query_live_loop_processes(ROOT, LOCK_PATH)
    return {
        "lock_exists": LOCK_PATH.exists(),
        "lock_pid": lock_pid,
        "lock_pid_alive": bool(lock_pid and pid_exists(lock_pid)),
        "process_count": len(processes),
        "pids": [to_int(row.get("pid"), 0) for row in processes],
        "running": bool(lock_pid and pid_exists(lock_pid) and processes),
    }


def _start_live() -> dict[str, Any]:
    cmd = [
        _runtime_python(),
        str(ROOT / "scripts" / "restart_live_session.py"),
        "--log-tag",
        "scheduled_start",
        "--no-allow-offhours",
        "--session-hard-gate",
        "--json",
    ]
    cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=45)
    try:
        payload = json.loads(cp.stdout) if (cp.stdout or "").strip() else {}
    except Exception:
        payload = {}
    return {
        "returncode": cp.returncode,
        "stdout": (cp.stdout or "").strip()[-4000:],
        "stderr": (cp.stderr or "").strip()[-4000:],
        "payload": payload,
    }


def _event_health(day: str, *, lookback_min: int = 10) -> dict[str, Any]:
    path = ROOT / "data" / "logs" / "events.jsonl"
    now = datetime.now(KST)
    cutoff = now - timedelta(minutes=max(1, int(lookback_min)))
    counts: dict[str, int] = {
        "scanner_events": 0,
        "strategist_llm_failed": 0,
        "commander_blocked": 0,
        "q9_scanner_selection": 0,
    }
    if not path.exists():
        return {"available": False, "reason": "events_log_missing", "counts": counts}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-3000:]
    except Exception as exc:
        return {"available": False, "reason": f"events_log_read_failed:{type(exc).__name__}", "counts": counts}
    for line in lines:
        if day not in line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts_text = str(row.get("ts_kst") or row.get("ts") or "")
        try:
            parsed = datetime.fromisoformat(ts_text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        parsed = parsed.astimezone(KST)
        if parsed < cutoff:
            continue
        stage = str(row.get("stage") or "")
        event = str(row.get("event_name") or row.get("event") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if stage == "scanner" or event.startswith("scanner."):
            counts["scanner_events"] += 1
        if event == "strategist_llm.result" and payload.get("ok") is False:
            if str(payload.get("blocked_reason") or "") == "strategist_llm_failed":
                counts["strategist_llm_failed"] += 1
        if event == "commander_router.fast_path" and str(payload.get("reason") or "") == "strategist_llm_failed":
            counts["commander_blocked"] += 1
        if "scanner_selection" in line:
            counts["q9_scanner_selection"] += 1
    status = "PASS"
    blockers: list[dict[str, Any]] = []
    if counts["strategist_llm_failed"] >= 3 and counts["scanner_events"] == 0:
        status = "BLOCKED"
        blockers.append({
            "code": "strategist_llm_failure_blocks_scanner",
            "lookback_min": lookback_min,
            "strategist_llm_failed": counts["strategist_llm_failed"],
            "scanner_events": counts["scanner_events"],
        })
    return {"available": True, "status": status, "counts": counts, "blockers": blockers}


def _write_status(day: str, mode: str, payload: dict[str, Any]) -> Path:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = STATUS_DIR / f"{day}_{mode}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = STATUS_DIR / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_start(day: str) -> dict[str, Any]:
    if not _session_stack_window_open():
        payload = {
            "schema_version": "trading_day_start.v1",
            "day": day,
            "mode": "start",
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "ok": False,
            "blockers": [{"code": "outside_regular_session_start_window"}],
            "live_after": _live_status(),
            "shadow_loops": {"running": {}},
        }
        payload["status_path"] = str(_write_status(day, "start", payload))
        return payload
    shadow = _ensure_shadow_loops(day, replace_stale=True)
    live_before = _live_status()
    live_start = {"skipped": True, "reason": "already_running"}
    if not live_before.get("running"):
        live_start = _start_live()
    live_after = _live_status()
    payload = {
        "schema_version": "trading_day_start.v1",
        "day": day,
        "mode": "start",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "live_before": live_before,
        "live_start": live_start,
        "live_after": live_after,
        "shadow_loops": shadow,
    }
    blockers: list[dict[str, Any]] = []
    if not live_after.get("running"):
        blockers.append({"code": "live_session_not_running"})
    for name, row in (shadow.get("running") or {}).items():
        if to_int(row.get("current_day_count"), 0) <= 0:
            blockers.append({"code": f"{name}_not_running_for_day"})
        if to_int(row.get("stale_count"), 0) > 0:
            blockers.append({"code": f"{name}_stale_process_still_running", "stale_count": row.get("stale_count")})
    payload["blockers"] = blockers
    payload["ok"] = not blockers
    payload["status_path"] = str(_write_status(day, "start", payload))
    return payload


def run_watchdog(day: str, *, lookback_min: int) -> dict[str, Any]:
    if not _session_stack_window_open():
        payload = {
            "schema_version": "trading_day_watchdog.v1",
            "day": day,
            "mode": "watchdog",
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "ok": True,
            "offhours_noop": True,
            "blockers": [],
            "live_after": _live_status(),
            "shadow_loops": {"running": {}},
            "event_health": {"available": False, "reason": "outside_regular_session_start_window"},
        }
        payload["status_path"] = str(_write_status(day, "watchdog", payload))
        return payload
    shadow = _ensure_shadow_loops(day, replace_stale=True)
    live_before = _live_status()
    live_start = {"skipped": True, "reason": "already_running"}
    if not live_before.get("running"):
        live_start = _start_live()
    live_after = _live_status()
    event_health = _event_health(day, lookback_min=lookback_min)
    blockers: list[dict[str, Any]] = []
    if not live_after.get("running"):
        blockers.append({"code": "live_session_not_running"})
    for name, row in (shadow.get("running") or {}).items():
        if to_int(row.get("current_day_count"), 0) <= 0:
            blockers.append({"code": f"{name}_not_running_for_day"})
    blockers.extend(list(event_health.get("blockers") or []))
    payload = {
        "schema_version": "trading_day_watchdog.v1",
        "day": day,
        "mode": "watchdog",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "live_before": live_before,
        "live_start": live_start,
        "live_after": live_after,
        "shadow_loops": shadow,
        "event_health": event_health,
        "blockers": blockers,
        "ok": not blockers,
    }
    payload["status_path"] = str(_write_status(day, "watchdog", payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and verify the live trading day runtime stack.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--mode", choices=["start", "watchdog"], default="start")
    parser.add_argument("--lookback-min", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    day = str(args.day)[:10]
    payload = run_watchdog(day, lookback_min=args.lookback_min) if args.mode == "watchdog" else run_start(day)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ok={bool(payload.get('ok'))} mode={payload.get('mode')} day={day} status_path={payload.get('status_path')}")
        for row in payload.get("blockers") or []:
            print(f"BLOCKER {row}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
