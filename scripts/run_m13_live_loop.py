from __future__ import annotations

import os
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.runtime.entrypoint_common import (
    first_universe_symbol,
    resolve_env_path,
    resolve_path_from_root,
    to_int,
)
from libs.runtime.live_loop_config import build_live_loop_initial_state, session_hard_gate_enabled
from libs.runtime.live_loop_runner import run_live_loop
from graphs.pipelines.m13_live_loop import run_m13_once


def _build_initial_state(symbol: str, *, tick_pipeline: str) -> Dict[str, Any]:
    return build_live_loop_initial_state(symbol, tick_pipeline=tick_pipeline)


def _session_hard_gate_enabled(*, session_hard_gate_flag: bool, allow_offhours_flag: bool) -> bool:
    return session_hard_gate_enabled(
        session_hard_gate_flag=bool(session_hard_gate_flag),
        allow_offhours_flag=bool(allow_offhours_flag),
    )


def main(argv: Optional[list[str]] = None) -> int:
    env_path = resolve_env_path(ROOT, argv)
    load_env_file(str(env_path))
    p = ArgumentParser(description="Run M13 live loop (mock-safe).")
    p.add_argument("--env-path", default=str(env_path), help="Env file path loaded before parsing defaults.")
    p.add_argument(
        "--symbol",
        default=os.getenv("SYMBOL", "").strip() or first_universe_symbol(),
        help="Primary symbol for live loop; defaults to SYMBOL env or first UNIVERSE_SYMBOLS entry.",
    )
    p.add_argument(
        "--tick-pipeline",
        choices=["legacy_m10", "integrated_chain"],
        default="integrated_chain",
        help="Tick runtime path: legacy M10 pipeline or integrated strategist->scanner->monitor chain.",
    )
    p.add_argument("--once", action="store_true", help="Run a single iteration and exit.")
    p.add_argument("--sleep-sec", type=int, default=int(os.getenv("SCAN_INTERVAL_SEC", "60")), help="Sleep seconds between iterations.")
    p.add_argument("--session-hard-gate", action="store_true", help="Abort runtime if market session is closed.")
    p.add_argument("--allow-offhours", action="store_true", help="Disable session hard gate for off-hours drills.")
    p.add_argument(
        "--lock-path",
        default=str(os.getenv("M13_LIVE_LOCK_PATH", "data/state/m13_live_loop.lock") or "data/state/m13_live_loop.lock"),
        help="Single-instance lock file path.",
    )
    p.add_argument(
        "--lock-stale-sec",
        type=int,
        default=to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800),
        help="Stale lock threshold seconds.",
    )
    args = p.parse_args(argv)

    state: Dict[str, Any] = _build_initial_state(
        str(args.symbol or "").strip(),
        tick_pipeline=str(args.tick_pipeline or "legacy_m10"),
    )
    return run_live_loop(
        state,
        once=bool(args.once),
        sleep_sec=int(args.sleep_sec),
        session_hard_gate=_session_hard_gate_enabled(
            session_hard_gate_flag=bool(args.session_hard_gate),
            allow_offhours_flag=bool(args.allow_offhours),
        ),
        lock_path=resolve_path_from_root(ROOT, str(args.lock_path or ""), "data/state/m13_live_loop.lock"),
        lock_stale_sec=max(1, int(args.lock_stale_sec)),
        run_once_fn=run_m13_once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
