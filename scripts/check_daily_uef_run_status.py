"""Operator-facing Daily UEF run-status classifier (HOST OPS FINAL FIX, B3).

Read-only. Cross-references two independent sources of evidence for a given
target_day and reports one of four states an operator can act on without
having to read raw logs by hand:

  SCHEDULED_AND_RAN        -- Windows Task Scheduler's own history shows the
                               task fired for this day (LastRunTime matches
                               the day) and exited 0. A scheduler-level
                               cross-check only -- never treated as proof the
                               evaluation itself succeeded (see STARTED_AND_*
                               below, which is the entrypoint's own evidence).
  SCHEDULED_BUT_NOT_STARTED -- No scheduler run recorded for this day, and no
                               durable process_start event for this day
                               either. The task may be disabled, the trigger
                               may not have fired yet, or it may be genuinely
                               missing -- this script does not guess which.
  STARTED_AND_FAILED        -- A process_start event exists for this day, but
                               either the matching process_end recorded a
                               non-ok result, or no process_end was ever
                               recorded at all (the process crashed or hung
                               without reaching its own end-of-run logging).
  STARTED_AND_COMPLETED     -- A process_start event exists for this day with
                               a matching process_end recording result="ok".

Deliberately does NOT infer success from "the task is Enabled" -- that only
proves the task definition exists, not that anything ran. Evidence source:
scripts/run_daily_uef_evaluation.py's own durable START/END lifecycle events
in data/logs/events.jsonl (stage="daily_uef_evaluation_entrypoint") -- this
is pure operational execution evidence, never evaluation authority; it does
not read or alter reports/evaluation/alpha_research_board/**/COMPLETE.json or
any registry, which remain the sole authority for whether a day's UEF
evaluation is itself valid.

The events.jsonl file is append-only and can grow very large (close to 1GB
in this repository) -- this scans it with a single streaming forward pass
and a cheap substring pre-filter before JSON-decoding each candidate line,
rather than loading the file into memory.

  python scripts/check_daily_uef_run_status.py --day 2026-10-01
  python scripts/check_daily_uef_run_status.py --day 2026-10-01 --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _scan_entrypoint_events(event_log_path: Path, day: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Single forward streaming pass; keeps only the LATEST process_start and
    LATEST process_end whose own payload.target_day matches `day` (a day can
    have more than one attempt -- e.g. a failed run followed by a retry --
    and the most recent attempt is what an operator cares about)."""
    latest_start: Optional[Dict[str, Any]] = None
    latest_end: Optional[Dict[str, Any]] = None
    if not event_log_path.exists():
        return {"process_start": None, "process_end": None}

    with event_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "daily_uef_evaluation_entrypoint" not in line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("stage") != "daily_uef_evaluation_entrypoint":
                continue
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            if str(payload.get("target_day") or "") != day:
                continue
            event = str(record.get("event") or "")
            if event == "process_start":
                if latest_start is None or str(record.get("ts") or "") >= str(latest_start.get("ts") or ""):
                    latest_start = record
            elif event == "process_end":
                if latest_end is None or str(record.get("ts") or "") >= str(latest_end.get("ts") or ""):
                    latest_end = record
    return {"process_start": latest_start, "process_end": latest_end}


def _scheduler_cross_check(task_name: str, day: str) -> Dict[str, Any]:
    """Best-effort only -- this script must still produce an entrypoint-
    evidence-based classification on a non-Windows host, or if Task
    Scheduler itself is unreachable for any reason."""
    try:
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                f"$i = Get-ScheduledTaskInfo -TaskName '{task_name}' -ErrorAction Stop; "
                "@{LastRunTime=$i.LastRunTime.ToString('o'); LastTaskResult=$i.LastTaskResult; "
                "NextRunTime=$i.NextRunTime.ToString('o'); NumberOfMissedRuns=$i.NumberOfMissedRuns} | ConvertTo-Json",
            ],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {"available": False, "reason": proc.stderr.strip()[:500]}
        info = json.loads(proc.stdout)
        last_run_day = str(info.get("LastRunTime") or "")[:10]
        return {
            "available": True,
            "last_run_time": info.get("LastRunTime"),
            "last_run_matches_day": last_run_day == day,
            "last_task_result": info.get("LastTaskResult"),
            "last_task_result_ok": info.get("LastTaskResult") == 0,
            "next_run_time": info.get("NextRunTime"),
            "number_of_missed_runs": info.get("NumberOfMissedRuns"),
        }
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def classify(*, day: str, event_log_path: Path, task_name: str) -> Dict[str, Any]:
    events = _scan_entrypoint_events(event_log_path, day)
    scheduler = _scheduler_cross_check(task_name, day)
    start = events["process_start"]
    end = events["process_end"]

    if start is None:
        status = "SCHEDULED_AND_RAN" if scheduler.get("last_run_matches_day") and scheduler.get("last_task_result_ok") else "SCHEDULED_BUT_NOT_STARTED"
    elif end is not None and str(end.get("payload", {}).get("result") or "") == "ok":
        status = "STARTED_AND_COMPLETED"
    else:
        # Started, and either ended with a non-ok result or never ended at
        # all (crash/hang) -- both are failures from an operator's
        # perspective: the day's evaluation did not durably complete.
        status = "STARTED_AND_FAILED"

    return {
        "schema_version": "daily_uef_run_status.v1",
        "target_day": day,
        "status": status,
        "entrypoint_evidence": {
            "process_start": (start or {}).get("payload"),
            "process_end": (end or {}).get("payload"),
        },
        "scheduler_cross_check": scheduler,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--event-log-path", default="data/logs/events.jsonl")
    parser.add_argument("--task-name", default="TradingAgent-DailyUefEvaluation")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = classify(
        day=str(args.day)[:10],
        event_log_path=Path(args.event_log_path),
        task_name=str(args.task_name),
    )
    if bool(args.json):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"target_day={result['target_day']} status={result['status']}")
        sc = result["scheduler_cross_check"]
        if sc.get("available"):
            print(f"scheduler: last_run_time={sc.get('last_run_time')} last_task_result={sc.get('last_task_result')} missed_runs={sc.get('number_of_missed_runs')}")
        else:
            print(f"scheduler: unavailable ({sc.get('reason')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
