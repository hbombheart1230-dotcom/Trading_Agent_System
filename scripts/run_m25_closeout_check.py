from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from scripts.check_alert_policy_v1 import main as alert_policy_main
from scripts.check_metrics_schema_v1 import main as metrics_schema_main
from scripts.generate_daily_report import generate_daily_report


def _env_fail_on(default: str = "critical") -> str:
    raw = str(os.getenv("ALERT_POLICY_FAIL_ON", "") or "").strip().lower()
    if raw in ("none", "warning", "critical"):
        return raw
    return str(default)


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed_rows(day: str, *, inject_critical_case: bool) -> List[Dict[str, Any]]:
    base_ts = f"{day}T00:00:"
    rows: List[Dict[str, Any]] = [
        {
            "ts": f"{base_ts}00+00:00",
            "run_id": "m25-closeout-r1",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY"}}},
        },
        {
            "ts": f"{base_ts}01+00:00",
            "run_id": "m25-closeout-r1",
            "stage": "execute_from_packet",
            "event": "verdict",
            "payload": {"allowed": True, "reason": "Allowed"},
        },
        {
            "ts": f"{base_ts}02+00:00",
            "run_id": "m25-closeout-r1",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"ok": True},
        },
        {
            "ts": f"{base_ts}03+00:00",
            "run_id": "m25-closeout-r2",
            "stage": "strategist_llm",
            "event": "result",
            "payload": {"ok": True, "latency_ms": 120, "attempts": 1, "circuit_state": "closed"},
        },
        {
            "ts": f"{base_ts}04+00:00",
            "run_id": "m25-closeout-r3",
            "stage": "execute_from_packet",
            "event": "error",
            "payload": {"api_id": "ORDER_SUBMIT", "status_code": 500, "error": "upstream transient"},
        },
    ]
    if inject_critical_case:
        rows.append(
            {
                "ts": f"{base_ts}05+00:00",
                "run_id": "m25-closeout-r4",
                "stage": "strategist_llm",
                "event": "result",
                "payload": {"ok": False, "error_type": "TimeoutError", "circuit_state": "open"},
            }
        )
    return rows


def _run_metrics_schema_json(
    *,
    events_path: Path,
    report_dir: Path,
    day: str,
) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = metrics_schema_main(
            [
                "--event-log-path",
                str(events_path),
                "--report-dir",
                str(report_dir),
                "--day",
                day,
                "--json",
            ]
        )
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _run_alert_policy_json(
    *,
    events_path: Path,
    report_dir: Path,
    day: str,
    fail_on: str,
) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = alert_policy_main(
            [
                "--event-log-path",
                str(events_path),
                "--report-dir",
                str(report_dir),
                "--day",
                day,
                "--fail-on",
                fail_on,
                "--json",
            ]
        )
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _write_alert_artifacts(*, report_dir: Path, day: str, alert_obj: Dict[str, Any]) -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    js_path = report_dir / f"alert_policy_{day}.json"
    md_path = report_dir / f"alert_policy_{day}.md"
    js_path.write_text(json.dumps(alert_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    sev = alert_obj.get("severity_total") if isinstance(alert_obj.get("severity_total"), dict) else {}
    alerts = alert_obj.get("alerts") if isinstance(alert_obj.get("alerts"), list) else []
    md_lines = [
        f"# Alert Policy Report ({day})",
        "",
        f"- ok: **{alert_obj.get('ok')}**",
        f"- fail_on: **{alert_obj.get('fail_on')}**",
        f"- alert_total: **{alert_obj.get('alert_total')}**",
        f"- warning_total: **{sev.get('warning', 0)}**",
        f"- critical_total: **{sev.get('critical', 0)}**",
        "",
        "## Alerts",
        "",
    ]
    if alerts:
        for a in alerts:
            md_lines.append(
                f"- [{a.get('severity')}] {a.get('code')} value={a.get('value')} threshold={a.get('threshold')}"
            )
    else:
        md_lines.append("- (none)")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return md_path, js_path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M25 closeout check (metrics schema freeze + alert policy + daily report).")
    p.add_argument("--event-log-path", default="data/logs/m25_closeout_events.jsonl")
    p.add_argument("--report-dir", default="reports/m25_closeout")
    p.add_argument("--day", default=None)
    p.add_argument("--fail-on", choices=["none", "warning", "critical"], default=_env_fail_on("critical"))
    p.add_argument("--inject-critical-case", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    # Load default .env profile for alert policy defaults.
    load_env_file(".env")
    args = _build_parser().parse_args(argv)
    day = str(args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    events_path = Path(args.event_log_path)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    if (not args.no_clear) and events_path.exists():
        events_path.unlink()

    _write_jsonl(events_path, _seed_rows(day, inject_critical_case=bool(args.inject_critical_case)))

    schema_rc, schema_obj = _run_metrics_schema_json(
        events_path=events_path,
        report_dir=report_dir,
        day=day,
    )
    alert_rc, alert_obj = _run_alert_policy_json(
        events_path=events_path,
        report_dir=report_dir,
        day=day,
        fail_on=str(args.fail_on),
    )
    daily_md, daily_js = generate_daily_report(events_path, report_dir, day=day)
    alert_md, alert_js = _write_alert_artifacts(report_dir=report_dir, day=day, alert_obj=alert_obj)

    daily_obj: Dict[str, Any] = {}
    try:
        daily_obj = json.loads(daily_js.read_text(encoding="utf-8"))
    except Exception:
        daily_obj = {}

    ok = True
    failures: List[str] = []
    if schema_rc != 0:
        ok = False
        failures.append("metrics_schema rc != 0")
    if schema_obj and not bool(schema_obj.get("ok")):
        ok = False
        failures.append("metrics_schema ok != true")
    if alert_rc != 0:
        ok = False
        failures.append("alert_policy rc != 0")
    if alert_obj and not bool(alert_obj.get("ok")):
        ok = False
        failures.append("alert_policy ok != true")
    if int(daily_obj.get("events") or 0) < 1:
        ok = False
        failures.append("daily_report.events < 1")

    out = {
        "ok": bool(ok),
        "day": day,
        "events_path": str(events_path),
        "report_dir": str(report_dir),
        "metrics_schema": {
            "rc": int(schema_rc),
            "ok": bool(schema_obj.get("ok")) if isinstance(schema_obj, dict) else False,
            "failure_total": int(schema_obj.get("failure_total") or 0) if isinstance(schema_obj, dict) else 0,
        },
        "alert_policy": {
            "rc": int(alert_rc),
            "ok": bool(alert_obj.get("ok")) if isinstance(alert_obj, dict) else False,
            "alert_total": int(alert_obj.get("alert_total") or 0) if isinstance(alert_obj, dict) else 0,
            "severity_total": alert_obj.get("severity_total") if isinstance(alert_obj, dict) else {},
        },
        "daily_report": {
            "path_md": str(daily_md),
            "path_json": str(daily_js),
            "events": int(daily_obj.get("events") or 0),
        },
        "alert_report": {
            "path_md": str(alert_md),
            "path_json": str(alert_js),
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} schema_rc={schema_rc} alert_rc={alert_rc} "
            f"daily_events={out['daily_report']['events']} alert_total={out['alert_policy']['alert_total']}"
        )
        if failures:
            for msg in failures:
                print(msg)

    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
