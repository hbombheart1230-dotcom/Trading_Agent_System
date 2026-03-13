from __future__ import annotations

import json
import os
import sys
import time
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.pipelines.offhours_validation import run_offhours_validation_once
from libs.core.settings import load_env_file
from scripts.run_m13_live_loop import _acquire_lock, _first_universe_symbol, _release_lock, _resolve_path_from_root, _to_bool, _to_int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbol(raw: Any) -> str:
    return str(raw or "").strip().upper()


def _build_initial_state(symbol: str) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "offhours_validation": True,
        "runtime_mode": "offhours_validation",
        "exec_context": {"mode": "mock", "offhours_validation": True},
    }
    if symbol:
        state["symbol"] = symbol
    return state


def _enforce_safe_runtime() -> None:
    # Off-hours validation must never route into real execution.
    os.environ["EXECUTION_MODE"] = "mock"
    os.environ["ALLOW_REAL_EXECUTION"] = "false"


def _apply_runtime_paths(*, state_path: str, event_log_path: str) -> None:
    if str(state_path or "").strip():
        os.environ["STATE_STORE_PATH"] = str(state_path).strip()
    if str(event_log_path or "").strip():
        os.environ["EVENT_LOG_PATH"] = str(event_log_path).strip()


def _iteration_summary(state: Dict[str, Any], *, iteration: int) -> Dict[str, Any]:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    monitor = state.get("monitor") if isinstance(state.get("monitor"), dict) else {}
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    return {
        "iteration": int(iteration),
        "ts": _utc_now_iso(),
        "path": str(state.get("path") or ""),
        "decision": str(state.get("decision") or ""),
        "decision_reason": str(state.get("decision_reason") or ""),
        "selected_symbol": str(selected.get("symbol") or ""),
        "selected_score": float(selected.get("score") or 0.0) if selected else 0.0,
        "intent_count": int(len(state.get("intents") or [])) if isinstance(state.get("intents"), list) else 0,
        "monitor_exit_reason": str(monitor.get("exit_reason") or ""),
        "execution_allowed": bool(execution.get("allowed")),
        "execution_reason": str(execution.get("reason") or ""),
        "mock_cash": float(persisted.get("mock_cash") or 0.0),
        "mock_position_count": int(len(persisted.get("mock_positions") or [])) if isinstance(persisted.get("mock_positions"), list) else 0,
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = ArgumentParser(description="Run off-hours validation loop with local mock fills.")
    p.add_argument("--env-path", default=str(ROOT / ".env"))
    p.add_argument("--state-path", default=os.getenv("STATE_STORE_PATH", "").strip())
    p.add_argument("--event-log-path", default=os.getenv("EVENT_LOG_PATH", "").strip())
    p.add_argument("--symbol", default=os.getenv("SYMBOL", "").strip() or _first_universe_symbol())
    p.add_argument("--sleep-sec", type=int, default=_to_int(os.getenv("SCAN_INTERVAL_SEC", "60"), 60))
    p.add_argument("--iterations", type=int, default=0, help="0 means infinite loop.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--lock-path", default=str(os.getenv("M13_LIVE_LOCK_PATH", "data/state/offhours_validation.lock") or "data/state/offhours_validation.lock"))
    p.add_argument("--lock-stale-sec", type=int, default=_to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    load_env_file(str(_resolve_path_from_root(str(args.env_path or ""), ".env")))
    _apply_runtime_paths(
        state_path=str(args.state_path or "").strip(),
        event_log_path=str(args.event_log_path or "").strip(),
    )
    _enforce_safe_runtime()

    symbol = _normalize_symbol(args.symbol)
    state = _build_initial_state(symbol)
    lock_path = _resolve_path_from_root(str(args.lock_path or ""), "data/state/offhours_validation.lock")
    acquired, reason = _acquire_lock(lock_path, lock_stale_sec=max(1, int(args.lock_stale_sec)))
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
            last_summary = _iteration_summary(state, iteration=count)

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
        _release_lock(lock_path)

    return 0 if last_summary else 3


if __name__ == "__main__":
    raise SystemExit(main())
