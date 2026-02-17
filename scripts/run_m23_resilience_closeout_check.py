from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.commander_runtime import run_commander_runtime
from libs.core.event_logger import EventLogger
from scripts.query_commander_resilience_events import main as query_commander_main


def _graph_ok(state: Dict[str, Any]) -> Dict[str, Any]:
    state["path"] = "graph_spine"
    return state


def _graph_error(state: Dict[str, Any]) -> Dict[str, Any]:
    raise RuntimeError("m23_closeout_runtime_error")


def _run_cooldown_case(*, logger: EventLogger) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": "m23-closeout-cooldown",
        "event_logger": logger,
        "now_epoch": 100,
        "resilience": {"incident_count": 5, "cooldown_until_epoch": 200},
        "resilience_policy": {"incident_threshold": 3, "cooldown_sec": 60},
    }
    return run_commander_runtime(state, graph_runner=_graph_ok)


def _run_resume_case(*, logger: EventLogger) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": "m23-closeout-resume",
        "event_logger": logger,
        "runtime_control": "resume",
        "now_epoch": 210,
        "resilience": {
            "degrade_mode": True,
            "degrade_reason": "incident_threshold_cooldown",
            "incident_count": 4,
            "cooldown_until_epoch": 260,
            "last_error_type": "TimeoutError",
        },
        "resilience_policy": {"incident_threshold": 3, "cooldown_sec": 60},
    }
    return run_commander_runtime(state, graph_runner=_graph_ok)


def _run_error_case(*, logger: EventLogger) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "run_id": "m23-closeout-error",
        "event_logger": logger,
        "now_epoch": 300,
        "resilience": {"incident_count": 0, "cooldown_until_epoch": 0},
        "resilience_policy": {"incident_threshold": 2, "cooldown_sec": 60},
    }
    try:
        run_commander_runtime(state, graph_runner=_graph_error)
    except RuntimeError:
        pass
    return state


def _query_summary_json(events_path: Path) -> tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = query_commander_main(
            [
                "--path",
                str(events_path),
                "--json",
            ]
        )
    text = buf.getvalue().strip()
    if not text:
        return int(rc), {}
    try:
        return int(rc), json.loads(text)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M23 closeout check (commander resilience + operator resume + incident logs)")
    p.add_argument("--event-log-path", default="data/logs/m23_closeout_events.jsonl")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--skip-error-case", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    events_path = Path(args.event_log_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    if (not args.no_clear) and events_path.exists():
        events_path.unlink()

    logger = EventLogger(log_path=events_path)

    cooldown_out = _run_cooldown_case(logger=logger)
    resume_out = _run_resume_case(logger=logger)
    error_out = {}
    if not bool(args.skip_error_case):
        error_out = _run_error_case(logger=logger)

    q_rc, q_obj = _query_summary_json(events_path)
    q_summary = q_obj.get("summary") if isinstance(q_obj.get("summary"), dict) else {}

    cooldown_transition_total = int(q_summary.get("cooldown_transition_total") or 0)
    intervention_total = int(q_summary.get("intervention_total") or 0)
    error_total = int(q_summary.get("error_total") or 0)

    ok = True
    failures: List[str] = []

    if str(cooldown_out.get("runtime_status") or "") != "cooldown_wait":
        ok = False
        failures.append("cooldown case runtime_status != cooldown_wait")
    if bool((cooldown_out.get("resilience") or {}).get("degrade_mode")) is not True:
        ok = False
        failures.append("cooldown case degrade_mode != true")

    if str(resume_out.get("runtime_status") or "") != "resuming":
        ok = False
        failures.append("resume case runtime_status != resuming")
    if str(resume_out.get("path") or "") != "graph_spine":
        ok = False
        failures.append("resume case path != graph_spine")
    if bool((resume_out.get("resilience") or {}).get("degrade_mode")) is not False:
        ok = False
        failures.append("resume case degrade_mode != false")

    if q_rc != 0:
        ok = False
        failures.append("query_commander_resilience_events rc != 0")
    if cooldown_transition_total < 1:
        ok = False
        failures.append("cooldown_transition_total < 1")
    if intervention_total < 1:
        ok = False
        failures.append("intervention_total < 1")
    if error_total < 1:
        ok = False
        failures.append("error_total < 1")

    if not bool(args.skip_error_case):
        resilience = error_out.get("resilience") if isinstance(error_out.get("resilience"), dict) else {}
        if str(error_out.get("runtime_status") or "") != "error":
            ok = False
            failures.append("error case runtime_status != error")
        if int(resilience.get("incident_count") or 0) < 1:
            ok = False
            failures.append("error case incident_count < 1")

    summary = {
        "ok": bool(ok),
        "events_path": str(events_path),
        "query_summary": {
            "cooldown_transition_total": cooldown_transition_total,
            "intervention_total": intervention_total,
            "error_total": error_total,
            "latest_status": q_summary.get("latest_status"),
            "latest_run_id": q_summary.get("latest_run_id"),
        },
        "failures": failures,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"ok={summary['ok']} cooldown_transition_total={cooldown_transition_total} "
            f"intervention_total={intervention_total} error_total={error_total}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
