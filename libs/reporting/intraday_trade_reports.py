from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from libs.reporting.llm_artifacts import trade_artifact_paths


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _trade_day_from_trade_id(trade_id: str) -> str:
    value = str(trade_id or "").strip()
    match = re.match(r"^TRD_(\d{4})(\d{2})(\d{2})_", value)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bundle_role() -> str:
    return "intraday_trade_report_bundle"


def _script_path(root: Path) -> Path:
    return root / "scripts" / "run_live_execution_bundle_report.py"


def _brief_cache_dir(root: Path) -> Path:
    return Path(
        os.getenv("OPERATOR_UI_CACHE_PATH", str(root / "data" / "operator_ui" / "brief_cache"))
    )


def _bundle_job_lock_path(root: Path) -> Path:
    return root / "reports" / "runtime" / "intraday_trade_report_bundle.lock"


def _read_lock_payload(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _pid_active(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _active_bundle_job(path: Path, *, stale_after_sec: float = 900.0) -> Dict[str, Any]:
    payload = _read_lock_payload(path)
    if not payload:
        return {}
    pid = int(payload.get("pid") or 0)
    touched_at = float(
        payload.get("touched_at_epoch")
        or payload.get("heartbeat_epoch")
        or payload.get("started_at_epoch")
        or 0.0
    )
    age_sec = max(0.0, float(time.time()) - touched_at) if touched_at > 0 else stale_after_sec + 1.0
    active = _pid_active(pid)
    if active and age_sec <= stale_after_sec:
        out = dict(payload)
        out["lock_path"] = str(path)
        out["age_sec"] = age_sec
        return out
    if age_sec > stale_after_sec or not active:
        with contextlib.suppress(Exception):
            path.unlink()
    return {}


def _active_bundle_process(root: Path) -> Dict[str, Any]:
    script_path = str(_script_path(root)).lower()
    current_pid = int(os.getpid())
    try:
        if os.name == "nt":
            probe = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*run_live_execution_bundle_report.py*' } | "
                "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Compress"
            )
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", probe],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            raw = str(completed.stdout or "").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                pid = int(row.get("ProcessId") or 0)
                cmd = str(row.get("CommandLine") or "").lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if script_path not in cmd and "run_live_execution_bundle_report.py" not in cmd:
                    continue
                creation_epoch = _creation_epoch_from_wmi(row.get("CreationDate"))
                return {
                    "pid": pid,
                    "parent_pid": int(row.get("ParentProcessId") or 0),
                    "script": "run_live_execution_bundle_report.py",
                    "command_line": str(row.get("CommandLine") or ""),
                    "detection_source": "process_scan",
                    "creation_epoch": creation_epoch,
                    "age_sec": max(0.0, float(time.time()) - creation_epoch) if creation_epoch > 0 else None,
                }
        else:
            completed = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
                check=False,
            )
            for raw in str(completed.stdout or "").splitlines():
                line = str(raw or "").strip()
                if not line:
                    continue
                try:
                    pid_text, cmd = line.split(None, 1)
                except ValueError:
                    continue
                pid = int(pid_text or 0)
                cmd_lower = str(cmd or "").lower()
                if pid <= 0 or pid == current_pid:
                    continue
                if script_path not in cmd_lower and "run_live_execution_bundle_report.py" not in cmd_lower:
                    continue
                return {
                    "pid": pid,
                    "parent_pid": int(parent_pid or 0),
                    "script": "run_live_execution_bundle_report.py",
                    "command_line": str(cmd or ""),
                    "detection_source": "process_scan",
                }
    except Exception:
        return {}
    return {}


def _creation_epoch_from_wmi(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    match = re.search(r"/Date\((\d+)", raw)
    if match:
        try:
            return float(match.group(1)) / 1000.0
        except Exception:
            return 0.0
    return 0.0


def _stale_process_after_sec() -> float:
    try:
        return max(30.0, float(os.getenv("INTRADAY_TRADE_REPORT_STALE_PROCESS_SEC", "180") or 180.0))
    except Exception:
        return 180.0


def _terminate_process_tree(pid: int) -> bool:
    pid = int(pid or 0)
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5.0,
                check=False,
            )
            return int(completed.returncode or 1) == 0
        os.kill(pid, 15)
        return True
    except Exception:
        return False


