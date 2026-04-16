from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.market_hours import KST
from libs.runtime.market_hours import MarketHours
from libs.runtime.market_hours import now_kst
from libs.storage.state_store import StateStore


PHASE_PREOPEN = "preopen"
PHASE_SESSION = "session"
PHASE_CLOSEOUT = "closeout"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_bool(v: Any, default: bool = False) -> bool:
    raw = str(v if v is not None else "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _resolve_path(raw: str, default_rel: str) -> Path:
    s = str(raw or "").strip() or str(default_rel)
    p = Path(s)
    if not p.is_absolute():
        p = ROOT / p
    return p


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = str(k).strip()
        val = str(v).strip()
        if val and val[0] not in ("'", '"') and "#" in val:
            val = val.split("#", 1)[0].rstrip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def _tail(s: str, max_chars: int = 4000) -> str:
    txt = str(s or "")
    if len(txt) <= max_chars:
        return txt
    return txt[-max_chars:]


def _parse_stdout_json(stdout_text: str) -> Dict[str, Any]:
    body = str(stdout_text or "").strip()
    if not body:
        return {}
    try:
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def _parse_kst_datetime(value: str) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    s = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> Optional[str]:
    e = _to_epoch(ts)
    if e is None:
        return None
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%d")


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


def _latest_event_day(event_log_path: Path, *, before_day: Optional[str] = None) -> Optional[str]:
    best: Optional[str] = None
    for row in _iter_jsonl(event_log_path) or []:
        d = _utc_day(row.get("ts"))
        if not d:
            continue
        if before_day and d >= before_day:
            continue
        if best is None or d > best:
            best = d
    return best


def _run_subprocess(
    *,
    step_id: str,
    command: Sequence[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: int = 1800,
) -> Dict[str, Any]:
    started_at = _utc_now_iso()
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
        out["stdout_tail"] = _tail(cp.stdout or "")
        out["stderr_tail"] = _tail(cp.stderr or "")
    except subprocess.TimeoutExpired as ex:
        out["rc"] = 124
        out["ok"] = False
        out["stdout_tail"] = _tail(ex.stdout or "")
        out["stderr_tail"] = _tail(ex.stderr or "")
        out["error"] = f"timeout:{int(timeout_sec)}s"
    except Exception as ex:
        out["rc"] = 1
        out["ok"] = False
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["finished_at"] = _utc_now_iso()
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out


def _start_live_loop_background(
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
                out["stderr_tail"] = _tail(stderr_path.read_text(encoding="utf-8"))
            except Exception:
                out["stderr_tail"] = ""
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out


def _start_background_command(
    *,
    step_id: str,
    command: Sequence[str],
    env: Dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> Dict[str, Any]:
    out = _start_live_loop_background(
        command=command,
        env=env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    out["step_id"] = str(step_id)
    return out


def _query_live_loop_processes(root: Path, lock_path: Path) -> List[Dict[str, Any]]:
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
        matches_scope = (
            lock_lower in cmd_lower
            or root_lower in cmd_lower
            or exe_lower.startswith(root_lower)
        )
        if not (matches_session and matches_scope):
            continue
        out.append(
            {
                "pid": _to_int(row.get("ProcessId"), 0),
                "parent_pid": _to_int(row.get("ParentProcessId"), 0),
                "executable_path": exe,
                "command_line": cmd,
            }
        )
    return [row for row in out if int(row.get("pid") or 0) > 0]


def _read_lock_owner_pid(lock_path: Path) -> int:
    if not lock_path.exists():
        return 0
    try:
        obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(obj, dict):
        return 0
    return _to_int(obj.get("pid"), 0)


def _select_runtime_owner_row(rows: List[Dict[str, Any]], *, owner_pid: int) -> Dict[str, Any]:
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


def _collect_runtime_chain(rows: List[Dict[str, Any]], *, owner_row: Dict[str, Any]) -> List[Dict[str, Any]]:
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


def _existing_live_loop_step(common: Dict[str, Any]) -> Dict[str, Any]:
    lock_path = Path(common["lock_path"])
    rows = _query_live_loop_processes(Path(common["root"]), lock_path)
    if not rows:
        return {}
    owner_pid = _read_lock_owner_pid(lock_path)
    owner_row = _select_runtime_owner_row(rows, owner_pid=owner_pid)
    if not owner_row:
        return {}
    chain = _collect_runtime_chain(rows, owner_row=owner_row)
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


def _stop_live_loop_processes(common: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    rows = _query_live_loop_processes(Path(common["root"]), Path(common["lock_path"]))
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
                stderr_chunks.append(_tail((cp.stdout or "") + "\n" + (cp.stderr or "")))
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


def _resolve_state_store_path(common: Dict[str, Any]) -> Path:
    explicit = common.get("state_path")
    if explicit:
        return Path(explicit)
    env_obj = _read_env_file(Path(common["env_path"]))
    raw = str(env_obj.get("STATE_STORE_PATH", "")).strip()
    return _resolve_path(raw, "data/state.json")


def _closeout_backup_liquidation(common: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.time()
    state_path = _resolve_state_store_path(common)
    env_obj = _read_env_file(Path(common["env_path"]))
    kiwoom_mode = str(env_obj.get("KIWOOM_MODE", "")).strip().lower()
    out: Dict[str, Any] = {
        "step_id": "closeout.backup_liquidation",
        "mode": "noop",
        "ok": True,
        "rc": 0,
        "state_path": str(state_path),
        "positions_before": 0,
        "positions_after": 0,
        "qty_total_before": 0,
        "symbols_before": [],
        "symbols_after": [],
        "error": "",
        "duration_sec": 0.0,
    }
    try:
        store = StateStore(str(state_path))
        state = store.load()
        raw_positions = state.get("mock_positions")
        positions: List[Dict[str, Any]] = []
        carry_rows: List[Dict[str, Any]] = []
        flatten_rows: List[Dict[str, Any]] = []
        overnight_map = (
            state.get("overnight_decision_by_symbol")
            if isinstance(state.get("overnight_decision_by_symbol"), dict)
            else {}
        )
        for row in raw_positions if isinstance(raw_positions, list) else []:
            if not isinstance(row, dict):
                continue
            qty = _to_int(row.get("qty"), 0)
            symbol = str(row.get("symbol") or "").strip()
            if qty <= 0 or not symbol:
                continue
            rec = {"symbol": symbol, "qty": qty, "row": dict(row)}
            positions.append(rec)
            decision = overnight_map.get(symbol) if isinstance(overnight_map, dict) else None
            if isinstance(decision, dict) and bool(decision.get("approved")):
                carry_rows.append(rec)
            else:
                flatten_rows.append(rec)
        out["positions_before"] = len(positions)
        out["qty_total_before"] = sum(int(row.get("qty") or 0) for row in positions)
        out["symbols_before"] = [str(row.get("symbol") or "") for row in positions]
        if not positions:
            out["mode"] = "noop_already_flat"
            out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
            return out
        if kiwoom_mode != "mock":
            out["mode"] = "non_mock_requires_manual_flatten"
            out["ok"] = False
            out["rc"] = 2
            out["error"] = "backup_liquidation_non_mock_not_supported"
            out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
            return out

        carry_symbols = [str(row.get("symbol") or "") for row in carry_rows]
        flatten_symbols = [str(row.get("symbol") or "") for row in flatten_rows]
        state["mock_positions"] = [dict(row.get("row") or {}) for row in carry_rows]
        state["open_positions"] = len(carry_rows)
        if carry_symbols:
            for key in ("position_peak_price", "position_strategy_context"):
                existing = state.get(key) if isinstance(state.get(key), dict) else {}
                filtered = {
                    str(sym): value
                    for sym, value in dict(existing).items()
                    if str(sym) in carry_symbols
                }
                if filtered:
                    state[key] = filtered
                else:
                    state.pop(key, None)
        else:
            state.pop("position_peak_price", None)
            state.pop("position_strategy_context", None)
        state["closeout_backup_liquidation"] = {
            "applied": bool(flatten_rows),
            "applied_at": _utc_now_iso(),
            "mode": (
                "noop_carry_forward"
                if carry_rows and not flatten_rows
                else "mock_backup_partial_flatten"
                if carry_rows and flatten_rows
                else "mock_backup_flatten"
            ),
            "symbols": list(flatten_symbols or out["symbols_before"]),
            "qty_total": int(sum(int(row.get("qty") or 0) for row in flatten_rows) if flatten_rows else out["qty_total_before"]),
            "carry_forward_symbols": list(carry_symbols),
            "flattened_symbols": list(flatten_symbols),
            "reason": (
                "overnight_carry_approved"
                if carry_rows and not flatten_rows
                else "closeout_respected_overnight_carry"
                if carry_rows and flatten_rows
                else "closeout_forced_flatten_backup"
            ),
        }
        store.save(state)
        out["mode"] = str(state["closeout_backup_liquidation"]["mode"])
        out["positions_after"] = len(carry_rows)
        out["symbols_after"] = list(carry_symbols)
        out["carry_forward_symbols"] = list(carry_symbols)
        out["flattened_symbols"] = list(flatten_symbols)
    except Exception as ex:
        out["ok"] = False
        out["rc"] = 1
        out["error"] = f"{type(ex).__name__}: {ex}"
    out["duration_sec"] = round(max(0.0, float(time.time() - t0)), 3)
    return out


def _runtime_mode_checks(env_obj: Dict[str, str]) -> Dict[str, Any]:
    runtime_profile = str(env_obj.get("RUNTIME_PROFILE", "")).strip().lower()
    kiwoom_mode = str(env_obj.get("KIWOOM_MODE", "")).strip().lower()
    approval_mode = str(env_obj.get("APPROVAL_MODE", "")).strip().lower()
    allow_real_execution = _to_bool(env_obj.get("ALLOW_REAL_EXECUTION"), default=False)
    return {
        "RUNTIME_PROFILE": runtime_profile,
        "KIWOOM_MODE": kiwoom_mode,
        "APPROVAL_MODE": approval_mode,
        "ALLOW_REAL_EXECUTION": bool(allow_real_execution),
        "ok": (
            runtime_profile == "staging"
            and kiwoom_mode == "mock"
            and approval_mode == "manual"
            and (not allow_real_execution)
        ),
    }


def _phase_template(name: str) -> Dict[str, Any]:
    return {"phase": name, "ok": False, "failure_reason": "", "steps": []}


def _run_preopen(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    out = _phase_template(PHASE_PREOPEN)
    py = str(common["python_path"])
    day = str(common["day"])
    report_root = Path(common["report_root"])
    event_log_path = Path(common["event_log_path"])

    step1 = _run_subprocess(
        step_id="preopen.m30_final_signoff",
        command=[
            py,
            str(ROOT / "scripts" / "run_m30_final_golive_signoff.py"),
            "--event-log-dir",
            str(ROOT / "data" / "logs" / "milestones" / "m30" / "golive"),
            "--quality-report-dir",
            str(ROOT / "reports" / "milestones" / "m30_quality_gates"),
            "--signoff-report-dir",
            str(ROOT / "reports" / "milestones" / "m30_signoff"),
            "--policy-report-dir",
            str(ROOT / "reports" / "milestones" / "m30_post_golive"),
            "--report-dir",
            str(ROOT / "reports" / "milestones" / "m30_golive"),
            "--day",
            day,
            "--no-clear",
            "--json",
        ],
        cwd=ROOT,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step1)
    if not bool(step1.get("ok")):
        out["failure_reason"] = "m30_final_signoff_failed"
        return out

    step1_obj = _parse_stdout_json(str(step1.get("stdout_tail") or ""))
    m30_2_signoff = step1_obj.get("m30_2_signoff") if isinstance(step1_obj.get("m30_2_signoff"), dict) else {}
    m30_2_signoff_json_path = str(m30_2_signoff.get("report_json_path") or "").strip()
    if not m30_2_signoff_json_path:
        m30_2_signoff_json_path = str(ROOT / "reports" / "milestones" / "m30_signoff" / f"m30_release_signoff_{day}.json")

    step2 = _run_subprocess(
        step_id="preopen.m30_post_golive_policy",
        command=[
            py,
            str(ROOT / "scripts" / "run_m30_post_golive_monitoring_policy.py"),
            "--signoff-json-path",
            str(m30_2_signoff_json_path),
            "--event-log-dir",
            str(ROOT / "data" / "logs" / "milestones" / "m30" / "golive"),
            "--quality-report-dir",
            str(ROOT / "reports" / "milestones" / "m30_quality_gates"),
            "--signoff-report-dir",
            str(ROOT / "reports" / "milestones" / "m30_signoff"),
            "--report-dir",
            str(ROOT / "reports" / "milestones" / "m30_post_golive"),
            "--day",
            day,
            "--json",
        ],
        cwd=ROOT,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step2)
    if not bool(step2.get("ok")):
        out["failure_reason"] = "m30_post_golive_policy_failed"
        return out

    requested_readiness_day = str(args.preopen_readiness_day or "").strip() or day
    step3 = _run_subprocess(
        step_id="preopen.m31_mock_exam_readiness_check",
        command=[
            py,
            str(ROOT / "scripts" / "run_m31_mock_exam_readiness_check.py"),
            "--day",
            requested_readiness_day,
            "--env-path",
            str(common["env_path"]),
            "--event-log-path",
            str(event_log_path),
            "--report-dir",
            str(report_root / "m31_mock_exam_readiness"),
            "--allow-offhours",
            "--json",
        ],
        cwd=ROOT,
        timeout_sec=int(common["timeout_sec"]),
    )
    out["steps"].append(step3)
    obj3 = _parse_stdout_json(str(step3.get("stdout_tail") or ""))
    readiness_ok = bool(step3.get("ok")) and bool(obj3.get("ok"))
    readiness_day_used = requested_readiness_day

    if not readiness_ok and requested_readiness_day == day:
        missing = obj3.get("missing_prerequisites") if isinstance(obj3.get("missing_prerequisites"), list) else []
        only_slo_gap = bool(missing) and all("m31_slo_incident_ok" in str(x) for x in missing)
        fallback_day = _latest_event_day(event_log_path, before_day=day)
        if only_slo_gap and fallback_day:
            step3b = _run_subprocess(
                step_id="preopen.m31_mock_exam_readiness_check_fallback",
                command=[
                    py,
                    str(ROOT / "scripts" / "run_m31_mock_exam_readiness_check.py"),
                    "--day",
                    str(fallback_day),
                    "--env-path",
                    str(common["env_path"]),
                    "--event-log-path",
                    str(event_log_path),
                    "--report-dir",
                    str(report_root / "m31_mock_exam_readiness"),
                    "--allow-offhours",
                    "--json",
                ],
                cwd=ROOT,
                timeout_sec=int(common["timeout_sec"]),
            )
            out["steps"].append(step3b)
            obj3b = _parse_stdout_json(str(step3b.get("stdout_tail") or ""))
            if bool(step3b.get("ok")) and bool(obj3b.get("ok")):
                obj3 = obj3b
                readiness_ok = True
                readiness_day_used = str(fallback_day)

    out["m31_mock_exam_readiness"] = obj3
    out["m31_mock_exam_readiness_day_used"] = readiness_day_used
    if not readiness_ok:
        out["failure_reason"] = "m31_mock_exam_readiness_failed"
        return out

    env_obj = _read_env_file(Path(common["env_path"]))
    mode = _runtime_mode_checks(env_obj)
    out["runtime_mode"] = mode
    if not bool(mode.get("ok")):
        out["failure_reason"] = "runtime_mode_policy_failed"
        return out

    out["ok"] = True
    return out


def _run_session(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    out = _phase_template(PHASE_SESSION)
    env_obj = _read_env_file(Path(common["env_path"]))
    mode = _runtime_mode_checks(env_obj)
    out["runtime_mode"] = mode
    if not bool(mode.get("ok")):
        out["failure_reason"] = "runtime_mode_policy_failed"
        return out

    dt_override = _parse_kst_datetime(str(args.now_kst or "")) if args.now_kst else None
    dt = dt_override or now_kst()
    if not bool(MarketHours().is_open(dt)):
        if bool(getattr(args, "allow_offhours_simulated_session", False)):
            cmd = [
                str(common["python_path"]),
                str(ROOT / "scripts" / "run_session.py"),
                "--mode",
                "mock",
                "--phase",
                "intraday",
                "--simulated",
                "--env-path",
                str(common["env_path"]),
                "--event-log-path",
                str(common["event_log_path"]),
                "--sleep-sec",
                str(int(args.sleep_sec)),
                "--lock-path",
                str(common["lock_path"]),
                "--lock-stale-sec",
                str(int(common["lock_stale_sec"])),
            ]
            if common.get("state_path"):
                cmd += ["--state-path", str(common["state_path"])]
            probe_symbol = str(getattr(args, "probe_symbol", "") or os.getenv("SYMBOL", "005930")).strip() or "005930"
            if probe_symbol:
                cmd += ["--symbol", probe_symbol]
            proc_env = os.environ.copy()
            proc_env["ENV_PATH"] = str(common["env_path"])
            step = _start_background_command(
                step_id="session.offhours_validation_loop",
                command=cmd,
                env=proc_env,
                stdout_path=Path(common["session_stdout_path"]),
                stderr_path=Path(common["session_stderr_path"]),
            )
            out["steps"].append(step)
            out["probe_mode"] = "offhours_simulated_session"
            out["ok"] = bool(step.get("ok"))
            if not out["ok"]:
                out["failure_reason"] = str(step.get("error") or "offhours_validation_launch_failed")
            return out

        if not bool(getattr(args, "allow_offhours_session_probe", False)):
            out["ok"] = True
            out["skipped"] = True
            out["skip_reason"] = "market_closed"
            out["market_closed_at"] = dt.isoformat()
            return out

        probe_symbol = str(getattr(args, "probe_symbol", "") or os.getenv("SYMBOL", "005930")).strip() or "005930"
        probe_price = float(getattr(args, "probe_price", 70000.0))
        probe_cash = float(getattr(args, "probe_cash", 2000000.0))
        step = _run_subprocess(
            step_id="session.offhours_probe",
            command=[
                str(common["python_path"]),
                str(ROOT / "scripts" / "run_session.py"),
                "--mode",
                "mock",
                "--phase",
                "intraday",
                "--probe",
                "--probe-symbol",
                probe_symbol,
                "--probe-price",
                str(probe_price),
                "--probe-cash",
                str(probe_cash),
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=int(common["timeout_sec"]),
        )
        out["steps"].append(step)
        probe_obj = _parse_stdout_json(str(step.get("stdout_tail") or ""))
        out["probe_mode"] = "offhours_session_probe"
        out["probe_result"] = probe_obj
        out["ok"] = bool(step.get("ok")) and bool(probe_obj.get("ok"))
        if not out["ok"]:
            out["failure_reason"] = "offhours_probe_failed"
        return out

    existing_step = _existing_live_loop_step(common)
    if existing_step:
        out["steps"].append(existing_step)
        out["ok"] = True
        out["reuse_existing"] = True
        return out

    cmd = [
        str(common["python_path"]),
        str(ROOT / "scripts" / "run_session.py"),
        "--mode",
        "mock",
        "--phase",
        "intraday",
        "--env-path",
        str(common["env_path"]),
        "--tick-pipeline",
        "integrated_chain",
        "--sleep-sec",
        str(int(args.sleep_sec)),
        "--lock-path",
        str(common["lock_path"]),
        "--lock-stale-sec",
        str(int(common["lock_stale_sec"])),
    ]

    proc_env = os.environ.copy()
    proc_env["ENV_PATH"] = str(common["env_path"])
    step = _start_live_loop_background(
        command=cmd,
        env=proc_env,
        stdout_path=Path(common["session_stdout_path"]),
        stderr_path=Path(common["session_stderr_path"]),
    )
    out["steps"].append(step)
    out["ok"] = bool(step.get("ok"))
    if not out["ok"]:
        out["failure_reason"] = str(step.get("error") or "session_launch_failed")
    return out


def _run_closeout(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    out = _phase_template(PHASE_CLOSEOUT)
    py = str(common["python_path"])
    day = str(common["day"])
    event_log_path = str(common["event_log_path"])
    evidence_log_path = str(common["evidence_log_path"])
    intents_path = str(Path(common["event_log_path"]).with_name("intents.jsonl"))
    report_root = Path(common["report_root"])
    timeout_sec = int(common["timeout_sec"])
    steps: List[Dict[str, Any]] = []

    stop_step = _stop_live_loop_processes(common)
    steps.append(stop_step)
    if not bool(stop_step.get("ok")):
        out["steps"] = steps
        out["failure_reason"] = "stop_session_loop_failed"
        return out

    steps.append(_closeout_backup_liquidation(common))

    steps.append(
        _run_subprocess(
            step_id="closeout.m31_slo_incident",
            command=[
                py,
                str(ROOT / "scripts" / "run_m31_slo_incident_review_check.py"),
                "--event-log-path",
                event_log_path,
                "--policy-report-dir",
                str(ROOT / "reports" / "milestones" / "m30_post_golive"),
                "--signoff-report-dir",
                str(ROOT / "reports" / "milestones" / "m30_golive"),
                "--report-dir",
                str(report_root / "m31_slo_incident"),
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    metrics_env = os.environ.copy()
    metrics_env["EVENT_LOG_PATH"] = event_log_path
    metrics_env["REPORT_DIR"] = str(report_root)
    metrics_env["METRICS_DAY"] = day
    steps.append(
        _run_subprocess(
            step_id="closeout.metrics",
            command=[py, str(ROOT / "scripts" / "generate_metrics_report.py")],
            cwd=ROOT,
            env=metrics_env,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.operator_summary",
            command=[
                py,
                str(ROOT / "scripts" / "run_operator_daily_summary.py"),
                "--event-log-path",
                event_log_path,
                "--metrics-report-dir",
                str(report_root / "metrics"),
                "--m30-post-golive-dir",
                str(ROOT / "reports" / "milestones" / "m30_post_golive"),
                "--m30-golive-dir",
                str(ROOT / "reports" / "milestones" / "m30_golive"),
                "--m31-slo-incident-dir",
                str(report_root / "m31_slo_incident"),
                "--report-dir",
                str(report_root / "operator_summary"),
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.decision_story",
            command=[
                py,
                str(ROOT / "scripts" / "run_decision_story_report.py"),
                "--event-log-path",
                event_log_path,
                "--report-dir",
                str(report_root / "decision_story"),
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.run_cards",
            command=[
                py,
                str(ROOT / "scripts" / "run_run_card_report.py"),
                "--event-log-path",
                event_log_path,
                "--report-dir",
                str(report_root / "run_cards"),
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    daily_env = os.environ.copy()
    daily_env["EVENT_LOG_PATH"] = event_log_path
    daily_env["REPORT_DIR"] = str(report_root)
    daily_env["REPORT_DAY"] = day
    steps.append(
        _run_subprocess(
            step_id="closeout.daily",
            command=[py, str(ROOT / "scripts" / "generate_daily_report.py")],
            cwd=ROOT,
            env=daily_env,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.reporter_analysis",
            command=[
                py,
                str(ROOT / "scripts" / "run_reporter_analysis_report.py"),
                "--env-path",
                str(common["env_path"]),
                "--event-log-path",
                event_log_path,
                "--intents-path",
                intents_path,
                "--reports-root",
                str(report_root),
                "--report-dir",
                str(report_root / "dev" / "analysis" / "reporter_analysis"),
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.live_execution_bundles",
            command=[
                py,
                str(ROOT / "scripts" / "run_live_execution_bundle_report.py"),
                "--env-path",
                str(common["env_path"]),
                "--event-log-path",
                event_log_path,
                "--evidence-log-path",
                evidence_log_path,
                "--reports-root",
                str(report_root),
                "--report-dir",
                str(report_root / "dev" / "analysis" / "live_execution_bundles"),
                "--intents-path",
                intents_path,
                "--day",
                day,
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    steps.append(
        _run_subprocess(
            step_id="closeout.report_inventory",
            command=[
                py,
                str(ROOT / "scripts" / "run_report_maintenance.py"),
                "--report-root",
                str(report_root),
                "--event-log-path",
                event_log_path,
                "--apply",
                "--include-legacy-root-daily",
                "--json",
            ],
            cwd=ROOT,
            timeout_sec=timeout_sec,
        )
    )

    out["steps"] = steps
    failed = [s for s in steps if not bool(s.get("ok"))]
    out["ok"] = len(failed) == 0
    if failed:
        out["failure_reason"] = "closeout_failed:" + ",".join(str(s.get("step_id") or "") for s in failed)
    return out


def _render_report_md(obj: Dict[str, Any]) -> str:
    lines = [
        f"# Mock Exam Day Orchestration ({obj.get('day')})",
        "",
        f"- phase: **{obj.get('phase')}**",
        f"- ok: **{bool(obj.get('ok'))}**",
        f"- event_log_path: `{obj.get('event_log_path')}`",
        f"- state_path: `{obj.get('state_path')}`",
        f"- report_root: `{obj.get('report_root')}`",
        "",
    ]
    phase_obj = obj.get("phase_result") if isinstance(obj.get("phase_result"), dict) else {}
    lines += [
        f"## {obj.get('phase')}",
        "",
        f"- ok: **{bool(phase_obj.get('ok'))}**",
        f"- failure_reason: `{phase_obj.get('failure_reason')}`",
        f"- skipped: **{bool(phase_obj.get('skipped'))}**",
        f"- skip_reason: `{phase_obj.get('skip_reason')}`",
        "",
        "### Steps",
        "",
    ]
    steps = phase_obj.get("steps") if isinstance(phase_obj.get("steps"), list) else []
    if not steps:
        lines.append("- (none)")
    else:
        for s in steps:
            lines.append(
                f"- `{s.get('step_id')}` ok={bool(s.get('ok'))} rc={int(s.get('rc') or 0)} "
                f"duration={float(s.get('duration_sec') or 0.0):.3f}s"
            )
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mock investor exam day orchestration by phase.")
    p.add_argument("--phase", choices=[PHASE_PREOPEN, PHASE_SESSION, PHASE_CLOSEOUT], required=True)
    p.add_argument("--day", default=None)
    p.add_argument("--env-path", default=".env")
    p.add_argument("--report-dir", default="reports/dev/exam/mock_exam_day")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--evidence-log-path", default="data/evidence_ledger/events.jsonl")
    p.add_argument("--state-path", default=os.getenv("STATE_STORE_PATH", ""))
    p.add_argument("--sleep-sec", type=int, default=_to_int(os.getenv("SCAN_INTERVAL_SEC", "60"), 60))
    p.add_argument("--python-path", default=sys.executable)
    p.add_argument("--timeout-sec", type=int, default=1800)
    p.add_argument("--lock-path", default="data/state/m13_live_loop.lock")
    p.add_argument("--lock-stale-sec", type=int, default=_to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800))
    p.add_argument("--session-stdout-path", default="data/logs/dev/session/mock_exam_day_session_stdout.log")
    p.add_argument("--session-stderr-path", default="data/logs/dev/session/mock_exam_day_session_stderr.log")
    p.add_argument("--now-kst", default=None)
    p.add_argument(
        "--allow-offhours-session-probe",
        action="store_true",
        help="When market is closed, run one-shot integrated-chain probe instead of failing session phase.",
    )
    p.add_argument(
        "--allow-offhours-simulated-session",
        action="store_true",
        help="When market is closed, start continuous off-hours validation loop with local mock fills.",
    )
    p.add_argument("--probe-symbol", default=os.getenv("SYMBOL", "005930"))
    p.add_argument("--probe-price", type=float, default=70000.0)
    p.add_argument("--probe-cash", type=float, default=2000000.0)
    p.add_argument("--preopen-readiness-day", default=None, help="Override readiness check day for preopen.")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day).strip() if args.day else now_kst().strftime("%Y-%m-%d")
    report_root = _resolve_path(str(args.report_dir), "reports/dev/exam/mock_exam_day")
    report_root.mkdir(parents=True, exist_ok=True)
    orchestration_dir = report_root / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)

    common: Dict[str, Any] = {
        "root": ROOT,
        "day": day,
        "env_path": _resolve_path(str(args.env_path), ".env"),
        "report_root": report_root,
        "event_log_path": _resolve_path(str(args.event_log_path), "data/logs/events.jsonl"),
        "evidence_log_path": _resolve_path(str(args.evidence_log_path), "data/evidence_ledger/events.jsonl"),
        "state_path": (
            _resolve_path(str(args.state_path), "data/state.json")
            if str(args.state_path or "").strip()
            else None
        ),
        "python_path": _resolve_path(str(args.python_path), str(sys.executable)),
        "timeout_sec": int(args.timeout_sec),
        "lock_path": _resolve_path(str(args.lock_path), "data/state/m13_live_loop.lock"),
        "lock_stale_sec": int(args.lock_stale_sec),
        "session_stdout_path": _resolve_path(str(args.session_stdout_path), "data/logs/dev/session/mock_exam_day_session_stdout.log"),
        "session_stderr_path": _resolve_path(str(args.session_stderr_path), "data/logs/dev/session/mock_exam_day_session_stderr.log"),
    }

    started_at = _utc_now_iso()
    phase = str(args.phase).strip().lower()

    if phase == PHASE_PREOPEN:
        phase_result = _run_preopen(args, common)
    elif phase == PHASE_SESSION:
        phase_result = _run_session(args, common)
    else:
        phase_result = _run_closeout(args, common)

    ok = bool(phase_result.get("ok"))
    out: Dict[str, Any] = {
        "schema_version": "mock_exam_day_orchestration.v1",
        "phase": phase,
        "day": day,
        "ok": ok,
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "event_log_path": str(common["event_log_path"]),
        "state_path": str(common["state_path"]) if common.get("state_path") else "",
        "report_root": str(report_root),
        "phase_result": phase_result,
    }

    json_path = orchestration_dir / f"mock_exam_day_{day}_{phase}.json"
    md_path = orchestration_dir / f"mock_exam_day_{day}_{phase}.md"
    out["report_json_path"] = str(json_path)
    out["report_md_path"] = str(md_path)
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_report_md(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok={ok} phase={phase} day={day} report_json={json_path} report_md={md_path}")

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
