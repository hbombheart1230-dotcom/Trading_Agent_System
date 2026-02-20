from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    def gen():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    return gen()

def _day_key(ts: Any) -> str:
    """Return YYYY-MM-DD in **UTC** for determinism across machines/timezones."""
    if ts is None:
        return date.today().isoformat()

    s = str(ts).strip()
    if not s:
        return date.today().isoformat()

    try:
        epoch = int(float(s))
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return date.today().isoformat()

def generate_daily_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    """Generate a daily markdown + json summary from events.jsonl.

    Notes:
      - Day bucketing uses UTC for deterministic tests and consistent reporting.
      - If `day` is provided, only events matching that UTC day are included.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for e in _iter_events(events_path):
        ts = e.get("ts") or e.get("payload", {}).get("ts")
        rows.append({**e, "_day": _day_key(ts)})
    if not rows:
        day = day or date.today().isoformat()
        md_path = out_dir / f"daily_{day}.md"
        js_path = out_dir / f"daily_{day}.json"
        md_path.write_text(f"# Daily Report ({day})\n\nNo events found.\n", encoding="utf-8")
        js_path.write_text(json.dumps({"day": day, "events": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path, js_path

    day = day or sorted({r["_day"] for r in rows})[-1]
    day_rows = [r for r in rows if r["_day"] == day]

    stage_counter = Counter(r.get("stage") for r in day_rows)
    event_counter = Counter((r.get("stage"), r.get("event")) for r in day_rows)

    verdicts = []
    for r in day_rows:
        if r.get("stage") == "execute_from_packet" and r.get("event") in ("verdict", "end", "result"):
            payload = r.get("payload") or {}
            v = payload.get("allowed")
            if isinstance(v, bool):
                verdicts.append(v)
    approvals = sum(1 for v in verdicts if v)
    blocks = sum(1 for v in verdicts if v is False)

    actions = Counter()
    for r in day_rows:
        if r.get("stage") == "decision" and r.get("event") == "trace":
            payload = r.get("payload") or {}
            pkt = payload.get("decision_packet") or {}
            intent = pkt.get("intent") or {}
            act = intent.get("action") or intent.get("intent") or "UNKNOWN"
            actions[str(act).upper()] += 1

    summary = {
        "day": day,
        "events": len(day_rows),
        "stage_counts": dict(stage_counter),
        "event_counts": {f"{k[0]}::{k[1]}": v for k, v in event_counter.items()},
        "decision_actions": dict(actions),
        "approvals": approvals,
        "blocks": blocks,
    }

    md_lines = [
        f"# Daily Report ({day})",
        "",
        f"- events: **{summary['events']}**",
        f"- approvals: **{approvals}** / blocks: **{blocks}**",
        "",
        "## Decision actions",
        "",
    ]
    if actions:
        for k, v in actions.most_common():
            md_lines.append(f"- {k}: {v}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "## Stage counts", ""]
    for k, v in stage_counter.most_common():
        md_lines.append(f"- {k}: {v}")

    md_path = out_dir / f"daily_{day}.md"
    js_path = out_dir / f"daily_{day}.json"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    js_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path

def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports")) / "daily"
    day = os.getenv("REPORT_DAY")  # optional YYYY-MM-DD (UTC)
    md, js = generate_daily_report(events_path, out_dir, day=day)
    print(f"Wrote: {md}")
    print(f"Wrote: {js}")

if __name__ == "__main__":
    main()
