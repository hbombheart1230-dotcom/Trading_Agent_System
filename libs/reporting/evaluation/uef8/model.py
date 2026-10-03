"""UEF-8 normalized output model.

Every dataclass here is comparison-VALIDITY evidence, never a ranking or
performance judgment. No field ever carries a score, rank, delta, winner,
or promotion recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

REPORT_SCHEMA_VERSION = "uef8.fair_comparison.v1"
FAIR_COMPARISON_POLICY_VERSION = "uef8_fair_comparison_policy.v1"

EXPECTED_UEF7_SCHEMA_VERSION = "uef7.alpha_board_normalization.v1"

# The normalized OUTCOME metric set UEF-8 evaluates availability over --
# deliberately excludes sample_count/window_count (accounting dimensions,
# never performance outcomes; see item 12).
OUTCOME_METRICS = (
    "win_rate",
    "avg_net_return_pct",
    "profit_factor",
    "max_drawdown_pct",
    "coverage",
    "avg_mfe_pct",
    "avg_mae_pct",
)

COMPARABLE = "COMPARABLE"
CONDITIONAL = "CONDITIONAL"
NOT_COMPARABLE = "NOT_COMPARABLE"

# One frozen, deterministic reason ordering (item 22) -- comparison_reasons
# is always emitted in this fixed order, never dependent on set/dict
# iteration order.
REASON_ORDER = (
    "DIFFERENT_RESEARCH_QUESTION",
    "DIFFERENT_TARGET_HORIZON",
    "DIFFERENT_EVIDENCE_COHORT",
    "EVIDENCE_COHORT_NOT_AVAILABLE",
    "NO_SHARED_OUTCOME_METRIC",
    "METRIC_AVAILABILITY_MISMATCH",
    "INSUFFICIENT_SAMPLE_ACCOUNTING",
    "POPULATION_RELATION_NOT_PROVEN",
    "SHARED_SOURCE_PROVENANCE",
)

# Any one of these present forces NOT_COMPARABLE regardless of anything
# else (item 21 step 1-2). Never looks at a metric's own performance value.
HARD_BLOCKER_REASONS = frozenset(
    {
        "DIFFERENT_RESEARCH_QUESTION",
        "DIFFERENT_TARGET_HORIZON",
        "DIFFERENT_EVIDENCE_COHORT",
        "EVIDENCE_COHORT_NOT_AVAILABLE",
        "NO_SHARED_OUTCOME_METRIC",
    }
)

# Present (with no hard blocker) forces CONDITIONAL (item 21 step 3).
CONDITIONAL_REASONS = frozenset(
    {
        "METRIC_AVAILABILITY_MISMATCH",
        "INSUFFICIENT_SAMPLE_ACCOUNTING",
        "POPULATION_RELATION_NOT_PROVEN",
        "SHARED_SOURCE_PROVENANCE",
    }
)

assert HARD_BLOCKER_REASONS | CONDITIONAL_REASONS == set(REASON_ORDER)


class UEF8ModelError(Exception):
    """Base class for UEF-8-local model/contract errors."""


@dataclass(frozen=True)
class ComparisonPair:
    comparison_pair_id: str

    left_candidate_id: str
    right_candidate_id: str

    question_id_left: str
    question_id_right: str

    target_horizon_left: str
    target_horizon_right: str

    evidence_cohort_left: Optional[str]
    evidence_cohort_right: Optional[str]

    sample_count_left: Optional[int]
    sample_count_right: Optional[int]

    metrics_available_left: tuple[str, ...]
    metrics_available_right: tuple[str, ...]
    shared_available_metrics: tuple[str, ...]

    population_identity_status_left: str
    population_identity_status_right: str

    shared_source_group_ids: tuple[str, ...]

    comparison_status: str
    comparison_reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "comparison_pair_id": self.comparison_pair_id,
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "question_id_left": self.question_id_left,
            "question_id_right": self.question_id_right,
            "target_horizon_left": self.target_horizon_left,
            "target_horizon_right": self.target_horizon_right,
            "evidence_cohort_left": self.evidence_cohort_left,
            "evidence_cohort_right": self.evidence_cohort_right,
            "sample_count_left": self.sample_count_left,
            "sample_count_right": self.sample_count_right,
            "metrics_available_left": list(self.metrics_available_left),
            "metrics_available_right": list(self.metrics_available_right),
            "shared_available_metrics": list(self.shared_available_metrics),
            "population_identity_status_left": self.population_identity_status_left,
            "population_identity_status_right": self.population_identity_status_right,
            "shared_source_group_ids": list(self.shared_source_group_ids),
            "comparison_status": self.comparison_status,
            "comparison_reasons": list(self.comparison_reasons),
        }


_FIXED_AUTHORITY = {
    "comparable_means_comparison_supported_not_better": True,
    "not_comparable_does_not_mean_bad_strategy": True,
    "conditional_does_not_authorize_ranking": True,
    "no_metric_value_used_to_decide_better": True,
    "ranking_change_authorized": False,
    "strategy_change_authorized": False,
    "production_change_authorized": False,
    "winner_selection_authorized": False,
}


@dataclass(frozen=True)
class FairComparisonSummary:
    candidate_count: int
    pair_count: int
    comparable_count: int
    conditional_count: int
    not_comparable_count: int
    reason_counts: dict
    by_question_id: dict
    by_target_horizon: dict

    def to_dict(self) -> dict:
        return {
            "candidate_count": self.candidate_count,
            "pair_count": self.pair_count,
            "comparable_count": self.comparable_count,
            "conditional_count": self.conditional_count,
            "not_comparable_count": self.not_comparable_count,
            "reason_counts": dict(self.reason_counts),
            "by_question_id": dict(self.by_question_id),
            "by_target_horizon": dict(self.by_target_horizon),
        }


@dataclass(frozen=True)
class FairComparisonRun:
    schema_version: str
    fair_comparison_policy_version: str

    source_uef7_run_id: str
    source_uef7_through_day: str

    candidate_count: int
    candidate_ids: tuple[str, ...]

    pairs: tuple[ComparisonPair, ...]
    summary: FairComparisonSummary

    uef7_normalized_semantic_digest: str
    uef8_implementation_digest: str
    uef8_run_id: str

    authority: dict = field(default_factory=lambda: dict(_FIXED_AUTHORITY))

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fair_comparison_policy_version": self.fair_comparison_policy_version,
            "source_uef7_run_id": self.source_uef7_run_id,
            "source_uef7_through_day": self.source_uef7_through_day,
            "candidate_count": self.candidate_count,
            "candidate_ids": list(self.candidate_ids),
            "pairs": [p.to_dict() for p in self.pairs],
            "summary": self.summary.to_dict(),
            "uef7_normalized_semantic_digest": self.uef7_normalized_semantic_digest,
            "uef8_implementation_digest": self.uef8_implementation_digest,
            "uef8_run_id": self.uef8_run_id,
            "authority": dict(self.authority),
        }


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "FAIR_COMPARISON_POLICY_VERSION",
    "EXPECTED_UEF7_SCHEMA_VERSION",
    "OUTCOME_METRICS",
    "COMPARABLE",
    "CONDITIONAL",
    "NOT_COMPARABLE",
    "REASON_ORDER",
    "HARD_BLOCKER_REASONS",
    "CONDITIONAL_REASONS",
    "UEF8ModelError",
    "ComparisonPair",
    "FairComparisonSummary",
    "FairComparisonRun",
]
