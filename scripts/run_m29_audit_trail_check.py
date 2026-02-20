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

from scripts.check_audit_trail_completeness import main as audit_main


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_json(argv: List[str]) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = audit_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M29 audit trail completeness check.")
    p.add_argument("--event-log-path", default="data/logs/m29_audit_events.jsonl")
    p.add_argument("--report-dir", default="reports/m29_audit")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _seed_events(path: Path, *, day: str, inject_fail: bool) -> None:
    rows: List[Dict[str, Any]] = [
        {
            "ts": f"{day}T00:00:00+00:00",
            "run_id": "run_ok_1",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1}}},
        },
        {
            "ts": f"{day}T00:00:01+00:00",
            "run_id": "run_ok_1",
            "stage": "execute_from_packet",
            "event": "start",
            "payload": {},
        },
        {
            "ts": f"{day}T00:00:02+00:00",
            "run_id": "run_ok_1",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": True},
        },
        {
            "ts": f"{day}T00:00:03+00:00",
            "run_id": "run_ok_1",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"allowed": True},
        },
        {
            "ts": f"{day}T00:00:04+00:00",
            "run_id": "run_ok_1",
            "stage": "execute_from_packet",
            "event": "end",
            "payload": {"ok": True},
        },
        {
            "ts": f"{day}T00:01:00+00:00",
            "run_id": "run_ok_2",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "SELL", "symbol": "000660", "qty": 1}}},
        },
        {
            "ts": f"{day}T00:01:01+00:00",
            "run_id": "run_ok_2",
            "stage": "execute_from_packet",
            "event": "start",
            "payload": {},
        },
        {
            "ts": f"{day}T00:01:02+00:00",
            "run_id": "run_ok_2",
            "stage": "execute_from_packet",
            "event": "degrade_policy_block",
            "payload": {"reason": "degrade_manual_approval_required"},
        },
        {
            "ts": f"{day}T00:01:03+00:00",
            "run_id": "run_ok_2",
            "stage": "execute_from_packet",
            "event": "end",
            "payload": {"ok": True},
        },
        {
            "ts": f"{day}T00:02:00+00:00",
            "run_id": "run_noop",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "NOOP"}}},
        },
    ]

    if inject_fail:
        rows += [
            {
                "ts": f"{day}T00:03:00+00:00",
                "run_id": "run_fail_payload",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "035420", "qty": 1}}},
            },
            {
                "ts": f"{day}T00:03:01+00:00",
                "run_id": "run_fail_payload",
                "stage": "execute_from_packet",
                "event": "start",
                "payload": {},
            },
            {
                "ts": f"{day}T00:03:02+00:00",
                "run_id": "run_fail_payload",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "ts": f"{day}T00:03:03+00:00",
                "run_id": "run_fail_payload",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
            },
            {
                "ts": f"{day}T00:04:00+00:00",
                "run_id": "run_fail_start",
                "stage": "decision",
                "event": "trace",
                "payload": {"decision_packet": {"intent": {"action": "SELL", "symbol": "051910", "qty": 1}}},
            },
            {
                "ts": f"{day}T00:04:01+00:00",
                "run_id": "run_fail_start",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": False, "reason": "blocked"},
            },
            {
                "ts": f"{day}T00:04:02+00:00",
                "run_id": "run_fail_start",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
            },
            {
                "ts": f"{day}T00:05:00+00:00",
                "run_id": "run_orphan_exec",
                "stage": "execute_from_packet",
                "event": "start",
                "payload": {},
            },
            {
                "ts": f"{day}T00:05:01+00:00",
                "run_id": "run_orphan_exec",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "ts": f"{day}T00:05:02+00:00",
                "run_id": "run_orphan_exec",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"allowed": True},
            },
            {
                "ts": f"{day}T00:05:03+00:00",
                "run_id": "run_orphan_exec",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
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

    rc, audit = _run_json(
        [
            "--event-log-path",
            str(events_path),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--require-actionable",
            "--json",
        ]
    )

    failures: List[str] = []
    expected_ok = not inject_fail

    if expected_ok:
        if rc != 0:
            failures.append("audit_check rc != 0")
        if not bool(audit.get("ok")):
            failures.append("audit_check ok != true")
        if int(audit.get("actionable_decision_run_total") or 0) < 2:
            failures.append("actionable_decision_run_total < 2")
        if int(audit.get("linked_complete_run_total") or 0) < 2:
            failures.append("linked_complete_run_total < 2")
    else:
        if rc == 0:
            failures.append("inject_fail expected rc != 0")
        if bool(audit.get("ok")):
            failures.append("inject_fail expected ok == false")
        anomaly_total = (
            int(audit.get("missing_execution_start_total") or 0)
            + int(audit.get("missing_execution_payload_total") or 0)
            + int(audit.get("orphan_execution_run_total") or 0)
        )
        if anomaly_total < 1:
            failures.append("inject_fail expected anomaly_total >= 1")

    overall_ok = len(failures) == 0 and not inject_fail
    if inject_fail and len(failures) == 0:
        failures.append("inject_fail scenario: expected non-zero closeout result")

    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "event_log_path": str(events_path),
        "report_dir": str(report_dir),
        "audit": {
            "rc": int(rc),
            "ok": bool(audit.get("ok")) if isinstance(audit, dict) else False,
            "actionable_decision_run_total": int(audit.get("actionable_decision_run_total") or 0)
            if isinstance(audit, dict)
            else 0,
            "linked_complete_run_total": int(audit.get("linked_complete_run_total") or 0)
            if isinstance(audit, dict)
            else 0,
            "missing_execution_start_total": int(audit.get("missing_execution_start_total") or 0)
            if isinstance(audit, dict)
            else 0,
            "missing_execution_payload_total": int(audit.get("missing_execution_payload_total") or 0)
            if isinstance(audit, dict)
            else 0,
            "orphan_execution_run_total": int(audit.get("orphan_execution_run_total") or 0)
            if isinstance(audit, dict)
            else 0,
            "report_json_path": str(audit.get("report_json_path") or "") if isinstance(audit, dict) else "",
            "report_md_path": str(audit.get("report_md_path") or "") if isinstance(audit, dict) else "",
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} linked_complete={out['audit']['linked_complete_run_total']} "
            f"missing_start={out['audit']['missing_execution_start_total']} "
            f"orphan_execution={out['audit']['orphan_execution_run_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
