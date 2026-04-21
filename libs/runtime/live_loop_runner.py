from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

from libs.runtime.live_loop_lock import acquire_live_loop_lock, refresh_live_loop_lock, release_live_loop_lock
from libs.runtime.market_hours import MarketHours, now_kst


def run_live_loop(
    state: Dict[str, Any],
    *,
    once: bool,
    sleep_sec: int,
    session_hard_gate: bool,
    lock_path: Path,
    lock_stale_sec: int,
    now_fn: Callable[[], datetime] = now_kst,
    run_once_fn: Callable[..., Dict[str, Any]],
    sleep_fn: Callable[[float], None] = time.sleep,
    market_hours: MarketHours | None = None,
) -> int:
    if state.get("m13_tick_pipeline") == "legacy_m10" and not state.get("symbol"):
        raise SystemExit("symbol is required for legacy_m10: set --symbol or SYMBOL/UNIVERSE_SYMBOLS env")

    if session_hard_gate:
        hours = market_hours if isinstance(market_hours, MarketHours) else MarketHours()
        check_dt = now_fn()
        if not hours.is_open(check_dt):
            print(f"live_loop aborted: market_closed session_hard_gate=true now_kst={check_dt.isoformat()}")
            return 5

    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=max(1, int(lock_stale_sec)))
    if not acquired:
        print(f"live_loop lock not acquired: {reason} lock_path={lock_path}")
        return 4

    try:
        while True:
            refresh_live_loop_lock(lock_path)
            state = run_once_fn(state, dt=now_fn())
            refresh_live_loop_lock(lock_path)

            if once:
                break
            sleep_fn(max(1, int(sleep_sec)))
    finally:
        release_live_loop_lock(lock_path)

    return 0
