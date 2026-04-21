from __future__ import annotations

import os
from typing import Any, Dict

from libs.runtime.entrypoint_common import normalize_tick_pipeline, to_bool


def build_live_loop_initial_state(symbol: str, *, tick_pipeline: str) -> Dict[str, Any]:
    normalized_tick_pipeline = normalize_tick_pipeline(tick_pipeline)
    state: Dict[str, Any] = {
        "m13_tick_pipeline": normalized_tick_pipeline,
        "use_exit_policy": True,
    }
    if normalized_tick_pipeline == "integrated_chain":
        state["auto_skill_runner"] = True
    if symbol:
        state["symbol"] = symbol
    return state


def session_hard_gate_enabled(*, session_hard_gate_flag: bool, allow_offhours_flag: bool) -> bool:
    if bool(allow_offhours_flag):
        return False
    if bool(session_hard_gate_flag):
        return True
    return to_bool(os.getenv("M31_MOCK_EXAM_SESSION_HARD_GATE", "true"), True)
