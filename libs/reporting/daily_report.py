from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

@dataclass
class Event:
    ts: int
    run_id: str
    stage: str
    event: str
    payload: Dict[str, Any]

def _iter_events(path: Path) -> Iterable[Event]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            yield Event(
                ts=int(obj.get("ts") or 0),
                run_id=str(obj.get("run_id") or ""),
                stage=str(obj.get("stage") or ""),
                event=str(obj.get("event") or ""),
                payload=dict(obj.get("payload") or {}),
            )

def _day_to_epoch_range_utc(day: str) -> Tuple[int, int]:
    """Return [start,end) epoch seconds for YYYY-MM-DD in UTC."""
    import datetime as dt
    y, m, d = [int(x) for x in day.split("-")]
    start = dt.datetime(y, m, d, tzinfo=dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())

def generate_daily_report(events_path: Path, out_dir: Path, day: str) -> Tuple[Path, Path]:
    """Generate a minimal EOD report (MD + JSON) from events.jsonl.

    - approvals: count of execute_from_packet verdict events with allowed==True within the UTC day.
    - denials: count of verdict events with allowed==False within the UTC day.
    - runs: number of distinct run_id observed in the day.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    start_ts, end_ts = _day_to_epoch_range_utc(day)

    approvals = 0
    denials = 0
    run_ids = set()
    rows: List[Dict[str, Any]] = []

    for ev in _iter_events(events_path):
        if ev.ts < start_ts or ev.ts >= end_ts:
            continue
        if ev.run_id:
            run_ids.add(ev.run_id)

        if ev.stage == "execute_from_packet" and ev.event == "verdict":
            allowed = bool((ev.payload or {}).get("allowed", False))
            if allowed:
                approvals += 1
            else:
                denials += 1

        rows.append({
            "ts": ev.ts,
            "run_id": ev.run_id,
            "stage": ev.stage,
            "event": ev.event,
            "payload": ev.payload,
        })

    data = {
        "day": day,
        "approvals": approvals,
        "denials": denials,
        "runs": len(run_ids),
        "events": rows,
    }

    js_path = out_dir / f"daily_report_{day}.json"
    md_path = out_dir / f"daily_report_{day}.md"
    js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        f"# Daily Report ({day})",
        "",
        f"- approvals: **{approvals}**",
        f"- denials: **{denials}**",
        f"- runs: **{len(run_ids)}**",
        "",
        "## Notes",
        "- This report is generated from `EVENT_LOG_PATH` (JSONL).",
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    return md_path, js_path
