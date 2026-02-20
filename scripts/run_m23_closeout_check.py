from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_metrics_report import generate_metrics_report
from scripts.run_m23_resilience_closeout_check import main as resilience_closeout_main


def _run_resilience_closeout_json(
    *,
    events_path: Path,
    no_clear: bool,
    skip_error_case: bool,
) -> Tuple[int, Dict[str, Any]]:
    argv = ["--event-log-path", str(events_path), "--json"]
    if no_clear:
        argv.append("--no-clear")
    if skip_error_case:
        argv.append("--skip-error-case")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = resilience_closeout_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M23 final closeout check (resilience runtime + metrics + handover)")
    p.add_argument("--event-log-path", default="data/logs/m23_closeout_events.jsonl")
    p.add_argument("--report-dir", default="reports/m23_closeout")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--skip-error-case", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    events_path = Path(args.event_log_path)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    rc, base = _run_resilience_closeout_json(
        events_path=events_path,
        no_clear=bool(args.no_clear),
        skip_error_case=bool(args.skip_error_case),
    )

    requested_day = str(args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    _, js = generate_metrics_report(events_path, report_dir, day=requested_day)
    metrics = json.loads(js.read_text(encoding="utf-8"))

    # Compatibility fallback:
    # If a past day is requested but this closeout run generated events on "today",
    # recalculate using latest-day mode so scripted closeout checks remain reproducible.
    commander_resilience_probe = (
        metrics.get("commander_resilience")
        if isinstance(metrics.get("commander_resilience"), dict)
        else {}
    )
    probe_total = int(commander_resilience_probe.get("total") or 0)
    if probe_total < 1 and args.day:
        try:
            req_date = datetime.strptime(requested_day, "%Y-%m-%d").date()
            today_utc = datetime.now(timezone.utc).date()
        except Exception:
            req_date = None
            today_utc = None
        if req_date is not None and today_utc is not None and req_date <= today_utc:
            _, js = generate_metrics_report(events_path, report_dir, day=None)
            metrics = json.loads(js.read_text(encoding="utf-8"))

    commander_resilience = (
        metrics.get("commander_resilience")
        if isinstance(metrics.get("commander_resilience"), dict)
        else {}
    )
    total = int(commander_resilience.get("total") or 0)
    cooldown_transition_total = int(commander_resilience.get("cooldown_transition_total") or 0)
    intervention_total = int(commander_resilience.get("intervention_total") or 0)
    error_total = int(commander_resilience.get("error_total") or 0)

    ok = True
    failures: List[str] = []
    if rc != 0:
        ok = False
        failures.append("m23_resilience_closeout rc != 0")
    if base and not bool(base.get("ok")):
        ok = False
        failures.append("m23_resilience_closeout ok != true")
    if total < 1:
        ok = False
        failures.append("commander_resilience.total < 1")
    if cooldown_transition_total < 1:
        ok = False
        failures.append("commander_resilience.cooldown_transition_total < 1")
    if intervention_total < 1:
        ok = False
        failures.append("commander_resilience.intervention_total < 1")
    if error_total < 1:
        ok = False
        failures.append("commander_resilience.error_total < 1")

    summary = {
        "ok": bool(ok),
        "day": requested_day,
        "events_path": str(events_path),
        "metrics_json_path": str(js),
        "resilience_closeout": {
            "rc": int(rc),
            "ok": bool(base.get("ok")) if isinstance(base, dict) else False,
            "query_summary": base.get("query_summary") if isinstance(base, dict) else {},
        },
        "commander_resilience": {
            "total": total,
            "cooldown_transition_total": cooldown_transition_total,
            "intervention_total": intervention_total,
            "error_total": error_total,
        },
        "failures": failures,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"ok={summary['ok']} day={day} commander_total={total} "
            f"cooldown_transition_total={cooldown_transition_total} "
            f"intervention_total={intervention_total} error_total={error_total}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
