from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


CONTRACT_VERSION = "q9_evaluation_contract.v1"


class EvidenceClass(str, Enum):
    REALIZED = "REALIZED"
    TRUSTED_SHADOW = "TRUSTED_SHADOW"
    RECONSTRUCTED = "RECONSTRUCTED"
    UNAVAILABLE = "UNAVAILABLE"


class IntegrityStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    FAIL = "FAIL"
    BLOCKER = "BLOCKER"


class DecisionClass(str, Enum):
    RETAIN = "RETAIN"
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"
    ADJUST_AND_RETEST = "ADJUST_AND_RETEST"
    REJECT = "REJECT"
    DEPRECATE_CANDIDATE = "DEPRECATE_CANDIDATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


DIRECTIONAL_MIN_OBSERVATIONS = 20
DIRECTIONAL_MIN_DAYS = 2
PROMOTION_MIN_OBSERVATIONS = 50
PROMOTION_MIN_DAYS = 3
STRONG_POLICY_MIN_OBSERVATIONS = 100
STRONG_POLICY_MIN_DAYS = 5


def contract_metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "directional_minimum": {
            "observations": DIRECTIONAL_MIN_OBSERVATIONS,
            "days": DIRECTIONAL_MIN_DAYS,
            "integrity_coverage": 0.90,
        },
        "promotion_minimum": {
            "observations": PROMOTION_MIN_OBSERVATIONS,
            "days": PROMOTION_MIN_DAYS,
            "integrity_coverage": 0.95,
            "maximum_single_day_share": 0.60,
        },
        "strong_policy_minimum": {
            "observations": STRONG_POLICY_MIN_OBSERVATIONS,
            "days": STRONG_POLICY_MIN_DAYS,
            "market_regime_groups": 2,
        },
    }


def validate_contract_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("q9 contract_version is missing or unsupported")
    evidence = payload.get("evidence_class")
    if evidence is not None:
        EvidenceClass(str(evidence))