def _write_bundle_job_lock(
    path: Path,
    *,
    pid: int,
    argv: List[str],
    target_run_id: str = "",
    target_symbol: str = "",
) -> None:
    now_epoch = float(time.time())
    payload = {
        "pid": int(pid or 0),
        "parent_pid": int(os.getpid()),
        "role": _bundle_role(),
        "status": "running",
        "created_at": _utc_iso(),
        "created_at_epoch": now_epoch,
        "started_at": _utc_iso(),
        "started_at_epoch": now_epoch,
        "touched_at": _utc_iso(),
        "touched_at_epoch": now_epoch,
        "script": "run_live_execution_bundle_report.py",
        "argv": list(argv or []),
        "target_run_id": str(target_run_id or ""),
        "target_symbol": _normalize_symbol(target_symbol),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _execution_action(state: Dict[str, Any]) -> str:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    return str(order.get("action") or execution.get("action") or "").strip().upper()


def _execution_ok(state: Dict[str, Any]) -> bool:
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    return bool(execution.get("ok")) and bool(execution.get("allowed", True))


def _cache_run_ids(summary: Dict[str, Any], current_run_id: str) -> List[str]:
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched_trade_ids = {
        str(row.get("trade_id") or "").strip()
        for row in run_bundles
        if str(row.get("run_id") or "").strip() == current_run_id and str(row.get("trade_id") or "").strip()
    }
    run_ids = {current_run_id}
    for row in run_bundles:
        if not isinstance(row, dict):
            continue
        trade_id = str(row.get("trade_id") or "").strip()
        run_id = str(row.get("run_id") or "").strip()
        if trade_id and trade_id in matched_trade_ids and run_id:
            run_ids.add(run_id)
    return sorted(x for x in run_ids if x)


def _invalidate_brief_cache(root: Path, run_ids: Iterable[str]) -> List[str]:
    cache_dir = _brief_cache_dir(root)
    removed: List[str] = []
    for run_id in run_ids:
        path = cache_dir / f"{run_id}.json"
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except Exception:
            continue
    return removed


def _build_bundle_argv(root: Path, state: Dict[str, Any] | None = None) -> List[str]:
    runtime_state = state if isinstance(state, dict) else {}
    execution = runtime_state.get("execution") if isinstance(runtime_state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    run_id = str(runtime_state.get("run_id") or "").strip()
    symbol = _normalize_symbol(order.get("symbol") or execution.get("symbol") or runtime_state.get("symbol") or "")
    argv = [
        "--env-path",
        str(Path(os.getenv("ENV_PATH", str(root / ".env")))),
        "--event-log-path",
        str(Path(os.getenv("EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl")))),
        "--evidence-log-path",
        str(Path(os.getenv("EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl")))),
        "--report-dir",
        str(root / "reports" / "dev" / "analysis" / "live_execution_bundles"),
        "--reports-root",
        str(root / "reports"),
        "--intents-path",
        str(Path(os.getenv("INTENTS_PATH", str(root / "data" / "logs" / "intents.jsonl")))),
        "--role",
        _bundle_role(),
        "--trade-report-ai",
        "--json",
    ]
    if run_id:
        argv.extend(["--target-run-id", run_id])
    if symbol:
        argv.extend(["--target-symbol", symbol])
    return argv


def _make_bundle_event_logger(root: Path):
    try:
        from libs.core.event_logger import EventLogger, resolve_event_log_path
    except Exception:
        return None
    try:
        return EventLogger(log_path=resolve_event_log_path(str(root / "data" / "logs" / "events.jsonl")))
    except Exception:
        return None


def _log_bundle_event(
    root: Path,
    *,
    event: str,
    reason: str = "",
    run_id: str = "",
    trade_id: str = "",
    symbol: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    logger = _make_bundle_event_logger(root)
    if logger is None:
        return
    safe_payload = dict(payload or {})
    safe_payload.setdefault("role", _bundle_role())
    if reason:
        safe_payload.setdefault("reason", str(reason))
    safe_payload.setdefault("pid", int(os.getpid()))
    safe_payload.setdefault("parent_pid", int(os.getpid()))
    with contextlib.suppress(Exception):
        logger.log(
            run_id=str(run_id or "runtime-report-bundle"),
            stage="reporting",
            event=event,
            event_name=f"reporting.{event}",
            level="info",
            trade_id=str(trade_id or ""),
            agent="reporting",
            phase="runtime",
            symbol=_normalize_symbol(symbol),
            payload=safe_payload,
        )


def _run_bundle_sync(argv: List[str]) -> tuple[int, str]:
    from scripts.run_live_execution_bundle_report import main as bundle_main

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = bundle_main(argv)
    return int(rc), stdout.getvalue().strip()


def _background_creationflags() -> int:
    flags = 0
    for name in ("CREATE_NO_WINDOW", "DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= int(getattr(subprocess, name, 0) or 0)
    return flags


def _run_bundle_with_timeout(
    root: Path,
    argv: List[str],
    *,
    timeout_sec: float,
    target_run_id: str = "",
    target_symbol: str = "",
) -> tuple[int | None, str, int | None]:
    cmd = [sys.executable, str(_script_path(root)), *argv]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(0.5, float(timeout_sec)),
            check=False,
        )
        return int(completed.returncode), str(completed.stdout or "").strip(), None
    except subprocess.TimeoutExpired:
        lock_path = _bundle_job_lock_path(root)
        env = dict(os.environ)
        env["INTRADAY_TRADE_REPORT_JOB_LOCK_PATH"] = str(lock_path)
        env["INTRADAY_TRADE_REPORT_PARENT_SPAWN"] = "1"
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=_background_creationflags(),
        )
        _write_bundle_job_lock(
            lock_path,
            pid=int(getattr(proc, "pid", 0) or 0),
            argv=cmd,
            target_run_id=target_run_id,
            target_symbol=target_symbol,
        )
        return None, "", int(getattr(proc, "pid", 0) or 0)


