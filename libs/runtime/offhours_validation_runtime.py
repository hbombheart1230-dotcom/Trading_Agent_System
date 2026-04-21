from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_symbol(raw: Any) -> str:
    return str(raw or "").strip().upper()


def build_initial_state(symbol: str) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "offhours_validation": True,
        "runtime_mode": "offhours_validation",
        "exec_context": {"mode": "mock", "offhours_validation": True},
    }
    if symbol:
        state["symbol"] = symbol
    return state


def enforce_safe_runtime() -> None:
    os.environ["EXECUTION_MODE"] = "mock"
    os.environ["ALLOW_REAL_EXECUTION"] = "false"


def apply_runtime_paths(*, state_path: str, event_log_path: str) -> None:
    if str(state_path or "").strip():
        os.environ["STATE_STORE_PATH"] = str(state_path).strip()
    if str(event_log_path or "").strip():
        os.environ["EVENT_LOG_PATH"] = str(event_log_path).strip()


def iteration_summary(state: Dict[str, Any], *, iteration: int) -> Dict[str, Any]:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    monitor = state.get("monitor") if isinstance(state.get("monitor"), dict) else {}
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    return {
        "iteration": int(iteration),
        "ts": utc_now_iso(),
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
        "mock_position_count": int(len(persisted.get("mock_positions") or []))
        if isinstance(persisted.get("mock_positions"), list)
        else 0,
    }
