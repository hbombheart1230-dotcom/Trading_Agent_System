from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]

from libs.runtime.live_loop_process_query import query_live_loop_processes
from libs.runtime.market_hours import KST
from libs.runtime.market_hours import now_kst
from libs.runtime.mock_exam_day import closeout_liquidation as _closeout_liquidation
from libs.runtime.mock_exam_day import closeout_phase as _closeout_phase
from libs.runtime.mock_exam_day import preopen_phase as _preopen_phase
from libs.runtime.mock_exam_day import session_phase as _session_phase
from libs.runtime.mock_exam_day.common import (
    iter_jsonl as _iter_jsonl,
    read_env_file as _read_env_file,
    resolve_path as _common_resolve_path,
    to_bool as _to_bool,
    to_int as _to_int,
    utc_day as _utc_day,
    utc_now_iso as _utc_now_iso,
)
from libs.runtime.mock_exam_day import processes as _processes
from libs.runtime.mock_exam_day.processes import collect_runtime_chain as _collect_runtime_chain
from libs.runtime.mock_exam_day.processes import read_lock_owner_pid as _read_lock_owner_pid
from libs.runtime.mock_exam_day.processes import select_runtime_owner_row as _select_runtime_owner_row


PHASE_PREOPEN = "preopen"
PHASE_SESSION = "session"
PHASE_CLOSEOUT = "closeout"


def _resolve_path(raw: str, default_rel: str) -> Path:
    return _common_resolve_path(raw, default_rel, root=ROOT)


_run_subprocess = _processes.run_subprocess
_background_creationflags = _processes.background_creationflags
_start_live_loop_background = _processes.start_live_loop_background
_start_background_command = _processes.start_background_command
_stop_live_loop_processes = _processes.stop_live_loop_processes


def _existing_live_loop_step(common: Dict[str, Any]) -> Dict[str, Any]:
    original = _processes.query_live_loop_processes
    _processes.query_live_loop_processes = query_live_loop_processes
    try:
        return _processes.existing_live_loop_step(common)
    finally:
        _processes.query_live_loop_processes = original


def _resolve_state_store_path(common: Dict[str, Any]) -> Path:
    return _closeout_liquidation.resolve_state_store_path(common, root=ROOT)


def _to_float(v: Any, default: float = 0.0) -> float:
    return _closeout_liquidation.to_float(v, default)


def _resolve_execution_mode_from_env(env_obj: Dict[str, str]) -> str:
    return _closeout_liquidation.resolve_execution_mode_from_env(env_obj)


def _normalize_position_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return _closeout_liquidation.normalize_position_row(row)


def _read_authoritative_portfolio_rows(common: Dict[str, Any], env_obj: Dict[str, str]) -> List[Dict[str, Any]]:
    return _closeout_liquidation.read_authoritative_portfolio_rows(common, env_obj)


def _merge_position_metadata(rows: List[Dict[str, Any]], state_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _closeout_liquidation.merge_position_metadata(rows, state_rows)


def _filter_state_position_metadata(state: Dict[str, Any], symbols: List[str]) -> None:
    _closeout_liquidation.filter_state_position_metadata(state, symbols)


def _closeout_backup_liquidation(common: Dict[str, Any]) -> Dict[str, Any]:
    return _closeout_liquidation.closeout_backup_liquidation(
        common,
        root=ROOT,
        portfolio_reader=_read_authoritative_portfolio_rows,
    )


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
    return _closeout_phase.phase_template(name)


def _optional_report_step(step_id: str, *, report_name: str, reason: str) -> Dict[str, Any]:
    return _closeout_phase.optional_report_step(step_id, report_name=report_name, reason=reason)


def _run_preopen(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    return _preopen_phase.run_preopen_phase(
        args,
        common,
        root=ROOT,
        phase_name=PHASE_PREOPEN,
        run_subprocess=_run_subprocess,
        runtime_mode_checks=_runtime_mode_checks,
    )


def _run_session(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    return _session_phase.run_session_phase(
        args,
        common,
        root=ROOT,
        phase_name=PHASE_SESSION,
        run_subprocess=_run_subprocess,
        start_live_loop_background=_start_live_loop_background,
        start_background_command=_start_background_command,
        existing_live_loop_step=_existing_live_loop_step,
        runtime_mode_checks=_runtime_mode_checks,
    )


def _run_closeout(args: argparse.Namespace, common: Dict[str, Any]) -> Dict[str, Any]:
    return _closeout_phase.run_closeout_phase(
        args,
        common,
        root=ROOT,
        phase_name=PHASE_CLOSEOUT,
        run_subprocess=_run_subprocess,
        stop_live_loop_processes=_stop_live_loop_processes,
        closeout_backup_liquidation=_closeout_backup_liquidation,
    )


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
    p.add_argument(
        "--generate-decision-story",
        action="store_true",
        help="Opt-in closeout generation for reports/dev/manual/decision_story. Disabled by default.",
    )
    p.add_argument(
        "--generate-run-cards",
        action="store_true",
        help="Opt-in closeout generation for reports/dev/manual/run_cards. Disabled by default.",
    )
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day).strip() if args.day else now_kst().strftime("%Y-%m-%d")
    report_root = _resolve_path(str(args.report_dir), "reports/dev/exam/mock_exam_day")
    canonical_reports_root = _resolve_path(str(os.getenv("REPORTS_ROOT", "reports")), "reports")
    report_root.mkdir(parents=True, exist_ok=True)
    orchestration_dir = report_root / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)

    common: Dict[str, Any] = {
        "root": ROOT,
        "day": day,
        "env_path": _resolve_path(str(args.env_path), ".env"),
        "report_root": report_root,
        "canonical_reports_root": canonical_reports_root,
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
        "canonical_reports_root": str(canonical_reports_root),
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
