from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
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
    started_at = float(payload.get("started_at_epoch") or 0.0)
    age_sec = max(0.0, float(time.time()) - started_at) if started_at > 0 else stale_after_sec + 1.0
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


def _write_bundle_job_lock(path: Path, *, pid: int, argv: List[str]) -> None:
    payload = {
        "pid": int(pid or 0),
        "started_at_epoch": float(time.time()),
        "script": "run_live_execution_bundle_report.py",
        "argv": list(argv or []),
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


def _build_bundle_argv(root: Path) -> List[str]:
    return [
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
        "--max-runs",
        str(int(float(os.getenv("INTRADAY_TRADE_REPORT_MAX_RUNS", "200")))),
        "--trade-report-ai",
        "--json",
    ]


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


def _run_bundle_with_timeout(root: Path, argv: List[str], *, timeout_sec: float) -> tuple[int | None, str, int | None]:
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
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=_background_creationflags(),
        )
        _write_bundle_job_lock(lock_path, pid=int(getattr(proc, "pid", 0) or 0), argv=cmd)
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

    repo_root = Path(root) if root is not None else _root_dir()
    run_id = str(state.get("run_id") or "").strip()
    argv = _build_bundle_argv(repo_root)
    force_sync = root is not None or _is_trueish(state.get("force_sync_intraday_trade_reports"))
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    order = execution.get("order") if isinstance(execution.get("order"), dict) else {}
    if not force_sync:
        active_job = _active_bundle_job(_bundle_job_lock_path(repo_root))
        if active_job:
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
                "symbol": _normalize_symbol(order.get("symbol") or ""),
                "cache_invalidated": [],
                "queue_mode": "background_subprocess_deduped",
                "background_pid": int(active_job.get("pid") or 0),
                "lock_path": str(active_job.get("lock_path") or ""),
            }
    if force_sync:
        rc, raw = _run_bundle_sync(argv)
        queued_pid = None
    else:
        rc, raw, queued_pid = _run_bundle_with_timeout(
            repo_root,
            argv,
            timeout_sec=float(os.getenv("INTRADAY_TRADE_REPORT_SYNC_TIMEOUT_SEC", "2.0") or 2.0),
        )

    if queued_pid:
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
            "symbol": _normalize_symbol(order.get("symbol") or ""),
            "cache_invalidated": [],
            "queue_mode": "background_subprocess",
            "background_pid": int(queued_pid),
            "lock_path": str(_bundle_job_lock_path(repo_root)),
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

    return _build_generation_result(root=repo_root, summary=summary, run_id=run_id, return_code=int(rc))
