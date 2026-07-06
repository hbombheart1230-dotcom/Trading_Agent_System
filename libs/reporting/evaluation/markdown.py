from __future__ import annotations

from typing import Any


def render_daily_scorecard(payload: dict[str, Any]) -> str:
    integrity = payload.get("artifact_integrity") or {}
    performance = payload.get("realized_performance") or {}
    attribution = payload.get("selection_attribution") or {}
    horizon = payload.get("horizon_alignment") or {}
    shadow = payload.get("q8_shadow_evidence") or {}
    phase = payload.get("evaluation_phase") or {}
    gate = phase.get("full_chain_start_gate") or {}
    return "\n".join([
        f"# Q9 Daily Scorecard - {payload.get('day', '')}",
        "",
        f"- Decision: **{payload.get('decision_class', '')}**",
        f"- Q8 status: **{phase.get('q8_status', '')}**",
        f"- Q9 status: **{phase.get('q9_status', '')}**",
        f"- Full-chain Start Gate: **{gate.get('status', '')}** ({float(gate.get('coverage') or 0) * 100:.1f}%)",
        f"- Missing gate items: {', '.join(gate.get('missing') or []) or 'None'}",
        f"- Artifact coverage: {float(integrity.get('required_coverage') or 0) * 100:.1f}%",
        f"- Trades: {integrity.get('trade_count', 0)} total / {integrity.get('eligible_trade_count', 0)} eligible",
        "",
        "## Realized Performance",
        "",
        f"- Count: {performance.get('count', 0)}",
        f"- Win rate: {float(performance.get('win_rate') or 0) * 100:.1f}%",
        f"- Average return: {float(performance.get('average_return_pct') or 0):.4f}%",
        f"- Profit factor: {performance.get('profit_factor', 0)}",
        f"- Maximum drawdown: {float(performance.get('maximum_drawdown_pct') or 0):.4f}%",
        "",
        "## Attribution",
        "",
        f"- Scanner/Strategist comparable: {attribution.get('comparison_count', 0)}",
        f"- Strategist delta: {attribution.get('average_strategist_delta_pct')}",
        f"- Unavailable comparisons: {attribution.get('unavailable_count', 0)}",
        "",
        "## Horizon Alignment",
        "",
        f"- Observed horizon contracts: {horizon.get('observed_count', 0)}",
        f"- Exit before min hold: {horizon.get('exit_before_min_hold_count', 0)}",
        f"- Exit before target hold: {horizon.get('exit_before_target_hold_count', 0)}",
        f"- Horizon violation candidates: {horizon.get('horizon_violation_candidate_count', 0)}",
        f"- Target hold would improve exit: {horizon.get('target_hold_would_improve_exit_count', 0)}",
        f"- Average early-exit cost: {horizon.get('average_early_exit_cost_pct')}",
        "",
        "## Q8 Evidence",
        "",
        f"- Candidates: {shadow.get('candidate_count')}",
        f"- Trusted forward count: {shadow.get('trusted_forward_count')}",
        f"- Trusted coverage: {shadow.get('trusted_forward_coverage')}",
        f"- Promotion allowed: {shadow.get('promotion_allowed')}",
        "",
    ])


def render_trade_evaluation(payload: dict[str, Any]) -> str:
    integrity = payload.get("integrity") or {}
    outcome = payload.get("realized_outcome") or {}
    horizon = payload.get("horizon_alignment") or {}
    return "\n".join([
        f"# Q9 Trade Evaluation - {payload.get('trade_id', '')}",
        "",
        f"- Symbol: {payload.get('symbol', '')}",
        f"- Integrity: **{integrity.get('status', '')}**",
        f"- Promotion metric eligible: {integrity.get('promotion_metric_eligible')}",
        f"- Net return: {outcome.get('net_return_pct')}",
        f"- Result: {outcome.get('result_label')}",
        f"- Holding seconds: {outcome.get('holding_seconds')}",
        f"- Horizon status: {horizon.get('status')}",
        f"- Horizon bucket: {horizon.get('bucket')}",
        f"- Horizon violation candidate: {horizon.get('horizon_violation_candidate')}",
        f"- Target hold would improve exit: {horizon.get('target_hold_would_improve_exit')}",
        "",
        "## Defects",
        "",
        *([f"- {item}" for item in integrity.get("defects") or []] or ["- None"]),
        "",
        "## Watch Items",
        "",
        *([f"- {item}" for item in integrity.get("watch_items") or []] or ["- None"]),
        "",
    ])
