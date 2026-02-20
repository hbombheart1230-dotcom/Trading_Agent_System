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

from scripts.query_m25_notification_events import main as query_main


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M27-9 portfolio guard notify ops query check.")
    p.add_argument("--event-log-path", default="data/logs/m27_notify_query_events.jsonl")
    p.add_argument("--day", default="2026-02-20")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _seed_rows(*, day: str, inject_fail: bool) -> List[Dict[str, Any]]:
    if inject_fail:
        return [
            {
                "ts": f"{day}T00:00:00+00:00",
                "stage": "ops_batch_notify",
                "event": "result",
                "payload": {
                    "day": day,
                    "provider": "webhook",
                    "route_reason": "default_provider",
                    "escalated": False,
                    "portfolio_guard_alert_total": 0,
                    "ok": True,
                    "sent": True,
                    "skipped": False,
                    "reason": "sent",
                    "status_code": 200,
                },
            }
        ]

    return [
        {
            "ts": f"{day}T00:00:00+00:00",
            "stage": "ops_batch_notify",
            "event": "result",
            "payload": {
                "day": day,
                "provider": "webhook",
                "route_reason": "default_provider",
                "escalated": False,
                "portfolio_guard_alert_total": 0,
                "ok": True,
                "sent": True,
                "skipped": False,
                "reason": "sent",
                "status_code": 200,
            },
        },
        {
            "ts": f"{day}T00:01:00+00:00",
            "stage": "ops_batch_notify",
            "event": "result",
            "payload": {
                "day": day,
                "provider": "slack_webhook",
                "route_reason": "portfolio_guard_escalation",
                "escalated": True,
                "portfolio_guard_alert_total": 2,
                "ok": True,
                "sent": True,
                "skipped": False,
                "reason": "sent",
                "status_code": 200,
            },
        },
    ]


def _run_query(args: List[str]) -> tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = query_main(args + ["--json"])
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    day = str(args.day or "2026-02-20").strip()
    inject_fail = bool(args.inject_fail)

    _write_jsonl(events_path, _seed_rows(day=day, inject_fail=inject_fail))

    rc, obj = _run_query(
        [
            "--event-log-path",
            str(events_path),
            "--day",
            day,
            "--provider",
            "slack_webhook",
            "--only-escalated",
            "--min-portfolio-guard-alert-total",
            "2",
        ]
    )

    route_reason_total = obj.get("route_reason_total") if isinstance(obj.get("route_reason_total"), dict) else {}
    failures: List[str] = []
    if rc != 0:
        failures.append("query_main rc != 0")
    if int(obj.get("total") or 0) < 1:
        failures.append("total < 1")
    if int(obj.get("escalated_total") or 0) < 1:
        failures.append("escalated_total < 1")
    if int(route_reason_total.get("portfolio_guard_escalation") or 0) < 1:
        failures.append("portfolio_guard_escalation route reason missing")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": inject_fail,
        "query_rc": int(rc),
        "query_total": int(obj.get("total") or 0),
        "escalated_total": int(obj.get("escalated_total") or 0),
        "route_reason_total": route_reason_total,
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} inject_fail={out['inject_fail']} query_total={out['query_total']} "
            f"escalated_total={out['escalated_total']} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
