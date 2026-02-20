from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def _numeric_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(float(v) for v in values if float(v) >= 0.0)
    if not vals:
        return {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    n = len(vals)

    def pct(p: float) -> float:
        if n == 1:
            return vals[0]
        idx = int(round((n - 1) * p))
        idx = max(0, min(n - 1, idx))
        return vals[idx]

    return {
        "count": float(n),
        "avg": float(sum(vals) / n),
        "p50": float(pct(0.50)),
        "p95": float(pct(0.95)),
        "max": float(vals[-1]),
    }


def _incident_trigger(row: Dict[str, Any]) -> Tuple[bool, str]:
    stage = str(row.get("stage") or "")
    event = str(row.get("event") or "")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

    if stage == "commander_router" and event == "error":
        reason = str(payload.get("error_type") or payload.get("error") or "commander_error")
        return True, f"commander_router:error:{reason}"

    if stage == "commander_router" and event == "transition":
        transition = str(payload.get("transition") or "").strip().lower()
        if transition == "cooldown":
            reason = str(payload.get("reason") or "cooldown_transition")
            return True, f"commander_router:transition:{reason}"

    if stage == "commander_router" and event == "resilience":
        reason = str(payload.get("reason") or "").strip().lower()
        if reason in ("cooldown_active", "incident_threshold_cooldown"):
            return True, f"commander_router:resilience:{reason}"

    if stage == "execute_from_packet" and event == "error":
        reason = str(payload.get("error") or "execute_error")
        return True, f"execute_from_packet:error:{reason}"

    return False, ""


def _is_recovery(row: Dict[str, Any]) -> Tuple[bool, str]:
    stage = str(row.get("stage") or "")
    event = str(row.get("event") or "")
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

    if stage == "commander_router" and event == "intervention":
        return True, "commander_router:intervention"
    if stage == "commander_router" and event == "end":
        status = str(payload.get("status") or "").strip().lower()
        if status in ("ok", "resuming", "normal"):
            return True, f"commander_router:end:{status or 'ok'}"
    if stage == "commander_router" and event == "resilience":
        reason = str(payload.get("reason") or "").strip().lower()
        if reason in ("cooldown_not_active", "resume_applied", "operator_resumed"):
            return True, f"commander_router:resilience:{reason}"
    if stage == "execute_from_packet" and event == "end":
        return True, "execute_from_packet:end"
    return False, ""


def _event_reason(row: Dict[str, Any]) -> str:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    for key in ("reason", "error_type", "error", "status"):
        v = payload.get(key)
        if v:
            return str(v)
    return ""


def _build_markdown(out: Dict[str, Any]) -> str:
    lines = [
        f"# Incident Timeline Reconstruction ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- events: **{int(out.get('events') or 0)}**",
        f"- runs: **{int(out.get('runs') or 0)}**",
        f"- incident_total: **{int(out.get('incident_total') or 0)}**",
        f"- recovered_incident_total: **{int(out.get('recovered_incident_total') or 0)}**",
        f"- unresolved_incident_total: **{int(out.get('unresolved_incident_total') or 0)}**",
        "",
        "## Trigger Totals",
        "",
    ]
    trigger_total = out.get("trigger_total") if isinstance(out.get("trigger_total"), dict) else {}
    if trigger_total:
        for k, v in sorted(trigger_total.items()):
            lines.append(f"- {k}: {int(v)}")
    else:
        lines.append("- (none)")

    lines += ["", "## Recovery Totals", ""]
    recovery_total = out.get("recovery_total") if isinstance(out.get("recovery_total"), dict) else {}
    if recovery_total:
        for k, v in sorted(recovery_total.items()):
            lines.append(f"- {k}: {int(v)}")
    else:
        lines.append("- (none)")

    ttr = out.get("ttr_sec") if isinstance(out.get("ttr_sec"), dict) else {}
    lines += [
        "",
        "## Time To Recovery (sec)",
        "",
        f"- count: {int(float(ttr.get('count') or 0.0))}",
        f"- avg: {float(ttr.get('avg') or 0.0):.3f}",
        f"- p50: {float(ttr.get('p50') or 0.0):.3f}",
        f"- p95: {float(ttr.get('p95') or 0.0):.3f}",
        f"- max: {float(ttr.get('max') or 0.0):.3f}",
        "",
        "## Failures",
        "",
    ]
    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reconstruct incident timelines from JSONL event logs.")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/incident_timeline")
    p.add_argument("--day", default=None)
    p.add_argument("--run-id", default="")
    p.add_argument("--window-before-sec", type=int, default=120)
    p.add_argument("--window-after-sec", type=int, default=900)
    p.add_argument("--require-incidents", action="store_true")
    p.add_argument("--require-recovered", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    all_rows = _iter_rows(events_path)
    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(all_rows):
        ts = row.get("ts") or ((row.get("payload") or {}).get("ts") if isinstance(row.get("payload"), dict) else None)
        epoch = _to_epoch(ts)
        rows.append({**row, "_idx": i, "_epoch": epoch, "_day": _utc_day(ts)})

    day = str(args.day or "").strip()
    if not day:
        days = sorted({str(r.get("_day") or "") for r in rows if str(r.get("_day") or "").strip()})
        day = days[-1] if days else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    day_rows = [r for r in rows if str(r.get("_day") or "") == day]
    run_id_filter = str(args.run_id or "").strip()
    if run_id_filter:
        day_rows = [r for r in day_rows if str(r.get("run_id") or "") == run_id_filter]

    sorted_rows = sorted(day_rows, key=lambda r: (int(r.get("_epoch") or 0), int(r.get("_idx") or 0)))
    runs = {str(r.get("run_id") or "") for r in sorted_rows if str(r.get("run_id") or "").strip()}

    incident_rows: List[Tuple[Dict[str, Any], str]] = []
    trigger_total: Dict[str, int] = {}
    for row in sorted_rows:
        ok, trigger = _incident_trigger(row)
        if not ok:
            continue
        incident_rows.append((row, trigger))
        trigger_total[trigger] = int(trigger_total.get(trigger) or 0) + 1

    before_sec = max(0, int(args.window_before_sec or 0))
    after_sec = max(1, int(args.window_after_sec or 1))
    incidents: List[Dict[str, Any]] = []
    recovery_total: Dict[str, int] = {}
    ttr_values: List[float] = []

    for idx, (trigger_row, trigger_key) in enumerate(incident_rows, start=1):
        run_id = str(trigger_row.get("run_id") or "").strip()
        trigger_epoch = int(trigger_row.get("_epoch") or 0)
        start_epoch = trigger_epoch - before_sec
        end_epoch = trigger_epoch + after_sec

        window_rows: List[Dict[str, Any]] = []
        for row in sorted_rows:
            epoch = int(row.get("_epoch") or 0)
            if epoch < start_epoch or epoch > end_epoch:
                continue
            if run_id and str(row.get("run_id") or "").strip() != run_id:
                continue
            window_rows.append(row)

        recovery_epoch: Optional[int] = None
        recovery_type = ""
        for row in window_rows:
            epoch = int(row.get("_epoch") or 0)
            if epoch < trigger_epoch:
                continue
            is_recovery, typ = _is_recovery(row)
            if not is_recovery:
                continue
            recovery_epoch = epoch
            recovery_type = typ
            break

        recovered = recovery_epoch is not None
        ttr_sec: Optional[float] = None
        if recovery_epoch is not None:
            ttr_sec = float(recovery_epoch - trigger_epoch)
            ttr_values.append(float(ttr_sec))
            recovery_total[recovery_type] = int(recovery_total.get(recovery_type) or 0) + 1

        stage_event_total: Dict[str, int] = {}
        event_slice: List[Dict[str, Any]] = []
        for row in window_rows[:80]:
            key = f"{str(row.get('stage') or '')}:{str(row.get('event') or '')}"
            stage_event_total[key] = int(stage_event_total.get(key) or 0) + 1
            event_slice.append(
                {
                    "ts": row.get("ts"),
                    "run_id": row.get("run_id"),
                    "stage": row.get("stage"),
                    "event": row.get("event"),
                    "reason": _event_reason(row),
                }
            )

        incidents.append(
            {
                "incident_id": f"INC-{day.replace('-', '')}-{idx:03d}",
                "run_id": run_id,
                "trigger_ts": trigger_row.get("ts"),
                "trigger_stage": trigger_row.get("stage"),
                "trigger_event": trigger_row.get("event"),
                "trigger_type": trigger_key,
                "trigger_reason": _event_reason(trigger_row),
                "window_start_epoch": int(start_epoch),
                "window_end_epoch": int(end_epoch),
                "event_total_in_window": int(len(window_rows)),
                "stage_event_total_in_window": stage_event_total,
                "recovered": bool(recovered),
                "recovery_type": recovery_type,
                "recovery_ts": (
                    datetime.fromtimestamp(recovery_epoch, tz=timezone.utc).replace(microsecond=0).isoformat()
                    if recovery_epoch is not None
                    else ""
                ),
                "time_to_recovery_sec": ttr_sec,
                "events": event_slice,
            }
        )

    incident_total = int(len(incidents))
    recovered_incident_total = int(sum(1 for x in incidents if bool(x.get("recovered"))))
    unresolved_incident_total = int(incident_total - recovered_incident_total)

    failures: List[str] = []
    if bool(args.require_incidents) and incident_total < 1:
        failures.append("incident_total < 1")
    if bool(args.require_recovered) and unresolved_incident_total > 0:
        failures.append("unresolved_incident_total > 0")

    out: Dict[str, Any] = {
        "ok": len(failures) == 0,
        "day": day,
        "event_log_path": str(events_path),
        "events": int(len(sorted_rows)),
        "runs": int(len(runs)),
        "incident_total": incident_total,
        "recovered_incident_total": recovered_incident_total,
        "unresolved_incident_total": unresolved_incident_total,
        "trigger_total": trigger_total,
        "recovery_total": recovery_total,
        "ttr_sec": _numeric_summary(ttr_values),
        "incidents": incidents,
        "failures": failures,
    }

    js_path = report_dir / f"incident_timeline_{day}.json"
    md_path = report_dir / f"incident_timeline_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} incident_total={incident_total} "
            f"recovered_incident_total={recovered_incident_total} unresolved_incident_total={unresolved_incident_total}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
