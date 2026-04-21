from __future__ import annotations

import json
import os
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.pipelines.offhours_validation import run_offhours_validation_once
from libs.core.settings import load_env_file
from libs.runtime.entrypoint_common import first_universe_symbol, resolve_path_from_root, to_int
from libs.runtime.live_loop_lock import acquire_live_loop_lock, release_live_loop_lock
from libs.runtime.offhours_validation_runtime import (
    apply_runtime_paths,
    build_initial_state,
    enforce_safe_runtime,
    iteration_summary,
    normalize_symbol,
)


def main(argv: Optional[list[str]] = None) -> int:
    p = ArgumentParser(description="Run off-hours validation loop with local mock fills.")
    p.add_argument("--env-path", default=str(ROOT / ".env"))
    p.add_argument("--state-path", default=str(os.getenv("STATE_STORE_PATH", "")).strip())
    p.add_argument("--event-log-path", default=str(os.getenv("EVENT_LOG_PATH", "")).strip())
    p.add_argument("--symbol", default=str(os.getenv("SYMBOL", "")).strip() or first_universe_symbol())
    p.add_argument("--sleep-sec", type=int, default=to_int(os.getenv("SCAN_INTERVAL_SEC", "60"), 60))
    p.add_argument("--iterations", type=int, default=0, help="0 means infinite loop.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--lock-path", default=str(os.getenv("M13_LIVE_LOCK_PATH", "data/state/offhours_validation.lock") or "data/state/offhours_validation.lock"))
    p.add_argument("--lock-stale-sec", type=int, default=to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    load_env_file(str(resolve_path_from_root(ROOT, str(args.env_path or ""), ".env")))
    apply_runtime_paths(
        state_path=str(args.state_path or "").strip(),
        event_log_path=str(args.event_log_path or "").strip(),
    )
    enforce_safe_runtime()

    symbol = normalize_symbol(args.symbol)
    state = build_initial_state(symbol)
    lock_path = resolve_path_from_root(ROOT, str(args.lock_path or ""), "data/state/offhours_validation.lock")
    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=max(1, int(args.lock_stale_sec)))
    if not acquired:
        print(json.dumps({"ok": False, "reason": reason, "lock_path": str(lock_path)}, ensure_ascii=False))
        return 4

    iterations = 1 if bool(args.once) else max(0, int(args.iterations))
    count = 0
    last_summary: Dict[str, Any] = {}

    try:
        while True:
            count += 1
            state = run_offhours_validation_once(state)
            last_summary = iteration_summary(state, iteration=count)

            if bool(args.json):
                print(json.dumps(last_summary, ensure_ascii=False))
            else:
                print(
                    f"iteration={count} decision={last_summary.get('decision')} "
                    f"selected={last_summary.get('selected_symbol')} intents={last_summary.get('intent_count')} "
                    f"execution_allowed={last_summary.get('execution_allowed')} "
                    f"positions={last_summary.get('mock_position_count')}"
                )

            if bool(args.once):
                break
            if iterations > 0 and count >= iterations:
                break
            time.sleep(max(1, int(args.sleep_sec)))
    finally:
        release_live_loop_lock(lock_path)

    return 0 if last_summary else 3


if __name__ == "__main__":
    raise SystemExit(main())
