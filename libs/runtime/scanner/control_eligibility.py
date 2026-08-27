from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_full_strategist_control_eligibility(pool_meta: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify whether the observed Scanner universe is strategy-neutral.

    This is observation-only. It never changes candidate sourcing or ranking.
    """
    meta = dict(pool_meta or {})
    reasons: list[str] = []
    candidate_source = str(meta.get("candidate_source") or "").strip().lower()
    scanner_candidate_source = str(meta.get("scanner_candidate_source") or "").strip().lower()
    source_policy = dict(meta.get("scanner_source_policy") or {})

    if candidate_source not in {"kiwoom", "kiwoom_market_data"}:
        reasons.append("candidate_source_not_kiwoom_market_data")
    if scanner_candidate_source not in ("", "kiwoom", "market_data"):
        reasons.append("scanner_candidate_source_not_neutral")
    if source_policy:
        reasons.append("strategist_scanner_source_policy_present")
    if list(meta.get("selected_themes") or []):
        reasons.append("strategist_selected_themes_present")
    if list(meta.get("avoid_themes") or []):
        reasons.append("strategist_avoid_themes_present")
    if bool(meta.get("backfill_used")):
        reasons.append("strategist_backfill_used")
    try:
        aggressive = float(meta.get("scan_aggressiveness") or 0.0)
    except (TypeError, ValueError):
        aggressive = 0.0
    if aggressive != 0.0 or bool(meta.get("aggressive_source_expansion_used")):
        reasons.append("strategist_scan_aggressiveness_applied")

    eligible = not reasons
    return {
        "schema_version": "strategist_control_eligibility.v1",
        "behavior_effect": "observation_only",
        "eligible": eligible,
        "status": "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
        "control_scope": "full_candidate_sourcing_and_intrinsic_ranking",
        "ineligibility_reasons": reasons,
        "reason_count": len(reasons),
        "candidate_source": candidate_source,
        "scanner_candidate_source": scanner_candidate_source,
        "note": (
            "Eligible means this runtime cycle exposed a naturally strategy-neutral Scanner universe; "
            "it does not imply superior performance."
        ),
    }


__all__ = ["build_full_strategist_control_eligibility"]
