from __future__ import annotations

from typing import Any, Dict


def build_commander_decision_frame(
    state: Dict[str, Any],
    mode_value: str,
    phase_value: str,
    *,
    status_value: str,
    path_value: str,
    reason_text: str = "",
) -> Dict[str, Any]:
    runtime_plan = state.get("runtime_plan") if isinstance(state.get("runtime_plan"), dict) else {}
    portfolio_snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    portfolio_preflight = state.get("portfolio_preflight") if isinstance(state.get("portfolio_preflight"), dict) else {}
    return {
        "session_type": str(phase_value or ""),
        "market_clock_phase": str(phase_value or ""),
        "portfolio_state_summary": {
            "position_count": len(list(portfolio_snapshot.get("positions") or [])),
            "cash": portfolio_snapshot.get("cash"),
            "positions_source": str(portfolio_preflight.get("positions_source") or ""),
            "preflight_status": str(portfolio_preflight.get("status") or ""),
        },
        "market_regime_summary": {
            "market_regime": str(strategist_output.get("market_regime") or ""),
            "market_sentiment": str(strategist_output.get("market_sentiment") or ""),
            "playbook": str(strategist_output.get("playbook") or ""),
        },
        "goal": (
            "Execute full trading session flow."
            if str(phase_value or "").strip() == "session"
            else f"Run {str(phase_value or '').strip() or 'runtime'} phase safely."
        ),
        "agent_invocation_plan": list(runtime_plan.get("agents") or []),
        "decision_checkpoints": {
            "runtime_transition": str(state.get("runtime_transition") or ""),
            "runtime_status": str(status_value or state.get("runtime_status") or ""),
            "portfolio_preflight_status": str(portfolio_preflight.get("status") or ""),
            "runtime_fast_path": dict(state.get("runtime_fast_path") or {})
            if isinstance(state.get("runtime_fast_path"), dict)
            else {},
        },
        "final_runtime_path": str(path_value or ""),
        "final_reason": str(reason_text or state.get("runtime_status") or ""),
        "handoff_instruction": (
            "Proceed to downstream agents according to runtime plan."
            if str(status_value or "").strip().lower() in {"ok", "ready", "preopen_ready", "closeout_ready"}
            else "Do not proceed. Inspect commander/runtime status first."
        ),
        "mode": str(mode_value or ""),
    }
