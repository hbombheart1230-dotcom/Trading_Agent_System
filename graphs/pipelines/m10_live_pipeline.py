from __future__ import annotations

from graphs.nodes.load_state import load_state
from graphs.nodes.build_snapshots import build_snapshots
from graphs.nodes.build_risk_context import build_risk_context
from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.update_state_after_execution import update_state_after_execution
from graphs.nodes.save_state import save_state


def run_m10_live_pipeline(state: dict) -> dict:
    """M10-4: fixed pipeline wiring.

    Order:
      1) load_state
      2) build_snapshots
      3) build_risk_context
      4) execute_from_packet
      5) update_state_after_execution
      6) save_state

    Notes:
      - snapshots readers can be injected via state for testing
      - decision_packet must be present for execute_from_packet
    """
    state = load_state(state)
    state = build_snapshots(state)
    state = build_risk_context(state)
    state = execute_from_packet(state)
    state = update_state_after_execution(state)
    state = save_state(state)
    return state
