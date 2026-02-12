from __future__ import annotations

from graphs.nodes.scan_candidates import scan_candidates
from graphs.nodes.select_candidate import select_candidate
from graphs.nodes.decide_trade import decide_trade

# These should already exist from M9/M10 patches
from graphs.nodes.build_market_snapshot import build_market_snapshot
from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot
from graphs.nodes.update_risk_context import update_risk_context
from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.update_state_after_execution import update_state_after_execution
from graphs.nodes.persist_state import persist_state


def run_m11_2_live_pipeline(state: dict) -> dict:
    """M11-2 pipeline: scan -> select -> snapshot -> risk -> decide -> execute -> persist."""
    state = scan_candidates(state)
    state = select_candidate(state)

    state = build_market_snapshot(state)
    state = build_portfolio_snapshot(state)
    state = update_risk_context(state)

    state = decide_trade(state)
    state = execute_from_packet(state)
    state = update_state_after_execution(state)
    state = persist_state(state)
    return state
