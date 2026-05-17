from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from libs.runtime.commander.env_overrides import is_trueish
from libs.runtime.commander.policy_surface import RuntimeMode, RuntimePhase


def normalize_mode(value: Any) -> RuntimeMode:
    v = str(value or "").strip().lower()
    if v == "decision_packet":
        return "decision_packet"
    if v in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    return "graph_spine"


def normalize_transition(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("retry", "pause", "cancel", "resume"):
        return v
    return ""


def normalize_phase(value: Any) -> RuntimePhase:
    v = str(value or "").strip().lower()
    if v == "preopen":
        return "preopen"
    if v == "closeout":
        return "closeout"
    return "session"


def runtime_agent_chain(mode: RuntimeMode, phase: RuntimePhase) -> Tuple[str, ...]:
    if phase == "preopen":
        return ("commander_router", "strategist")
    if phase == "closeout":
        return ("commander_router",)
    if mode == "decision_packet":
        return ("commander_router", "strategist", "supervisor", "executor", "reporter")
    if mode == "integrated_chain":
        return ("commander_router", "strategist", "scanner", "monitor", "decision", "supervisor", "executor", "reporter")
    return ("commander_router", "strategist", "scanner", "monitor", "supervisor", "executor", "reporter")


def annotate_runtime_plan(state: Dict[str, Any], selected: RuntimeMode, phase: RuntimePhase) -> Dict[str, Any]:
    state["runtime_plan"] = {
        "mode": selected,
        "phase": phase,
        "agents": list(runtime_agent_chain(selected, phase)),
    }
    return state


def resolve_runtime_mode(state: Dict[str, Any], *, mode: Optional[RuntimeMode] = None) -> RuntimeMode:
    """Resolve runtime mode with explicit precedence."""
    if mode is not None:
        return normalize_mode(mode)

    allow_decision_packet = is_trueish(state.get("allow_decision_packet_runtime")) or is_trueish(
        os.getenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "")
    )

    if "runtime_mode" in state:
        selected = normalize_mode(state.get("runtime_mode"))
        if selected == "decision_packet" and not allow_decision_packet:
            return "graph_spine"
        return selected
    env_mode = os.getenv("COMMANDER_RUNTIME_MODE", "")
    selected = normalize_mode(env_mode or "graph_spine")
    if selected == "decision_packet" and not allow_decision_packet:
        return "graph_spine"
    return selected


def resolve_runtime_phase(state: Dict[str, Any], *, phase: Optional[RuntimePhase] = None) -> RuntimePhase:
    """Resolve runtime phase with explicit precedence."""
    if phase is not None:
        return normalize_phase(phase)
    if "runtime_phase" in state:
        return normalize_phase(state.get("runtime_phase"))
    return normalize_phase(os.getenv("COMMANDER_RUNTIME_PHASE", "session"))
