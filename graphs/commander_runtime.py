from __future__ import annotations

"""M21-1: Canonical commander runtime entry.

This module provides one stable entry for orchestration while preserving
existing runtime behavior.

Modes:
  - graph_spine: run M17 graph spine (`run_trading_graph`)
  - decision_packet: run strategist decision + execution packet path
    (`decide_trade` -> `execute_from_packet`)

Default mode is graph_spine for backward compatibility.
"""

import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional, Tuple

from graphs.trading_graph import run_trading_graph
from graphs.nodes.decide_trade import decide_trade
from graphs.nodes.execute_from_packet import execute_from_packet
from libs.runtime.resilience_state import ensure_runtime_resilience_state


RuntimeMode = Literal["graph_spine", "decision_packet"]


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_mode(value: Any) -> RuntimeMode:
    v = str(value or "").strip().lower()
    if v == "decision_packet":
        return "decision_packet"
    return "graph_spine"


def _normalize_transition(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("retry", "pause", "cancel", "resume"):
        return v
    return ""


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _runtime_now_epoch(state: Dict[str, Any]) -> int:
    return _coerce_int(state.get("now_epoch"), int(time.time()))


def _resolve_commander_cooldown_policy(state: Dict[str, Any]) -> Tuple[int, int]:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    threshold_default = _coerce_int(os.getenv("COMMANDER_INCIDENT_THRESHOLD", "0"), 0)
    cooldown_default = _coerce_int(os.getenv("COMMANDER_COOLDOWN_SEC", "0"), 0)
    threshold = _coerce_int(policy.get("incident_threshold"), threshold_default)
    cooldown_sec = _coerce_int(policy.get("cooldown_sec"), cooldown_default)
    return max(0, threshold), max(0, cooldown_sec)


def _set_degrade_mode(state: Dict[str, Any], *, reason: str) -> None:
    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        resilience = {}
        state["resilience"] = resilience
    resilience["degrade_mode"] = True
    if not str(resilience.get("degrade_reason") or "").strip():
        resilience["degrade_reason"] = str(reason or "")


def _apply_commander_cooldown_guard(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    """M23-4: apply incident/cooldown policy before running node path."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)
    now_epoch = _runtime_now_epoch(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0))
    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))

    if cooldown_until > now_epoch:
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="commander_cooldown_active")
        return False, state, {
            "reason": "cooldown_active",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = now_epoch + cooldown_sec
        resilience["cooldown_until_epoch"] = cooldown_until
        state["resilience"] = resilience
        state["runtime_status"] = "cooldown_wait"
        state["runtime_transition"] = "cooldown"
        _set_degrade_mode(state, reason="incident_threshold_cooldown")
        return False, state, {
            "reason": "incident_threshold_cooldown",
            "incident_count": incident_count,
            "incident_threshold": threshold,
            "cooldown_sec": cooldown_sec,
            "cooldown_until_epoch": cooldown_until,
            "now_epoch": now_epoch,
        }

    return True, state, {
        "reason": "cooldown_not_active",
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "now_epoch": now_epoch,
    }


def _register_commander_incident(state: Dict[str, Any], *, error_type: str) -> Dict[str, Any]:
    """M23-4: increment incident counter and optionally open commander cooldown."""
    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    now_epoch = _runtime_now_epoch(state)
    threshold, cooldown_sec = _resolve_commander_cooldown_policy(state)

    incident_count = max(0, _coerce_int(resilience.get("incident_count"), 0)) + 1
    resilience["incident_count"] = incident_count
    resilience["last_error_type"] = str(error_type or "")

    cooldown_until = max(0, _coerce_int(resilience.get("cooldown_until_epoch"), 0))
    if threshold > 0 and cooldown_sec > 0 and incident_count >= threshold:
        cooldown_until = max(cooldown_until, now_epoch + cooldown_sec)
        resilience["cooldown_until_epoch"] = cooldown_until
        _set_degrade_mode(state, reason="incident_threshold_cooldown")

    state["resilience"] = resilience
    return {
        "incident_count": incident_count,
        "incident_threshold": threshold,
        "cooldown_sec": cooldown_sec,
        "cooldown_until_epoch": cooldown_until,
        "last_error_type": str(error_type or ""),
    }


def _apply_operator_resume_intervention(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """M23-6: explicit operator intervention to resume runtime from cooldown/degrade."""
    transition = _normalize_transition(state.get("runtime_control"))
    if transition != "resume":
        return state, {}

    resilience = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    before = {
        "degrade_mode": bool(resilience.get("degrade_mode")),
        "degrade_reason": str(resilience.get("degrade_reason") or ""),
        "incident_count": _coerce_int(resilience.get("incident_count"), 0),
        "cooldown_until_epoch": _coerce_int(resilience.get("cooldown_until_epoch"), 0),
        "last_error_type": str(resilience.get("last_error_type") or ""),
    }
    now_epoch = _runtime_now_epoch(state)

    resilience["degrade_mode"] = False
    resilience["degrade_reason"] = ""
    resilience["incident_count"] = 0
    resilience["cooldown_until_epoch"] = 0
    resilience["last_error_type"] = ""
    state["resilience"] = resilience

    return state, {
        "type": "operator_resume",
        "at_epoch": now_epoch,
        "before": before,
        "after": {
            "degrade_mode": False,
            "degrade_reason": "",
            "incident_count": 0,
            "cooldown_until_epoch": 0,
            "last_error_type": "",
        },
    }


def _apply_runtime_transition(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Apply runtime control transition.

    Supported controls in `state["runtime_control"]`:
      - cancel: stop run immediately
      - pause: stop run immediately
      - retry: increment retry counter and continue run
    """
    transition = _normalize_transition(state.get("runtime_control"))
    if not transition:
        return True, state

    state["runtime_transition"] = transition

    if transition == "cancel":
        state["runtime_status"] = "cancelled"
        return False, state

    if transition == "pause":
        state["runtime_status"] = "paused"
        return False, state

    if transition == "resume":
        state["runtime_status"] = "resuming"
        return True, state

    # retry: mark status and continue the selected runtime path.
    state["runtime_status"] = "retrying"
    state["runtime_retry_count"] = _coerce_int(state.get("runtime_retry_count"), 0) + 1
    return True, state


def _runtime_agent_chain(mode: RuntimeMode) -> Tuple[str, ...]:
    if mode == "decision_packet":
        return ("commander_router", "strategist", "supervisor", "executor", "reporter")
    return ("commander_router", "strategist", "scanner", "monitor", "supervisor", "executor", "reporter")


def _annotate_runtime_plan(state: Dict[str, Any], selected: RuntimeMode) -> Dict[str, Any]:
    state["runtime_plan"] = {
        "mode": selected,
        "agents": list(_runtime_agent_chain(selected)),
    }
    return state


def _import_event_logger():
    for mod in ("libs.event_logger", "libs.logging.event_logger", "libs.core.event_logger"):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _ensure_run_id(state: Dict[str, Any]) -> str:
    _EventLogger, new_run_id = _import_event_logger()
    rid = str(state.get("run_id") or new_run_id())
    state["run_id"] = rid
    return rid


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    EventLogger, _new_run_id = _import_event_logger()
    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_commander_event(state: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = _ensure_run_id(state)
        logger.log(run_id=run_id, stage="commander_router", event=event, payload=payload)
    except Exception:
        return


def _portfolio_guard_event_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    pg = state.get("portfolio_guard")
    if not isinstance(pg, dict):
        return {}
    return {
        "portfolio_guard": {
            "applied": bool(pg.get("applied")),
            "approved_total": _coerce_int(pg.get("approved_total"), 0),
            "blocked_total": _coerce_int(pg.get("blocked_total"), 0),
            "blocked_reason_counts": pg.get("blocked_reason_counts")
            if isinstance(pg.get("blocked_reason_counts"), dict)
            else {},
        }
    }


def resolve_runtime_mode(state: Dict[str, Any], *, mode: Optional[RuntimeMode] = None) -> RuntimeMode:
    """Resolve runtime mode with explicit precedence.

    Priority:
      1) explicit argument `mode`
      2) `state["runtime_mode"]`
      3) env `COMMANDER_RUNTIME_MODE`
      4) default `graph_spine`

    Safety guard:
      - decision_packet via state/env requires activation:
        state["allow_decision_packet_runtime"]=true OR
        env COMMANDER_RUNTIME_ALLOW_DECISION_PACKET=true
      - explicit `mode` bypasses this guard (caller-controlled override).
    """
    if mode is not None:
        return _normalize_mode(mode)

    allow_decision_packet = _is_trueish(state.get("allow_decision_packet_runtime")) or _is_trueish(
        os.getenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "")
    )

    if "runtime_mode" in state:
        selected = _normalize_mode(state.get("runtime_mode"))
        if selected == "decision_packet" and not allow_decision_packet:
            return "graph_spine"
        return selected
    env_mode = os.getenv("COMMANDER_RUNTIME_MODE", "")
    selected = _normalize_mode(env_mode or "graph_spine")
    if selected == "decision_packet" and not allow_decision_packet:
        return "graph_spine"
    return selected


def run_commander_runtime(
    state: Dict[str, Any],
    *,
    mode: Optional[RuntimeMode] = None,
    graph_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    decide: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    execute: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one canonical commander runtime step.

    Mode selection uses `resolve_runtime_mode(...)`.
    """
    state = ensure_runtime_resilience_state(state)
    selected = resolve_runtime_mode(state, mode=mode)
    state = _annotate_runtime_plan(state, selected)
    _log_commander_event(
        state,
        "route",
        {"mode": selected, "agents": list(state.get("runtime_plan", {}).get("agents", []))},
    )

    should_run, state = _apply_runtime_transition(state)
    if state.get("runtime_transition"):
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "retry_count": state.get("runtime_retry_count"),
            },
        )
    if not should_run:
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None},
        )
        return state

    state, intervention_payload = _apply_operator_resume_intervention(state)
    if intervention_payload:
        _log_commander_event(state, "intervention", intervention_payload)

    should_run, state, cooldown_payload = _apply_commander_cooldown_guard(state)
    if not should_run:
        _log_commander_event(
            state,
            "transition",
            {
                "transition": state.get("runtime_transition"),
                "status": state.get("runtime_status"),
                "reason": cooldown_payload.get("reason"),
                "cooldown_until_epoch": cooldown_payload.get("cooldown_until_epoch"),
                "incident_count": cooldown_payload.get("incident_count"),
                "incident_threshold": cooldown_payload.get("incident_threshold"),
            },
        )
        _log_commander_event(state, "resilience", cooldown_payload)
        _log_commander_event(
            state,
            "end",
            {"mode": selected, "status": state.get("runtime_status", "stopped"), "path": None},
        )
        return state

    graph_runner = graph_runner or run_trading_graph
    decide = decide or decide_trade
    execute = execute or execute_from_packet

    try:
        if selected == "decision_packet":
            state = decide(state)
            state = execute(state)
            _log_commander_event(
                state,
                "end",
                {
                    "mode": selected,
                    "status": state.get("runtime_status", "ok"),
                    "path": "decision_packet",
                    **_portfolio_guard_event_summary(state),
                },
            )
            return state

        state = graph_runner(state)
        _log_commander_event(
            state,
            "end",
            {
                "mode": selected,
                "status": state.get("runtime_status", "ok"),
                "path": "graph_spine",
                **_portfolio_guard_event_summary(state),
            },
        )
        return state
    except Exception as e:
        incident_payload = _register_commander_incident(state, error_type=type(e).__name__)
        state["runtime_status"] = "error"
        _log_commander_event(
            state,
            "error",
            {"mode": selected, "error_type": type(e).__name__, "error": str(e), **incident_payload},
        )
        raise
