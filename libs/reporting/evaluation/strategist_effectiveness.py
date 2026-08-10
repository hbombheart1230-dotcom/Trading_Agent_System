from __future__ import annotations

from collections import defaultdict
from typing import Any

from .contracts import CONTRACT_VERSION, DecisionClass
from .metrics import performance_metrics


def build_strategist_effectiveness(trade_evaluations: list[dict[str, Any]], attributions: list[dict[str, Any]]) -> dict[str, Any]:
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
    return {
        "schema_version": "strategist_effectiveness.v2",
        "contract_version": CONTRACT_VERSION,
        "decision_class": DecisionClass.INSUFFICIENT_EVIDENCE.value,
        "runtime_order": "strategist_initial_frame_then_scanner",
        "full_strategist_contribution": {
            "status": "NOT_MEASURABLE",
            "missing_control": "parallel strategy-neutral candidate sourcing and ranking shadow",
            "reason": "same-universe Scanner controls may already contain Strategist source-policy influence",
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
    }
