from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconstruct_incident_timeline import main as reconstruct_main


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_json(argv: List[str]) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = reconstruct_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M29-7 incident timeline reconstruction closeout check.")
    p.add_argument("--event-log-path", default="data/logs/m29_incident_timeline_events.jsonl")
    p.add_argument("--report-dir", default="reports/m29_incident_timeline")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _seed_events(path: Path, *, day: str, inject_fail: bool) -> None:
    rows: List[Dict[str, Any]] = [
        {
            "ts": f"{day}T00:00:00+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "route",
            "payload": {"mode": "graph_spine"},
        },
        {
            "ts": f"{day}T00:00:10+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "transition",
            "payload": {"transition": "cooldown", "status": "cooldown_wait", "reason": "incident_threshold_cooldown"},
        },
        {
            "ts": f"{day}T00:00:20+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "resilience",
            "payload": {"reason": "cooldown_active", "incident_count": 3},
        },
        {
            "ts": f"{day}T00:00:40+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "intervention",
            "payload": {"type": "operator_resume", "at_epoch": 1700000040},
        },
        {
            "ts": f"{day}T00:00:55+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "resilience",
            "payload": {"reason": "cooldown_not_active", "incident_count": 0},
        },
        {
            "ts": f"{day}T00:01:00+00:00",
            "run_id": "run_incident_1",
            "stage": "commander_router",
            "event": "end",
            "payload": {"status": "resuming", "path": "graph_spine"},
        },
        {
            "ts": f"{day}T00:02:00+00:00",
            "run_id": "run_incident_2",
            "stage": "commander_router",
            "event": "error",
            "payload": {"error_type": "RuntimeError", "error": "boom"},
        },
        {
            "ts": f"{day}T00:02:20+00:00",
            "run_id": "run_incident_2",
            "stage": "commander_router",
            "event": "end",
            "payload": {"status": "ok", "path": "graph_spine"},
        },
        {
            "ts": f"{day}T00:03:00+00:00",
            "run_id": "run_noise",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "NOOP"}}},
        },
    ]

    if inject_fail:
        rows += [
            {
                "ts": f"{day}T00:04:00+00:00",
                "run_id": "run_unresolved",
                "stage": "commander_router",
                "event": "error",
                "payload": {"error_type": "RuntimeError", "error": "still_broken"},
            },
            {
                "ts": f"{day}T00:04:20+00:00",
                "run_id": "run_unresolved",
                "stage": "commander_router",
                "event": "resilience",
                "payload": {"reason": "cooldown_active", "incident_count": 5},
            },
        ]

    _write_jsonl(path, rows)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    inject_fail = bool(args.inject_fail)

    _seed_events(events_path, day=day, inject_fail=inject_fail)

    rc, reconstructed = _run_json(
        [
            "--event-log-path",
            str(events_path),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--require-incidents",
            "--require-recovered",
            "--json",
        ]
    )

    failures: List[str] = []
    expected_ok = not inject_fail
    if expected_ok:
        if rc != 0:
            failures.append("reconstruct_check rc != 0")
        if not bool(reconstructed.get("ok")):
            failures.append("reconstruct_check ok != true")
        if int(reconstructed.get("incident_total") or 0) < 2:
            failures.append("incident_total < 2")
        if int(reconstructed.get("unresolved_incident_total") or 0) != 0:
            failures.append("unresolved_incident_total != 0")
    else:
        if rc == 0:
            failures.append("inject_fail expected rc != 0")
        if bool(reconstructed.get("ok")):
            failures.append("inject_fail expected ok == false")
        if int(reconstructed.get("unresolved_incident_total") or 0) < 1:
            failures.append("inject_fail unresolved_incident_total < 1")

    overall_ok = len(failures) == 0 and expected_ok
    if inject_fail and len(failures) == 0:
        failures.append("inject_fail scenario: expected non-zero closeout result")

    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "event_log_path": str(events_path),
        "report_dir": str(report_dir),
        "timeline": {
            "rc": int(rc),
            "ok": bool(reconstructed.get("ok")) if isinstance(reconstructed, dict) else False,
            "incident_total": int(reconstructed.get("incident_total") or 0) if isinstance(reconstructed, dict) else 0,
            "recovered_incident_total": int(reconstructed.get("recovered_incident_total") or 0)
            if isinstance(reconstructed, dict)
            else 0,
            "unresolved_incident_total": int(reconstructed.get("unresolved_incident_total") or 0)
            if isinstance(reconstructed, dict)
            else 0,
            "report_json_path": str(reconstructed.get("report_json_path") or "") if isinstance(reconstructed, dict) else "",
            "report_md_path": str(reconstructed.get("report_md_path") or "") if isinstance(reconstructed, dict) else "",
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} incident_total={out['timeline']['incident_total']} "
            f"recovered_incident_total={out['timeline']['recovered_incident_total']} "
            f"unresolved_incident_total={out['timeline']['unresolved_incident_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
