from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.closeout_maintenance import (
    run_closeout_maintenance_with_lock,
    write_closeout_maintenance_report,
)
from libs.reporting.scheduled_intelligence import materialize_closeout_intelligence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run end-of-day closeout maintenance artifacts.")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--reports-root", default="reports")
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--post-exit-report-dir", default="reports/dev/analysis/post_exit_shadow_recap")
    parser.add_argument("--state-path", default="")
    parser.add_argument("--trigger", default="manual_closeout_maintenance")
    parser.add_argument("--skip-account-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _log_lifecycle(*, run_id: str, day: str, event: str, level: str = "info", detail: dict | None = None) -> None:
    """Durable, immediate-flush lifecycle record for this entrypoint
    (2026-09-30 closeout diagnostic hardening). Uses the existing
    EventLogger (data/logs/events.jsonl, fsync'd on every write) --
    NOT a new logging surface, and never raises: a diagnostic-logging
    failure must never break closeout maintenance itself.

    Why this exists: the wrapping .bat (scripts/run_closeout_maintenance.bat)
    already writes a per-invocation log
    (reports/runtime/closeout_maintenance_<date>_<time>.log) with a start
    line and an exit line -- but on 2026-09-28 that log showed only those
    two lines with nothing in between across a ~10m37s run that ended
    rc=1, and on 2026-09-29 the run was interrupted (^C /
    STATUS_CONTROL_C_EXIT) before this script's own print statements
    (which only run at the very end of main(), after everything else
    completes) ever executed. Neither failure left any trace of what the
    process was actually doing. These lifecycle events are written
    immediately, at each stage boundary, specifically so the next
    occurrence leaves a durable trace even if the process is later killed
    or hangs indefinitely.
    """
    try:
        from libs.core.event_logger import EventLogger, resolve_event_log_path

        EventLogger(resolve_event_log_path()).log(
            run_id=run_id,
            stage="closeout_maintenance_entrypoint",
            event=event,
            level=level,
            payload={"target_day": day, **(detail or {})},
        )
    except Exception:  # noqa: BLE001 - diagnostics must never break closeout maintenance
        pass


def main() -> int:
    args = _build_parser().parse_args()
    reports_root = Path(str(args.reports_root))
    day = str(args.day)[:10]
    trigger = str(args.trigger)
    run_id = f"closeout-cli-{day}-{trigger}"

    _log_lifecycle(run_id=run_id, day=day, event="process_start", detail={"trigger": trigger})
    try:
        _log_lifecycle(run_id=run_id, day=day, event="closeout_start", detail={"trigger": trigger})
        # 2026-09-30 closeout single-owner safety fix: this entrypoint and
        # the tick-loop trigger (libs/runtime/market_status_closeout.py)
        # both used to call run_closeout_maintenance() directly, with no
        # coordination -- nothing prevented both from executing
        # concurrently. run_closeout_maintenance_with_lock() wraps the
        # exact same call with a PID-based single-owner lock (reusing
        # libs/runtime/live_loop_lock.py, already proven for the m13 live
        # loop's own single-instance guard); see its own docstring for the
        # full design.
        payload = run_closeout_maintenance_with_lock(
            day=day,
            reports_root=reports_root,
            event_log_path=Path(str(args.event_log_path)),
            post_exit_report_dir=Path(str(args.post_exit_report_dir)),
            state_path=Path(str(args.state_path)) if str(args.state_path or "").strip() else None,
            trigger=trigger,
            collect_account_snapshot=not bool(args.skip_account_snapshot),
            run_id=run_id,
        )
        _log_lifecycle(
            run_id=run_id, day=day, event="closeout_end",
            detail={"ok": bool(payload.get("ok")), "skipped": bool(payload.get("skipped"))},
        )

        if payload.get("skipped"):
            # Another owner (the tick-loop trigger, or a still-active prior
            # fallback run) is genuinely running this same closeout right
            # now -- do not write a report or run scheduled intelligence
            # here, to avoid a race against whatever the real owner is
            # about to write. This is a clean, expected skip, not a
            # failure.
            paths: dict = {}
        else:
            _log_lifecycle(run_id=run_id, day=day, event="report_write_start")
            paths = write_closeout_maintenance_report(payload, reports_root=reports_root)
            payload["report_paths"] = dict(paths)
            _log_lifecycle(run_id=run_id, day=day, event="report_write_end", detail={"paths": dict(paths)})

            _log_lifecycle(run_id=run_id, day=day, event="scheduled_intelligence_start")
            try:
                payload["scheduled_intelligence"] = materialize_closeout_intelligence(
                    day=day,
                    closeout_payload=payload,
                    closeout_paths=paths,
                    reports_root=reports_root,
                )
            except Exception as exc:
                payload["scheduled_intelligence"] = {"status": "FAILED", "error": str(exc)}
            _log_lifecycle(run_id=run_id, day=day, event="scheduled_intelligence_end")
    except Exception as exc:
        _log_lifecycle(
            run_id=run_id, day=day, event="process_exception", level="error",
            detail={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:2000],
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:8000],
            },
        )
        _log_lifecycle(run_id=run_id, day=day, event="process_exit", detail={"exit_code": 1, "reason": "exception"})
        raise

    if bool(args.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif payload.get("skipped"):
        print(f"skipped=True skip_reason={payload.get('skip_reason')}")
    else:
        print(f"ok={bool(payload.get('ok'))} report_json={paths.get('report_json_path')} report_md={paths.get('report_md_path')}")
        for name, step in (payload.get("steps") or {}).items():
            if isinstance(step, dict):
                print(f"{name}={'ok' if step.get('ok') else 'failed'}")
    # A skipped run (ownership not acquired -- ALREADY_RUNNING) is a clean,
    # expected outcome of the single-owner guard, not a failure.
    exit_code = 0 if (bool(payload.get("ok")) or bool(payload.get("skipped"))) else 1
    _log_lifecycle(
        run_id=run_id, day=day, event="process_exit",
        detail={"exit_code": exit_code, "reason": "skipped" if payload.get("skipped") else "completed"},
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