def _build_generation_result(*, root: Path, summary: Dict[str, Any], run_id: str, return_code: int) -> Dict[str, Any]:
    cache_run_ids = _cache_run_ids(summary, run_id)
    removed_cache = _invalidate_brief_cache(root, cache_run_ids)
    run_bundles = summary.get("run_bundles") if isinstance(summary.get("run_bundles"), list) else []
    matched = next(
        (row for row in run_bundles if isinstance(row, dict) and str(row.get("run_id") or "").strip() == run_id),
        {},
    )
    brief_artifacts: Dict[str, str] = {}
    trade_id = str((matched or {}).get("trade_id") or "").strip()
    trade_day = _trade_day_from_trade_id(trade_id)
    if trade_id and trade_day:
        trade_paths = trade_artifact_paths(root / "reports", trade_day, trade_id)
        brief_json_path = Path(trade_paths.get("brief_json") or Path())
        brief_md_path = Path(trade_paths.get("brief_md") or Path())
        brief_artifacts = {
            "operator_brief_json_path": str(brief_json_path),
            "operator_brief_md_path": str(brief_md_path),
        }

    return {
        "ok": True,
        "status": "generated",
        "reason": "",
        "return_code": int(return_code),
        "summary": summary,
        "trade_id": trade_id,
        "story_id": str((matched or {}).get("story_id") or ""),
        "report_status": str((matched or {}).get("report_status") or ""),
        "report_path": str((matched or {}).get("trade_report_json_path") or ""),
        "symbol": _normalize_symbol((matched or {}).get("symbol") or ""),
        "cache_invalidated": removed_cache,
        **brief_artifacts,
    }


