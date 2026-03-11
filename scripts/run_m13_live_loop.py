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

from libs.core.settings import load_env_file
from libs.runtime.market_hours import MarketHours
from libs.runtime.market_hours import now_kst
from graphs.pipelines.m13_live_loop import run_m13_once


def _first_universe_symbol() -> str:
    raw = str(os.getenv("UNIVERSE_SYMBOLS", "") or "").strip()
    if not raw:
        return ""
    for part in raw.split(","):
        s = str(part or "").strip()
        if s:
            return s
    return ""


def _normalize_tick_pipeline(v: Any) -> str:
    raw = str(v or "").strip().lower()
    if raw in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    return "legacy_m10"


def _build_initial_state(symbol: str, *, tick_pipeline: str) -> Dict[str, Any]:
    # Minimal initial state; nodes/pipelines will enrich it.
    state: Dict[str, Any] = {
        "m13_tick_pipeline": _normalize_tick_pipeline(tick_pipeline),
        # Keep integrated runtime exit behavior deterministic from env-driven runtime profile.
        "use_exit_policy": _to_bool(os.getenv("USE_EXIT_POLICY", "false"), False),
    }
    if symbol:
        state["symbol"] = symbol
    return state


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_bool(v: Any, default: bool = False) -> bool:
    raw = str(v if v is not None else "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _session_hard_gate_enabled(*, session_hard_gate_flag: bool, allow_offhours_flag: bool) -> bool:
    if bool(allow_offhours_flag):
        return False
    if bool(session_hard_gate_flag):
        return True
    return _to_bool(os.getenv("M31_MOCK_EXAM_SESSION_HARD_GATE", "true"), True)


def _pid_exists(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
    except Exception:
        return False
    return True


def _acquire_lock(lock_path: Path, *, lock_stale_sec: int) -> tuple[bool, str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    stale = max(1, int(lock_stale_sec))

    if lock_path.exists():
        obj: Dict[str, Any] = {}
        try:
            obj = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {}

        pid = _to_int(obj.get("pid"), 0)
        started_epoch = _to_int(obj.get("started_epoch"), 0)
        # Fast recovery for forced-stop cases: reclaim lock if owner pid is gone.
        if pid > 0 and not _pid_exists(pid):
            try:
                lock_path.unlink()
            except Exception:
                return False, "lock_owner_dead_unlink_failed"
        else:
            age = max(0, now - started_epoch) if started_epoch > 0 else stale + 1
            if age <= stale:
                return False, "lock_active"
            try:
                lock_path.unlink()
            except Exception:
                return False, "lock_stale_unlink_failed"

    payload = {
        "pid": int(os.getpid()),
        "started_epoch": int(now),
        "started_ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with open(lock_path, "x", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False))
        return True, ""
    except FileExistsError:
        return False, "lock_active"
    except Exception:
        return False, "lock_create_failed"


def _release_lock(lock_path: Path) -> None:
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def _resolve_path_from_root(raw: str, default_rel: str) -> Path:
    s = str(raw or "").strip() or str(default_rel)
    p = Path(s)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main(argv: Optional[list[str]] = None) -> int:
    load_env_file(str(ROOT / ".env"))
    p = ArgumentParser(description="Run M13 live loop (mock-safe).")
    p.add_argument(
        "--symbol",
        default=os.getenv("SYMBOL", "").strip() or _first_universe_symbol(),
        help="Primary symbol for live loop; defaults to SYMBOL env or first UNIVERSE_SYMBOLS entry.",
    )
    p.add_argument(
        "--tick-pipeline",
        choices=["legacy_m10", "integrated_chain"],
        default=_normalize_tick_pipeline(os.getenv("M13_TICK_PIPELINE", "legacy_m10")),
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
        default=_to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800),
        help="Stale lock threshold seconds.",
    )
    args = p.parse_args(argv)

    state: Dict[str, Any] = _build_initial_state(
        str(args.symbol or "").strip(),
        tick_pipeline=str(args.tick_pipeline or "legacy_m10"),
    )
    if state.get("m13_tick_pipeline") == "legacy_m10" and not state.get("symbol"):
        raise SystemExit("symbol is required for legacy_m10: set --symbol or SYMBOL/UNIVERSE_SYMBOLS env")

    session_hard_gate = _session_hard_gate_enabled(
        session_hard_gate_flag=bool(args.session_hard_gate),
        allow_offhours_flag=bool(args.allow_offhours),
    )
    if session_hard_gate:
        mh = MarketHours()
        check_dt = now_kst()
        if not mh.is_open(check_dt):
            print(f"live_loop aborted: market_closed session_hard_gate=true now_kst={check_dt.isoformat()}")
            return 5

    lock_path = _resolve_path_from_root(str(args.lock_path or ""), "data/state/m13_live_loop.lock")
    acquired, reason = _acquire_lock(lock_path, lock_stale_sec=max(1, int(args.lock_stale_sec)))
    if not acquired:
        print(f"live_loop lock not acquired: {reason} lock_path={lock_path}")
        return 4

    try:
        while True:
            dt: datetime = now_kst()
            state = run_m13_once(state, dt=dt)

            if args.once:
                break

            time.sleep(max(1, int(args.sleep_sec)))
    finally:
        _release_lock(lock_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
