from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _write_state(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def startup_hook(
    *,
    state_path: str,
    lock_stale_sec: int = 1800,
    now_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    path = Path(str(state_path).strip())
    now = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    stale_sec = max(1, int(lock_stale_sec))
    state = _read_state(path)
    status = str(state.get("status") or "").strip().lower()
    started_epoch = _to_int(state.get("started_epoch"), 0)

    if status == "running" and started_epoch > 0:
        age = max(0, now - started_epoch)
        if age <= stale_sec:
            return {
                "ok": False,
                "reason": "active_run",
                "state_path": str(path),
                "status": "running",
                "age_sec": int(age),
                "run_id": str(state.get("run_id") or ""),
            }

    run_id = f"runtime-{now}-{os.getpid()}"
    out = {
        "run_id": run_id,
        "status": "running",
        "pid": int(os.getpid()),
        "started_epoch": int(now),
        "started_ts": _utc_now_iso(),
        "ended_epoch": 0,
        "ended_ts": "",
    }
    _write_state(path, out)
    return {
        "ok": True,
        "reason": "started",
        "state_path": str(path),
        "run_id": run_id,
        "status": "running",
    }


def shutdown_hook(
    *,
    state_path: str,
    run_id: str = "",
    final_status: str = "stopped",
    now_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    path = Path(str(state_path).strip())
    state = _read_state(path)
    now = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    requested_run_id = str(run_id or "").strip()
    current_run_id = str(state.get("run_id") or "").strip()

    if not state:
        return {
            "ok": True,
            "reason": "state_missing",
            "state_path": str(path),
            "run_id": requested_run_id,
            "status": "stopped",
        }

    if requested_run_id and current_run_id and requested_run_id != current_run_id:
        return {
            "ok": False,
            "reason": "run_id_mismatch",
            "state_path": str(path),
            "run_id": current_run_id,
            "requested_run_id": requested_run_id,
            "status": str(state.get("status") or ""),
        }

    out = dict(state)
    out["status"] = str(final_status or "stopped").strip() or "stopped"
    out["ended_epoch"] = int(now)
    out["ended_ts"] = _utc_now_iso()
    _write_state(path, out)

    return {
        "ok": True,
        "reason": "stopped",
        "state_path": str(path),
        "run_id": str(out.get("run_id") or ""),
        "status": str(out.get("status") or "stopped"),
    }
