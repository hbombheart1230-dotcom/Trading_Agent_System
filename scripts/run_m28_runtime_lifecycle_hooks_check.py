from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file
from libs.runtime.runtime_lifecycle import shutdown_hook
from libs.runtime.runtime_lifecycle import startup_hook


def _env_str(name: str, default: str) -> str:
    raw = str(os.getenv(name, "") or "").strip()
    return raw if raw else str(default)


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except Exception:
        return int(default)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M28-2 runtime lifecycle hooks check.")
    p.add_argument(
        "--state-path",
        default=_env_str("M28_LIFECYCLE_STATE_PATH", "data/state/m28_runtime_lifecycle.json"),
    )
    p.add_argument(
        "--lock-stale-sec",
        type=int,
        default=_env_int("M28_LIFECYCLE_LOCK_STALE_SEC", 1800),
    )
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    load_env_file(".env")
    args = _build_parser().parse_args(argv)

    state_path = Path(str(args.state_path).strip())
    if not bool(args.no_clear):
        try:
            if state_path.exists():
                state_path.unlink()
            if state_path.parent.exists():
                # keep sibling artifacts; just ensure path is writable
                state_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    s1 = startup_hook(
        state_path=str(state_path),
        lock_stale_sec=max(1, int(args.lock_stale_sec)),
    )
    s2 = startup_hook(
        state_path=str(state_path),
        lock_stale_sec=max(1, int(args.lock_stale_sec)),
    )

    if bool(args.inject_fail):
        stop = shutdown_hook(
            state_path=str(state_path),
            run_id="wrong-run-id",
            final_status="stopped",
        )
    else:
        stop = shutdown_hook(
            state_path=str(state_path),
            run_id=str(s1.get("run_id") or ""),
            final_status="stopped",
        )

    s3 = startup_hook(
        state_path=str(state_path),
        lock_stale_sec=max(1, int(args.lock_stale_sec)),
    )

    failures: List[str] = []
    if not bool(s1.get("ok")):
        failures.append("startup#1 failed")
    if bool(s2.get("ok")):
        failures.append("startup#2 should be blocked by active run")
    if str(s2.get("reason") or "") != "active_run":
        failures.append("startup#2 reason != active_run")
    if not bool(stop.get("ok")):
        failures.append("shutdown failed")
    if not bool(s3.get("ok")):
        failures.append("startup#3 after shutdown failed")

    out = {
        "ok": len(failures) == 0,
        "inject_fail": bool(args.inject_fail),
        "state_path": str(state_path),
        "startup_1": s1,
        "startup_2": s2,
        "shutdown": stop,
        "startup_3": s3,
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} inject_fail={out['inject_fail']} "
            f"startup1_ok={bool(s1.get('ok'))} startup2_reason={s2.get('reason')} "
            f"shutdown_ok={bool(stop.get('ok'))} startup3_ok={bool(s3.get('ok'))} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
