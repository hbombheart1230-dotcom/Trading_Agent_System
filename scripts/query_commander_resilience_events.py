from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except Exception:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _is_incident_event(rec: Dict[str, Any]) -> bool:
    event = str(rec.get("event") or "")
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    if event == "error":
        return True
    if event == "transition" and str(payload.get("transition") or "") == "cooldown":
        return True
    if event == "resilience":
        reason = str(payload.get("reason") or "")
        if reason in ("cooldown_active", "incident_threshold_cooldown"):
            return True
    return False


def _filtered_events(
    rows: List[Dict[str, Any]],
    *,
    run_id: str = "",
    only_incidents: bool = False,
    include_route: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in rows:
        if rec.get("stage") != "commander_router":
            continue
        event = str(rec.get("event") or "")
        if event == "route" and not include_route:
            continue
        if run_id and str(rec.get("run_id") or "") != run_id:
            continue
        if only_incidents and not _is_incident_event(rec):
            continue
        out.append(rec)
    return out


def _summary(rows: List[Dict[str, Any]], *, total_matched: int) -> Dict[str, Any]:
    event_total: Dict[str, int] = {}
    cooldown_transitions = 0
    intervention_total = 0
    error_total = 0
    latest_status = ""
    latest_run_id = ""

    for rec in rows:
        event = str(rec.get("event") or "")
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        event_total[event] = int(event_total.get(event, 0)) + 1

        if event == "transition" and str(payload.get("transition") or "") == "cooldown":
            cooldown_transitions += 1
        if event == "intervention":
            intervention_total += 1
        if event == "error":
            error_total += 1

        status = str(payload.get("status") or "")
        if status:
            latest_status = status
        latest_run_id = str(rec.get("run_id") or latest_run_id)

    return {
        "total_matched": int(total_matched),
        "shown": int(len(rows)),
        "event_total": event_total,
        "cooldown_transition_total": int(cooldown_transitions),
        "intervention_total": int(intervention_total),
        "error_total": int(error_total),
        "latest_status": latest_status,
        "latest_run_id": latest_run_id,
    }


def _print_human(path: Path, rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    print("=== Commander Resilience Events ===")
    print(f"path={path}")
    print(f"total_matched={summary.get('total_matched')} shown={summary.get('shown')}")
    print(
        f"cooldown_transition_total={summary.get('cooldown_transition_total')} "
        f"intervention_total={summary.get('intervention_total')} "
        f"error_total={summary.get('error_total')}"
    )
    print(f"latest_run_id={summary.get('latest_run_id')} latest_status={summary.get('latest_status')}")
    for rec in rows:
        ts = str(rec.get("ts") or "")
        run_id = str(rec.get("run_id") or "")
        event = str(rec.get("event") or "")
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        key = ""
        if event == "transition":
            key = (
                f"transition={payload.get('transition')} status={payload.get('status')} "
                f"reason={payload.get('reason')} cooldown_until_epoch={payload.get('cooldown_until_epoch')}"
            )
        elif event == "resilience":
            key = (
                f"reason={payload.get('reason')} incident_count={payload.get('incident_count')} "
                f"incident_threshold={payload.get('incident_threshold')} "
                f"cooldown_until_epoch={payload.get('cooldown_until_epoch')}"
            )
        elif event == "intervention":
            key = f"type={payload.get('type')} at_epoch={payload.get('at_epoch')}"
        elif event == "error":
            key = f"error_type={payload.get('error_type')} error={payload.get('error')}"
        elif event == "end":
            key = f"status={payload.get('status')} path={payload.get('path')}"
        elif event == "route":
            key = f"mode={payload.get('mode')}"
        print(f"{ts} run_id={run_id} event={event} {key}".strip())


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Query commander_router resilience events from EVENT_LOG_PATH JSONL.")
    p.add_argument("--path", default=os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    p.add_argument("--run-id", default="", help="Filter by exact run_id.")
    p.add_argument("--limit", type=int, default=20, help="Show last N matched rows.")
    p.add_argument("--only-incidents", action="store_true", help="Only include cooldown/error incident events.")
    p.add_argument("--include-route", action="store_true", help="Include route events (excluded by default).")
    p.add_argument("--json", action="store_true", help="Print JSON object instead of human-readable lines.")
    args = p.parse_args(argv)

    path = Path(str(args.path).strip())
    if not path.exists():
        print(f"ERROR: event log path does not exist: {path}", file=sys.stderr)
        return 2

    rows = _load_jsonl(path)
    matched = _filtered_events(
        rows,
        run_id=str(args.run_id or "").strip(),
        only_incidents=bool(args.only_incidents),
        include_route=bool(args.include_route),
    )
    limit = max(1, int(args.limit))
    shown = matched[-limit:]
    summary = _summary(shown, total_matched=len(matched))

    if args.json:
        print(json.dumps({"summary": summary, "rows": shown}, ensure_ascii=False))
    else:
        _print_human(path, shown, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
