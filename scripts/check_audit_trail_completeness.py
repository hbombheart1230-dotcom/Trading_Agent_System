from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _extract_ts(row: Dict[str, Any]) -> Any:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return row.get("ts") or payload.get("ts")


def _iter_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _extract_decision_action(row: Dict[str, Any]) -> str:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
    intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
    action = intent.get("action") or payload.get("action") or payload.get("intent")
    return str(action or "").strip().upper()


def _extract_allowed(row: Dict[str, Any]) -> Optional[bool]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    v = payload.get("allowed")
    if isinstance(v, bool):
        return v
    return None


def _latest_day(rows: List[Dict[str, Any]]) -> str:
    days = sorted({str(r.get("_day") or "") for r in rows if str(r.get("_day") or "").strip()})
    if days:
        return str(days[-1])
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def analyze_day_rows(day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_run: Dict[str, List[Dict[str, Any]]] = {}
    stage_event_total: Dict[str, int] = {
        "start": 0,
        "verdict": 0,
        "execution": 0,
        "degrade_policy_block": 0,
        "end": 0,
        "error": 0,
    }

    for row in day_rows:
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            by_run.setdefault(run_id, []).append(row)

        stage = str(row.get("stage") or "")
        event = str(row.get("event") or "")
        if stage == "execute_from_packet" and event in stage_event_total:
            stage_event_total[event] = int(stage_event_total.get(event) or 0) + 1

    actionable_run_total = 0
    execution_run_total = 0
    linked_complete_run_total = 0

    missing_start: List[str] = []
    missing_resolution: List[str] = []
    missing_execution_payload: List[str] = []
    missing_terminal: List[str] = []
    orphan_execution: List[str] = []

    for run_id, rows in by_run.items():
        has_actionable = False
        has_exec_activity = False
        has_start = False
        has_verdict = False
        has_degrade_block = False
        has_execution = False
        has_end = False
        has_error = False
        has_allowed_true = False

        for row in rows:
            stage = str(row.get("stage") or "")
            event = str(row.get("event") or "")

            if stage == "decision" and event == "trace":
                action = _extract_decision_action(row)
                if action in ("BUY", "SELL"):
                    has_actionable = True

            if stage == "execute_from_packet":
                has_exec_activity = True
                if event == "start":
                    has_start = True
                elif event == "verdict":
                    has_verdict = True
                    if _extract_allowed(row) is True:
                        has_allowed_true = True
                elif event == "degrade_policy_block":
                    has_degrade_block = True
                elif event == "execution":
                    has_execution = True
                elif event == "end":
                    has_end = True
                elif event == "error":
                    has_error = True

        if has_exec_activity:
            execution_run_total += 1
        if has_exec_activity and not has_actionable:
            orphan_execution.append(run_id)

        if not has_actionable:
            continue

        actionable_run_total += 1

        has_resolution = has_verdict or has_degrade_block or has_error
        has_terminal = has_end or has_error

        if not has_start:
            missing_start.append(run_id)
        if not has_resolution:
            missing_resolution.append(run_id)
        if has_allowed_true and not has_execution:
            missing_execution_payload.append(run_id)
        if not has_terminal:
            missing_terminal.append(run_id)

        if has_start and has_resolution and (not has_allowed_true or has_execution) and has_terminal:
            linked_complete_run_total += 1

    link_success_rate = (
        float(linked_complete_run_total) / float(actionable_run_total)
        if actionable_run_total > 0
        else 1.0
    )

    return {
        "run_total": int(len(by_run)),
        "actionable_decision_run_total": int(actionable_run_total),
        "execution_run_total": int(execution_run_total),
        "linked_complete_run_total": int(linked_complete_run_total),
        "link_success_rate": float(link_success_rate),
        "missing_execution_start_total": int(len(missing_start)),
        "missing_execution_resolution_total": int(len(missing_resolution)),
        "missing_execution_payload_total": int(len(missing_execution_payload)),
        "missing_terminal_event_total": int(len(missing_terminal)),
        "orphan_execution_run_total": int(len(orphan_execution)),
        "stage_event_total": stage_event_total,
        "anomaly_examples": {
            "missing_execution_start": missing_start[:10],
            "missing_execution_resolution": missing_resolution[:10],
            "missing_execution_payload": missing_execution_payload[:10],
            "missing_terminal_event": missing_terminal[:10],
            "orphan_execution": orphan_execution[:10],
        },
    }


def _build_markdown(*, day: str, out: Dict[str, Any]) -> str:
    anomalies = out.get("anomaly_examples") if isinstance(out.get("anomaly_examples"), dict) else {}
    stage_event_total = out.get("stage_event_total") if isinstance(out.get("stage_event_total"), dict) else {}
    lines = [
        f"# Audit Trail Completeness ({day})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- events: **{int(out.get('events') or 0)}**",
        f"- runs: **{int(out.get('run_total') or 0)}**",
        f"- actionable_decision_run_total: **{int(out.get('actionable_decision_run_total') or 0)}**",
        f"- linked_complete_run_total: **{int(out.get('linked_complete_run_total') or 0)}**",
        f"- link_success_rate: **{float(out.get('link_success_rate') or 0.0):.2%}**",
        "",
        "## Anomaly Totals",
        "",
        f"- missing_execution_start_total: {int(out.get('missing_execution_start_total') or 0)}",
        f"- missing_execution_resolution_total: {int(out.get('missing_execution_resolution_total') or 0)}",
        f"- missing_execution_payload_total: {int(out.get('missing_execution_payload_total') or 0)}",
        f"- missing_terminal_event_total: {int(out.get('missing_terminal_event_total') or 0)}",
        f"- orphan_execution_run_total: {int(out.get('orphan_execution_run_total') or 0)}",
        "",
        "## execute_from_packet stage_event_total",
        "",
    ]

    for k in ("start", "verdict", "execution", "degrade_policy_block", "end", "error"):
        lines.append(f"- {k}: {int(stage_event_total.get(k) or 0)}")

    lines += ["", "## Anomaly Examples", ""]
    for key in (
        "missing_execution_start",
        "missing_execution_resolution",
        "missing_execution_payload",
        "missing_terminal_event",
        "orphan_execution",
    ):
        vals = anomalies.get(key) if isinstance(anomalies.get(key), list) else []
        if vals:
            lines.append(f"- {key}: {', '.join(str(x) for x in vals)}")
        else:
            lines.append(f"- {key}: (none)")

    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    lines += ["", "## Failures", ""]
    if failures:
        for x in failures:
            lines.append(f"- {x}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check intent->decision->execution audit trail completeness.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/audit")
    p.add_argument("--day", default=None)
    p.add_argument("--require-actionable", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    rows = _iter_rows(events_path)
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        ts = _extract_ts(row)
        prepared.append({**row, "_day": _utc_day(ts)})

    day = str(args.day or "").strip()
    if not day:
        day = _latest_day(prepared)

    day_rows = [r for r in prepared if str(r.get("_day") or "") == day]
    analysis = analyze_day_rows(day_rows)

    failures: List[str] = []
    if int(analysis.get("missing_execution_start_total") or 0) > 0:
        failures.append("missing_execution_start_total > 0")
    if int(analysis.get("missing_execution_resolution_total") or 0) > 0:
        failures.append("missing_execution_resolution_total > 0")
    if int(analysis.get("missing_execution_payload_total") or 0) > 0:
        failures.append("missing_execution_payload_total > 0")
    if int(analysis.get("missing_terminal_event_total") or 0) > 0:
        failures.append("missing_terminal_event_total > 0")
    if int(analysis.get("orphan_execution_run_total") or 0) > 0:
        failures.append("orphan_execution_run_total > 0")
    if bool(args.require_actionable) and int(analysis.get("actionable_decision_run_total") or 0) < 1:
        failures.append("actionable_decision_run_total < 1")

    out: Dict[str, Any] = {
        "ok": len(failures) == 0,
        "day": day,
        "event_log_path": str(events_path),
        "events": int(len(day_rows)),
        **analysis,
        "failures": failures,
    }

    js_path = report_dir / f"audit_trail_{day}.json"
    md_path = report_dir / f"audit_trail_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)

    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(day=day, out=out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} actionable={out['actionable_decision_run_total']} "
            f"linked={out['linked_complete_run_total']} missing={len(failures)}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
