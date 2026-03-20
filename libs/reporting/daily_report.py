from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.reporting.llm_artifacts import daily_artifact_paths
from libs.reporting.symbol_trade_report import build_daily_trade_index
from libs.reporting.symbol_trade_report import collect_symbols_for_day
from libs.reporting.symbol_trade_report import generate_symbol_trade_report

@dataclass
class Event:
    ts: int
    run_id: str
    stage: str
    event: str
    payload: Dict[str, Any]


def _to_epoch_utc(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        return int(float(raw))
    except Exception:
        pass
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0

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
                ts=_to_epoch_utc(obj.get("ts")),
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
    out_dir = out_dir.parent if out_dir.name == "daily" else out_dir
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

    paths = daily_artifact_paths(out_dir, day)
    js_path = paths["daily_report_json"]
    md_path = paths["daily_report_md"]
    trade_index = build_daily_trade_index(out_dir, day)
    symbols_for_day = collect_symbols_for_day(events_path, out_dir, day)
    generated_symbol_reports = [
        generate_symbol_trade_report(events_path=events_path, reports_root=out_dir, symbol=symbol)
        for symbol in symbols_for_day
    ]
    data["trade_index"] = trade_index
    data["symbols_observed"] = symbols_for_day
    data["generated_symbol_report_count"] = len(generated_symbol_reports)
    js_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["trade_index_json"].write_text(json.dumps(trade_index, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        f"# Daily Report ({day})",
        "",
        f"- approvals: **{approvals}**",
        f"- denials: **{denials}**",
        f"- runs: **{len(run_ids)}**",
        f"- symbols observed: **{len(symbols_for_day)}**",
        "",
        "## Notes",
        "- This report is generated from `EVENT_LOG_PATH` (JSONL).",
        "- Symbol aggregate reports are generated from events + trade lifecycle truth.",
    ]
    md_text = "\n".join(md) + "\n"
    md_path.write_text(md_text, encoding="utf-8")

    return md_path, js_path
