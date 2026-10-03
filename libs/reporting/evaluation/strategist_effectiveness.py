from __future__ import annotations

from collections import defaultdict
from typing import Any

from .contracts import CONTRACT_VERSION, DecisionClass
from .metrics import performance_metrics


def build_strategist_effectiveness(
    trade_evaluations: list[dict[str, Any]],
    attributions: list[dict[str, Any]],
    q9_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_playbook: dict[str, list[float]] = defaultdict(list)
    for row in trade_evaluations:
        value = (row.get("realized_outcome") or {}).get("net_return_pct")
        if value is None or not bool((row.get("integrity") or {}).get("promotion_metric_eligible")):
            continue
        playbook = str((row.get("tactic_alignment") or {}).get("playbook") or "unknown")
        by_playbook[playbook].append(float(value))
    comparable = [
        row for row in attributions
        if (row.get("deltas") or {}).get("strategist_delta_pct") is not None
    ]
    nontrivial = [
        row for row in comparable
        if bool((row.get("strategist_selected") or {}).get("changed_scanner_top1"))
    ]
    windows = list(q9_windows or [])
    eligible_controls = []
    for window in windows:
        scanner_control = window.get("scanner_control") if isinstance(window.get("scanner_control"), dict) else {}
        eligibility = scanner_control.get("full_strategist_control_eligibility")
        eligibility = eligibility if isinstance(eligibility, dict) else {}
        if bool(eligibility.get("eligible")):
            eligible_controls.append(window)
    neutral_selection_changes = 0
    for window in eligible_controls:
        scanner = window.get("scanner_control") if isinstance(window.get("scanner_control"), dict) else {}
        strategist = window.get("strategist_selection") if isinstance(window.get("strategist_selection"), dict) else {}
        if str(scanner.get("top1_symbol") or "") and str(strategist.get("selected_symbol") or ""):
            neutral_selection_changes += int(
                str(scanner.get("top1_symbol") or "") != str(strategist.get("selected_symbol") or "")
            )
    control_status = (
        "CONTROL_CAPTURE_ACTIVE_AWAITING_PAIRED_FORWARD"
        if eligible_controls
        else "NOT_MEASURABLE"
    )
    return {
        "schema_version": "strategist_effectiveness.v2",
        "contract_version": CONTRACT_VERSION,
        "decision_class": DecisionClass.INSUFFICIENT_EVIDENCE.value,
        "runtime_order": "strategist_initial_frame_then_scanner",
        "full_strategist_contribution": {
            "status": control_status,
            "eligible_control_count": len(eligible_controls),
            "ineligible_control_count": len(windows) - len(eligible_controls),
            "selection_change_count": neutral_selection_changes,
            "missing_control": (
                "paired strategy-neutral and strategy-influenced forward outcomes"
                if eligible_controls
                else "naturally strategy-neutral candidate sourcing and ranking cycles"
            ),
            "reason": (
                "Eligible neutral cycles are now identified; economic value still requires paired forward outcomes."
                if eligible_controls
                else "same-universe Scanner controls may already contain Strategist source-policy influence"
            ),
            "causal_claim_allowed": False,
        },
        "ranking_overlay": {
            "comparable_count": len(comparable),
            "selection_change_count": len(nontrivial),
            "scope": "same_candidate_universe_ranking_only",
            "decision_class": DecisionClass.INSUFFICIENT_EVIDENCE.value,
            "note": "symbol changes prove overlay influence, not economic value; paired forward outcomes are required",
        },
        "post_scanner_refresh": {
            "status": "NOT_MEASURABLE",
            "missing_control": "first-Scanner versus post-refresh Scanner paired forward outcomes",
        },
        "scanner_vs_strategist": {
            "comparable_count": len(comparable),
            "selection_change_count": len(nontrivial),
            "deprecated_name": True,
            "replacement": "ranking_overlay",
            "note": "this is not a full Scanner-versus-Strategist comparison",
        },
        "by_playbook": [
            {"playbook": playbook, **performance_metrics(values)}
            for playbook, values in sorted(by_playbook.items())
        ],
        "missing_comparison_count": len(attributions) - len(comparable),
        "q9_window_count": len(windows),
    }
