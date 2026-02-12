from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from libs.runtime.market_hours import MarketHours, now_kst
from libs.runtime.dates import kst_day_str, to_kst

GenerateFn = Callable[[Path, Path, str], Tuple[Path, Path]]

def run_m13_eod_report(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    market_hours: Optional[MarketHours] = None,
    generate: Optional[GenerateFn] = None,
    grace_minutes: int = 5,
) -> Dict[str, Any]:
    """M13-2: end-of-day daily report trigger (test-first).

    Behavior:
      - Only runs on weekdays.
      - Only runs after market close + grace_minutes (KST).
      - Runs at most once per KST day (tracked via state['last_daily_report_day']).

    Uses env by default:
      - EVENT_LOG_PATH (default ./data/events.jsonl)
      - REPORT_DIR (default ./reports)

    Output:
      - state['daily_report'] = {'day': ..., 'md': '...', 'js': '...'}
    """
    mh = market_hours or MarketHours()
    ts = to_kst(dt or now_kst())
    day = kst_day_str(ts)

    state["eod_ts"] = int(ts.timestamp())
    state["eod_day"] = day

    if state.get("last_daily_report_day") == day:
        state["eod_skipped"] = True
        state["eod_skip_reason"] = "already_generated"
        return state

    if ts.weekday() >= 5:
        state["eod_skipped"] = True
        state["eod_skip_reason"] = "weekend"
        return state

    close_dt = ts.replace(hour=mh.close_time.hour, minute=mh.close_time.minute, second=0, microsecond=0)
    if ts < (close_dt + timedelta(minutes=grace_minutes)):
        state["eod_skipped"] = True
        state["eod_skip_reason"] = "before_close"
        return state

    if generate is None:
        from libs.reporting.daily_report import generate_daily_report as generate  # lazy import

    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/events.jsonl"))
    report_dir = Path(os.getenv("REPORT_DIR", "./reports"))

    md, js = generate(events_path, report_dir, day=day)  # type: ignore[misc]
    state["daily_report"] = {"day": day, "md": str(md), "js": str(js)}
    state["last_daily_report_day"] = day
    state["eod_skipped"] = False
    return state
