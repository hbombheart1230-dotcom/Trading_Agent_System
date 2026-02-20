from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m29_audit_trail_check import main as m29_5_main
from scripts.run_m29_disaster_recovery_drill import main as m29_8_main
from scripts.run_m29_incident_timeline_check import main as m29_7_main
from scripts.run_m29_log_archive_integrity_check import main as m29_6_main


def _run_json(main_fn, argv: List[str]) -> Tuple[int, Dict[str, Any]]:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main_fn(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M29 governance closeout check (audit/archive/timeline/dr).")
    p.add_argument("--event-log-dir", default="data/logs/m29_closeout")
    p.add_argument("--report-dir", default="reports/m29_closeout")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    event_log_dir = Path(str(args.event_log_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        if event_log_dir.exists():
            shutil.rmtree(event_log_dir, ignore_errors=True)
        if report_dir.exists():
            shutil.rmtree(report_dir, ignore_errors=True)

    event_log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    m29_5_argv = [
        "--event-log-path",
        str(event_log_dir / "m29_5_events.jsonl"),
        "--report-dir",
        str(report_dir / "m29_5_audit"),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m29_5_argv.insert(-1, "--inject-fail")
    m29_5_rc, m29_5 = _run_json(m29_5_main, m29_5_argv)

    m29_6_argv = [
        "--archive-dir",
        str(event_log_dir / "m29_6_archive"),
        "--report-dir",
        str(report_dir / "m29_6_archive"),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m29_6_argv.insert(-1, "--inject-fail")
    m29_6_rc, m29_6 = _run_json(m29_6_main, m29_6_argv)

    m29_7_argv = [
        "--event-log-path",
        str(event_log_dir / "m29_7_events.jsonl"),
        "--report-dir",
        str(report_dir / "m29_7_timeline"),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m29_7_argv.insert(-1, "--inject-fail")
    m29_7_rc, m29_7 = _run_json(m29_7_main, m29_7_argv)

    m29_8_argv = [
        "--working-dataset-root",
        str(event_log_dir / "m29_8_working_dataset"),
        "--archive-dir",
        str(event_log_dir / "m29_8_archive"),
        "--restored-dataset-root",
        str(event_log_dir / "m29_8_restored_dataset"),
        "--report-dir",
        str(report_dir / "m29_8_disaster_recovery"),
        "--day",
        day,
        "--json",
    ]
    if inject_fail:
        m29_8_argv.insert(-1, "--inject-fail")
    m29_8_rc, m29_8 = _run_json(m29_8_main, m29_8_argv)

    failures: List[str] = []
    checks = [
        ("m29_5", m29_5_rc, m29_5),
        ("m29_6", m29_6_rc, m29_6),
        ("m29_7", m29_7_rc, m29_7),
        ("m29_8", m29_8_rc, m29_8),
    ]

    if not inject_fail:
        for name, rc, obj in checks:
            if int(rc) != 0:
                failures.append(f"{name} rc != 0")
            if obj and not bool(obj.get("ok")):
                failures.append(f"{name} ok != true")

        if int(((m29_5.get("audit") or {}).get("linked_complete_run_total") or 0)) < 2:
            failures.append("m29_5 linked_complete_run_total < 2")
        if int(((m29_6.get("integrity") or {}).get("verified_total") or 0)) < 1:
            failures.append("m29_6 verified_total < 1")
        if int(((m29_7.get("timeline") or {}).get("unresolved_incident_total") or 0)) != 0:
            failures.append("m29_7 unresolved_incident_total != 0")
        if bool(((m29_8.get("parity") or {}).get("ok")) is not True):
            failures.append("m29_8 parity.ok != true")
    else:
        failing_subchecks = 0
        for _name, rc, obj in checks:
            if int(rc) != 0 or not bool(obj.get("ok")):
                failing_subchecks += 1
        if failing_subchecks < 1:
            failures.append("inject_fail expected at least one failing subcheck")

    overall_ok = len(failures) == 0 and not inject_fail

    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "event_log_dir": str(event_log_dir),
        "report_dir": str(report_dir),
        "m29_5_audit": {
            "rc": int(m29_5_rc),
            "ok": bool(m29_5.get("ok")) if isinstance(m29_5, dict) else False,
            "linked_complete_run_total": int(((m29_5.get("audit") or {}).get("linked_complete_run_total") or 0))
            if isinstance(m29_5, dict)
            else 0,
        },
        "m29_6_archive_integrity": {
            "rc": int(m29_6_rc),
            "ok": bool(m29_6.get("ok")) if isinstance(m29_6, dict) else False,
            "verified_total": int(((m29_6.get("integrity") or {}).get("verified_total") or 0))
            if isinstance(m29_6, dict)
            else 0,
            "hash_mismatch_total": int(((m29_6.get("integrity") or {}).get("hash_mismatch_total") or 0))
            if isinstance(m29_6, dict)
            else 0,
        },
        "m29_7_timeline": {
            "rc": int(m29_7_rc),
            "ok": bool(m29_7.get("ok")) if isinstance(m29_7, dict) else False,
            "incident_total": int(((m29_7.get("timeline") or {}).get("incident_total") or 0))
            if isinstance(m29_7, dict)
            else 0,
            "unresolved_incident_total": int(((m29_7.get("timeline") or {}).get("unresolved_incident_total") or 0))
            if isinstance(m29_7, dict)
            else 0,
        },
        "m29_8_disaster_recovery": {
            "rc": int(m29_8_rc),
            "ok": bool(m29_8.get("ok")) if isinstance(m29_8, dict) else False,
            "parity_ok": bool(((m29_8.get("parity") or {}).get("ok"))) if isinstance(m29_8, dict) else False,
            "archive_hash_mismatch_total": int(((m29_8.get("archive_integrity") or {}).get("hash_mismatch_total") or 0))
            if isinstance(m29_8, dict)
            else 0,
        },
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} "
            f"audit_linked={out['m29_5_audit']['linked_complete_run_total']} "
            f"archive_verified={out['m29_6_archive_integrity']['verified_total']} "
            f"timeline_unresolved={out['m29_7_timeline']['unresolved_incident_total']} "
            f"dr_parity_ok={out['m29_8_disaster_recovery']['parity_ok']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
