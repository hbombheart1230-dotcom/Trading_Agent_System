"""Scheduler-agnostic daily post-market evaluation entry point (P1.2).

The ONLY thing a scheduler (current Windows Task, future Docker/Linux) may
do is invoke this script and check its exit code -- no Alpha Board or UEF
semantics belong in the scheduling layer itself.

  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29
  python scripts/run_daily_uef_evaluation.py --through-day 2026-09-29 --diagnostic

Exit code 0 only if the full Alpha Board -> UEF-7 -> UEF-8 -> UEF-9 chain
succeeded and UEF-9's authority_status is VALID. Any other outcome exits
non-zero and leaves reports/evaluation/alpha_research_board/latest.json
and .md untouched.

--diagnostic runs the same chain WITHOUT enforcing the freshness contracts,
for inspecting a stale/incomplete input set -- but a diagnostic run can
NEVER write any canonical file (dated board, latest.json/.md, or UEF-7/8/9
run directories), regardless of outcome; this is enforced inside
libs.reporting.evaluation.daily_uef_pipeline.run_daily_uef_evaluation
itself, not just by this CLI's own flag handling. A scheduler must never
pass --diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.daily_uef_pipeline import run_daily_uef_evaluation  # noqa: E402


def _source_sha() -> str:
    """Best-effort only: a Docker image or other deployment without a .git
    directory must never fail this entrypoint over a missing SHA."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
            text=True, timeout=5, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _log_lifecycle(*, run_id: str, day: str, event: str, level: str = "info", detail: dict | None = None) -> None:
    """Durable, immediate-flush START/END lifecycle record for this
    entrypoint (2026-10-01 HOST runtime pivot follow-up). Mirrors
    scripts/run_closeout_maintenance.py's own _log_lifecycle helper exactly
    -- same EventLogger (data/logs/events.jsonl, fsync'd on every write),
    same never-raises contract -- rather than inventing a second pattern
    for the same kind of entrypoint-boundary evidence.

    This is independent of, and does not replace, Windows Task Scheduler's
    own run history (LastRunTime/LastTaskResult) -- that only proves the
    scheduler itself fired and the process exited; it carries no target_day,
    source SHA, or failure-reason detail. Nor does it duplicate UEF
    authority itself -- the canonical generation's own COMPLETE.json (via
    libs.reporting.evaluation.daily_uef_pipeline) remains the sole authority
    for whether a day's evaluation is valid; these events are pure
    operational execution evidence (did this process start, with what
    identity, and how did it end), consulted for diagnosing a run that
    never reached that point at all (crash, hang, wrong day argument),
    which COMPLETE.json cannot explain since it is simply absent in that
    case.
    """
    try:
        from libs.core.event_logger import EventLogger, resolve_event_log_path

        EventLogger(resolve_event_log_path()).log(
            run_id=run_id,
            stage="daily_uef_evaluation_entrypoint",
            event=event,
            level=level,
            payload={"target_day": day, **(detail or {})},
        )
    except Exception:  # noqa: BLE001 - diagnostics must never break the real evaluation run
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-day", default=date.today().isoformat())
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Inspect the chain against current sources without the freshness contracts. "
             "Never writes any canonical file, whatever the outcome. Never use for a real daily run.",
    )
    args = parser.parse_args()
    day = str(args.through_day)[:10]
    canonical = not bool(args.diagnostic)
    run_id = f"daily-uef-{day}-{'canonical' if canonical else 'diagnostic'}-{os.getpid()}"
    started_at = time.time()

    _log_lifecycle(
        run_id=run_id, day=day, event="process_start",
        detail={
            "pid": os.getpid(),
            "started_at_epoch": started_at,
            "source_sha": _source_sha(),
            "canonical": canonical,
            "repo_root": str(args.repo_root),
        },
    )

    try:
        result = run_daily_uef_evaluation(
            repo_root=Path(args.repo_root),
            through_day=day,
            canonical=canonical,
        )
    except Exception as exc:
        _log_lifecycle(
            run_id=run_id, day=day, event="process_end", level="error",
            detail={
                "ended_at_epoch": time.time(),
                "result": "exception",
                "exit_code": 1,
                "canonical_generation": "",
                "failure_reason": f"{type(exc).__name__}: {exc}",
            },
        )
        raise

    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    exit_code = 0 if result.ok else 1
    _log_lifecycle(
        run_id=run_id, day=day, event="process_end",
        level="info" if result.ok else "error",
        detail={
            "ended_at_epoch": time.time(),
            "result": "ok" if result.ok else "failed",
            "exit_code": exit_code,
            "canonical_generation": str(payload.get("authority_id") or payload.get("uef9_run_id") or ""),
            "failure_reason": "" if result.ok else str(payload.get("reason") or ""),
        },
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
