from __future__ import annotations

import os
import time
from argparse import ArgumentParser
from datetime import datetime
from typing import Any, Dict, Optional

from libs.core.settings import load_env_file
from libs.runtime.market_hours import now_kst
from graphs.pipelines.m13_live_loop import run_m13_once


def _first_allowlist_symbol() -> str:
    raw = str(os.getenv("SYMBOL_ALLOWLIST", "") or "").strip()
    if not raw:
        return ""
    for part in raw.split(","):
        s = str(part or "").strip()
        if s:
            return s
    return ""


def _build_initial_state(symbol: str) -> Dict[str, Any]:
    # Minimal initial state; nodes/pipelines will enrich it.
    return {"symbol": symbol} if symbol else {}


def main(argv: Optional[list[str]] = None) -> int:
    load_env_file(".env")
    p = ArgumentParser(description="Run M13 live loop (mock-safe).")
    p.add_argument(
        "--symbol",
        default=os.getenv("SYMBOL", "").strip() or _first_allowlist_symbol(),
        help="Primary symbol for live loop; defaults to SYMBOL env or first SYMBOL_ALLOWLIST entry.",
    )
    p.add_argument("--once", action="store_true", help="Run a single iteration and exit.")
    p.add_argument("--sleep-sec", type=int, default=int(os.getenv("SCAN_INTERVAL_SEC", "60")), help="Sleep seconds between iterations.")
    args = p.parse_args(argv)

    state: Dict[str, Any] = _build_initial_state(str(args.symbol or "").strip())
    if not state.get("symbol"):
        raise SystemExit("symbol is required: set --symbol or SYMBOL/SYMBOL_ALLOWLIST env")

    while True:
        dt: datetime = now_kst()
        state = run_m13_once(state, dt=dt)

        if args.once:
            break

        time.sleep(max(1, int(args.sleep_sec)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
