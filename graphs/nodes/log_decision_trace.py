from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Tuple

def _import_event_logger() -> Tuple[Any, Any]:
    # supports both old/new layouts
    try:
        from libs.event_logger import EventLogger, new_run_id  # type: ignore
        return EventLogger, new_run_id
    except Exception:
        from libs.logging.event_logger import EventLogger, new_run_id  # type: ignore
        return EventLogger, new_run_id

def log_decision_trace(state: dict) -> dict:
    """M11-4 node: persist decision inputs/features/decision to events.jsonl.

    Expects:
      - state['run_id'] optional
      - state['market_snapshot'] optional
      - state['portfolio_snapshot'] optional
      - state['risk_context'] optional
      - state['decision_packet'] optional
      - state['decision_trace'] optional

    Produces:
      - appends event: stage='decision', event='trace'
    """
    EventLogger, new_run_id = _import_event_logger()
    log_path = os.getenv("EVENT_LOG_PATH", "./data/events.jsonl")
    logger = EventLogger(log_path=Path(log_path))

    run_id = state.get("run_id") or new_run_id()
    state["run_id"] = run_id

    payload: Dict[str, Any] = {
        "ts": int(time.time()),
        "symbol": state.get("symbol") or state.get("selected_symbol"),
        "market": state.get("market_snapshot") or {},
        "portfolio": state.get("portfolio_snapshot") or {},
        "risk": state.get("risk_context") or {},
        "decision_packet": state.get("decision_packet") or {},
        "decision_trace": state.get("decision_trace") or {},
    }

    logger.log(run_id=run_id, stage="decision", event="trace", payload=payload)
    return state
