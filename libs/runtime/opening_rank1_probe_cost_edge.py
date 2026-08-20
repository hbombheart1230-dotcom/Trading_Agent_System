from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "opening_rank1_probe_cost_edge.v2"
FROZEN_EVIDENCE_DATE = "2026-08-14"
FROZEN_EVIDENCE_SOURCE = (
    "docs/offline_alpha/opening_rank1_controlled_probe_2026-08-14.md"
)
MISSING_EVIDENCE_REASONS = frozenset(
    {
        "directional_edge_evidence_missing",
        "estimated_gross_edge_missing",
    }
)

# The source report stores live-net percentages using 0.28% round-trip drag.
# Runtime fallback values below convert them to the frozen Q9 mock drag of
# 1.036849% observed cost plus 0.05% evaluation slippage.
FROZEN_LIVE_DRAG_RATIO = 0.0028
FROZEN_MOCK_DRAG_RATIO = 0.01086849
FROZEN_LIVE_TO_MOCK_DELTA_RATIO = FROZEN_MOCK_DRAG_RATIO - FROZEN_LIVE_DRAG_RATIO
FROZEN_SETUP_EVIDENCE: dict[str, dict[str, Any]] = {
    "DIRECTIONAL_BREADTH": {
        "independent_day_symbol_count": 18,
        "source_live_net_return_15m": 0.016660,
        "source_live_net_return_30m": 0.014919,
        "avg_mock_net_return_15m": 0.00859151,
        "avg_mock_net_return_30m": 0.00685051,
    },
    "FRESH_CHANGE_ACTIVATION": {
        "independent_day_symbol_count": 6,
        "source_live_net_return_15m": 0.070757,
        "source_live_net_return_30m": 0.048750,
        "avg_mock_net_return_15m": 0.06268851,
        "avg_mock_net_return_30m": 0.04068151,
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def evaluate_opening_probe_cost_edge(
    *,
    candidate_setup: str,
    entry_cost_filter: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve cost evidence for the bounded opening Rank-1 mock probe.

    The normal cost filter remains authoritative whenever it has actual evidence.
    Frozen setup evidence is allowed only when that filter failed exclusively
    because its directional/gross edge estimate was unavailable.
    """

    cost = dict(entry_cost_filter or {})
    setup = _text(candidate_setup).upper()
    fail_reasons = [
        _text(item)
        for item in list(cost.get("fail_reasons") or [])
        if _text(item)
    ]
    fail_reason_set = frozenset(fail_reasons)
    normal_passed = bool(cost.get("passed"))
    evidence = dict(FROZEN_SETUP_EVIDENCE.get(setup) or {})
    conservative_net_return = min(
        _to_float(evidence.get("avg_mock_net_return_15m")),
        _to_float(evidence.get("avg_mock_net_return_30m")),
    ) if evidence else 0.0
    minimum_net_return = max(0.0, _to_float(cost.get("min_cost_adjusted_edge_pct")))

    missing_only = bool(
        fail_reason_set
        and fail_reason_set.issubset(MISSING_EVIDENCE_REASONS)
    )
    fallback_available = bool(evidence)
    fallback_passed = bool(
        not normal_passed
        and missing_only
        and fallback_available
        and conservative_net_return >= minimum_net_return
    )
    passed = bool(normal_passed or fallback_passed)

    if normal_passed:
        reason = "normal_cost_filter_passed"
        source = "normal_entry_cost_filter"
    elif not missing_only:
        reason = "normal_cost_filter_has_non_missing_failure"
        source = "normal_entry_cost_filter"
    elif not fallback_available:
        reason = "frozen_setup_evidence_unavailable"
        source = "frozen_opening_rank1_setup_evidence"
    elif conservative_net_return < minimum_net_return:
        reason = "frozen_setup_edge_below_minimum"
        source = "frozen_opening_rank1_setup_evidence"
    else:
        reason = "frozen_setup_edge_substituted_for_missing_estimate"
        source = "frozen_opening_rank1_setup_evidence"

    return {
        "schema_version": SCHEMA_VERSION,
        "passed": passed,
        "reason": reason,
        "source": source,
        "normal_cost_filter_passed": normal_passed,
        "normal_fail_reasons": fail_reasons,
        "missing_evidence_only": missing_only,
        "fallback_applied": fallback_passed,
        "candidate_setup": setup,
        "frozen_evidence_date": FROZEN_EVIDENCE_DATE,
        "frozen_evidence_source": FROZEN_EVIDENCE_SOURCE,
        "cost_basis": {
            "source_live_drag_ratio": FROZEN_LIVE_DRAG_RATIO,
            "target_mock_drag_ratio": FROZEN_MOCK_DRAG_RATIO,
            "live_to_mock_delta_ratio": FROZEN_LIVE_TO_MOCK_DELTA_RATIO,
            "target_basis": "mock_net_after_observed_cost_and_evaluation_slippage",
        },
        "independent_day_symbol_count": int(
            evidence.get("independent_day_symbol_count") or 0
        ),
        "source_live_net_return_15m": (
            _to_float(evidence.get("source_live_net_return_15m")) if evidence else None
        ),
        "source_live_net_return_30m": (
            _to_float(evidence.get("source_live_net_return_30m")) if evidence else None
        ),
        "avg_mock_net_return_15m": (
            _to_float(evidence.get("avg_mock_net_return_15m")) if evidence else None
        ),
        "avg_mock_net_return_30m": (
            _to_float(evidence.get("avg_mock_net_return_30m")) if evidence else None
        ),
        "conservative_net_return": conservative_net_return if evidence else None,
        "minimum_net_return": minimum_net_return,
        "behavior_effect": (
            "controlled_mock_entry_probe_only" if fallback_passed else "none"
        ),
    }


__all__ = [
    "FROZEN_EVIDENCE_DATE",
    "FROZEN_EVIDENCE_SOURCE",
    "FROZEN_LIVE_DRAG_RATIO",
    "FROZEN_LIVE_TO_MOCK_DELTA_RATIO",
    "FROZEN_MOCK_DRAG_RATIO",
    "FROZEN_SETUP_EVIDENCE",
    "MISSING_EVIDENCE_REASONS",
    "SCHEMA_VERSION",
    "evaluate_opening_probe_cost_edge",
]
