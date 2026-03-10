from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger

    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _sanitize(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        out: Dict[str, Any] = {}
        for k, x in v.items():
            out[str(k)] = _sanitize(x)
        return out
    if isinstance(v, (list, tuple)):
        return [_sanitize(x) for x in v]
    return str(v)


def append_decision_trace(
    state: Dict[str, Any],
    *,
    agent: str,
    payload: Dict[str, Any] | None = None,
    event: str = "snapshot",
    max_entries: int = 64,
) -> Dict[str, Any]:
    """Append one lightweight cross-agent decision-trace ledger entry.

    This is additive observability only:
    - does not mutate trading decisions
    - does not change guard/approval behavior
    - keeps payload intentionally compact for reporter consumption
    """
    run_id = str(state.get("run_id") or "").strip()
    safe_payload = _sanitize(dict(payload or {}))

    ledger = state.get("decision_trace_ledger")
    if not isinstance(ledger, dict):
        ledger = {
            "run_id": run_id or None,
            "entries": [],
            "latest_by_agent": {},
        }

    if not ledger.get("run_id") and run_id:
        ledger["run_id"] = run_id

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        entries = []

    entry = {
        "run_id": run_id or None,
        "ts_epoch": int(time.time()),
        "agent": str(agent or "").strip().lower(),
        "payload": safe_payload,
    }
    entries.append(entry)
    if max_entries > 0 and len(entries) > int(max_entries):
        entries = entries[-int(max_entries) :]

    ledger["entries"] = entries
    latest = ledger.get("latest_by_agent")
    if not isinstance(latest, dict):
        latest = {}
    latest[str(entry["agent"])] = safe_payload
    ledger["latest_by_agent"] = latest

    state["decision_trace_ledger"] = ledger
    # Alias for operator-facing naming.
    state["reason_ledger"] = ledger

    if run_id:
        try:
            logger = _make_event_logger(state)
            logger.log(
                run_id=run_id,
                stage="decision_trace",
                event=str(event or "snapshot"),
                payload={
                    "agent": str(entry["agent"]),
                    "payload": safe_payload,
                },
            )
        except Exception:
            pass
    return state