def generate_intraday_trade_artifacts(state: Dict[str, Any], *, root: Path | None = None) -> Dict[str, Any]:
    if not _is_trueish(os.getenv("INTRADAY_TRADE_REPORTS_ENABLED", "true")):
        return {"ok": False, "status": "disabled", "reason": "intraday_trade_reports_disabled"}

    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    reporter = applied_policy.get("reporter") if isinstance(applied_policy.get("reporter"), dict) else {}
    trade_report = reporter.get("trade_report") if isinstance(reporter.get("trade_report"), dict) else {}
    if trade_report and trade_report.get("enabled") is False:
        return {
            "ok": False,
            "status": "disabled",
            "reason": "reporter.trade_report.enabled is false",
            "policy_source": str(trade_report.get("policy_source") or "commander_applied_policy"),
        }

    if not _execution_ok(state):
        return {"ok": False, "status": "skipped", "reason": "execution_not_successful"}

    action = _execution_action(state)
    if action not in {"BUY", "SELL"}:
        return {"ok": False, "status": "skipped", "reason": "non_trade_action"}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    repo_root = Path(root) if root is not None else _root_dir()
    run_id = str(state.get("run_id") or "").strip()
    argv = _build_bundle_argv(repo_root, state)
    force_sync = root is not None or _is_trueish(state.get("force_sync_intraday_trade_reports"))

    generate_on_open = bool(trade_report.get("generate_on_open", False))
    if action == "BUY" and not generate_on_open and not force_sync:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "trade_report_generate_on_open_disabled",
            "report_status": "pending",
            "symbol": _normalize_symbol(
                ((execution.get("order") or {}) if isinstance(execution.get("order"), dict) else {}).get("symbol")
                or execution.get("symbol")
                or state.get("symbol")
                or ""
            ),
            "target_run_id": str(state.get("run_id") or "").strip(),
            "target_symbol": _normalize_symbol(
                ((execution.get("order") or {}) if isinstance(execution.get("order"), dict) else {}).get("symbol")
                or execution.get("symbol")
                or state.get("symbol")
                or ""
            ),
            "role": _bundle_role(),
            "policy_source": str(trade_report.get("policy_source") or "commander_applied_policy"),
        }

    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    symbol = _normalize_symbol(order.get("symbol") or execution.get("symbol") or state.get("symbol") or "")
    _log_bundle_event(
        repo_root,
        event="report_bundle_spawn_requested",
        run_id=run_id,
        symbol=symbol,
        payload={
            "lock_path": str(_bundle_job_lock_path(repo_root)),
            "target_run_id": run_id,
            "target_symbol": symbol,
            "force_sync": bool(force_sync),
        },
    )
    if not force_sync:
        active_job = _active_bundle_job(_bundle_job_lock_path(repo_root))
        if not active_job:
            active_job = _active_bundle_process(repo_root)
            active_pid = int(active_job.get("pid") or 0) if isinstance(active_job, dict) else 0
            active_age_sec = float(active_job.get("age_sec") or 0.0) if isinstance(active_job, dict) else 0.0
            if active_pid > 0 and active_age_sec >= _stale_process_after_sec():
                terminated = _terminate_process_tree(active_pid)
                _log_bundle_event(
                    repo_root,
                    event="report_bundle_stale_process_terminated",
                    reason="orphan_bundle_process_exceeded_stale_window",
                    run_id=run_id,
                    symbol=symbol,
                    payload={
                        "lock_path": str(_bundle_job_lock_path(repo_root)),
                        "active_pid": active_pid,
                        "active_age_sec": active_age_sec,
                        "terminated": bool(terminated),
                        "target_run_id": run_id,
                        "target_symbol": symbol,
                    },
                )
                if terminated:
                    time.sleep(0.2)
                    active_job = {}
        if active_job:
            _log_bundle_event(
                repo_root,
                event="report_bundle_spawn_skipped_existing_process",
                reason="bundle_job_already_running",
                run_id=run_id,
                symbol=symbol,
                payload={
                    "lock_path": str(active_job.get("lock_path") or _bundle_job_lock_path(repo_root)),
                    "active_pid": int(active_job.get("pid") or 0),
                    "dedupe_source": str(active_job.get("detection_source") or "lock"),
                    "target_run_id": run_id,
                    "target_symbol": symbol,
                },
            )
            return {
                "ok": True,
                "status": "skipped",
                "reason": "bundle_job_already_running",
                "return_code": None,
                "summary": {},
                "trade_id": "",
                "story_id": "",
                "report_status": "queued",
                "report_path": "",
                "symbol": symbol,
                "cache_invalidated": [],
                "queue_mode": "background_subprocess_deduped",
                "background_pid": int(active_job.get("pid") or 0),
                "lock_path": str(active_job.get("lock_path") or ""),
                "dedupe_source": str(active_job.get("detection_source") or "lock"),
                "target_run_id": run_id,
                "target_symbol": symbol,
                "role": _bundle_role(),
            }
    if force_sync:
        rc, raw = _run_bundle_sync(argv)
        queued_pid = None
    else:
        rc, raw, queued_pid = _run_bundle_with_timeout(
            repo_root,
            argv,
            timeout_sec=float(os.getenv("INTRADAY_TRADE_REPORT_SYNC_TIMEOUT_SEC", "2.0") or 2.0),
            target_run_id=run_id,
            target_symbol=symbol,
        )

    if queued_pid:
        _log_bundle_event(
            repo_root,
            event="report_bundle_spawned_background",
            run_id=run_id,
            symbol=symbol,
            payload={
                "lock_path": str(_bundle_job_lock_path(repo_root)),
                "background_pid": int(queued_pid),
                "target_run_id": run_id,
                "target_symbol": symbol,
            },
        )
        return {
            "ok": True,
            "status": "queued",
            "reason": "",
            "return_code": None,
            "summary": {},
            "trade_id": "",
            "story_id": "",
            "report_status": "queued",
            "report_path": "",
            "symbol": symbol,
            "cache_invalidated": [],
            "queue_mode": "background_subprocess",
            "background_pid": int(queued_pid),
            "lock_path": str(_bundle_job_lock_path(repo_root)),
            "target_run_id": run_id,
            "target_symbol": symbol,
            "role": _bundle_role(),
        }

    try:
        summary = json.loads(raw) if raw else {}
    except Exception:
        summary = {}

    if rc != 0 or not isinstance(summary, dict):
        return {
            "ok": False,
            "status": "failed",
            "reason": "intraday_bundle_generation_failed",
            "return_code": int(rc),
            "stdout": raw[-1000:],
        }

    result = _build_generation_result(root=repo_root, summary=summary, run_id=run_id, return_code=int(rc))
    result["target_run_id"] = run_id
    result["target_symbol"] = symbol
    result["role"] = _bundle_role()
    return result
