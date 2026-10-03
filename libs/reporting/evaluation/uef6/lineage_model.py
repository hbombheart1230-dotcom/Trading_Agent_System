"""UEF-6B-local sidecar model: ``AggregateLineageWitness`` and related types.

Binds to the canonical aggregate using ONLY existing UEF-1/UEF-3A identity
(``canonical_aggregate_id`` / ``evaluation_subject_id`` /
``evaluation_record_id`` via ``AggregateIdentity``, and
``MetricAggregationContext``'s own policy-id fields) -- no new aggregate
identity authority is introduced here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

WITNESS_SCHEMA_VERSION = "uef6b_lineage_witness.v1"

# The ONLY lineage status obtainable when no direct
# aggregate_canonical_samples_with_lineage() call happened at aggregation
# time -- i.e. when all that is available is an already-persisted
# AggregateRecord and/or an EpisodeRecord population. This exact string is
# the fixed, non-heuristic answer; there is deliberately no function
# anywhere in this package that accepts (AggregateRecord, EpisodeRecord[])
# plus correlating fields (day/symbol/hypothesis/horizon/counts) and
# attempts to produce a witness from them -- see
# ``lineage_witness.lineage_status_without_direct_witness()``.
DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE = "DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE"
DIRECT_WITNESS_REQUIRED = "DIRECT_WITNESS_REQUIRED"


class UEF6LineageError(Exception):
    """Base class for UEF-6B-local integrity errors."""


class UEF6LineagePopulationMismatchError(UEF6LineageError):
    """Raised when the witness's own member-state counts (sample/evaluated/
    missing/excluded) do not exactly match the frozen ``AggregateRecord``'s
    persisted ``metrics.sample_population`` counts. Never repaired, never
    trusted one side over the other -- both sides are read directly from
    what the frozen aggregator actually produced and what the witness
    actually observed; a mismatch means something in the caller's own
    plumbing let the two diverge, which UEF-6B refuses to paper over."""


@dataclass(frozen=True)
class MemberOccurrence:
    """One canonical, ``repr()``/``hash()``/object-identity-free
    serialization of ONE ``CanonicalAggregationMember`` occurrence --
    preserves every occurrence, never deduplicated."""

    state: str
    evaluation_record_id: str
    gross_return: Optional[float]
    return_unit: Optional[str]
    source_cost_semantics: Optional[str]
    cost_policy_id: str
    source_net_return: Optional[float]
    observed_timestamp: Optional[int]
    target_timestamp: Optional[int]

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "evaluation_record_id": self.evaluation_record_id,
            "gross_return": self.gross_return,
            "return_unit": self.return_unit,
            "source_cost_semantics": self.source_cost_semantics,
            "cost_policy_id": self.cost_policy_id,
            "source_net_return": self.source_net_return,
            "observed_timestamp": self.observed_timestamp,
            "target_timestamp": self.target_timestamp,
        }


@dataclass(frozen=True)
class AggregateLineageWitness:
    """UEF-6B's direct-evidence sidecar for ONE canonical aggregate. Only
    ever produced by ``lineage_witness.aggregate_canonical_samples_with_lineage``
    from the ACTUAL ``CanonicalSampleBatch`` members supplied to that one
    aggregation call -- never reconstructed from a persisted
    ``AggregateRecord`` alone."""

    witness_id: str
    canonical_aggregate_id: str
    aggregate_evaluation_subject_id: str
    aggregate_evaluation_record_id: str

    horizon_label: str
    forward_policy_id: str
    cost_policy_id: str
    metric_policy_id: str

    sample_count: int
    evaluated_count: int
    missing_count: int
    excluded_count: int

    member_occurrences: Sequence[MemberOccurrence]
    member_multiset_digest: str
    context_digest: str

    identified_member_count: int
    unidentified_member_count: int
    exact_population_member_identity_proven: bool

    duplicate_member_ids: Sequence[str]
    duplicate_member_identity_count: int  # total excess occurrences across all duplicated identities

    witness_schema_version: str = WITNESS_SCHEMA_VERSION
    implementation_digest: str = ""

    def to_dict(self) -> dict:
        return {
            "witness_id": self.witness_id,
            "canonical_aggregate_id": self.canonical_aggregate_id,
            "aggregate_evaluation_subject_id": self.aggregate_evaluation_subject_id,
            "aggregate_evaluation_record_id": self.aggregate_evaluation_record_id,
            "horizon_label": self.horizon_label,
            "forward_policy_id": self.forward_policy_id,
            "cost_policy_id": self.cost_policy_id,
            "metric_policy_id": self.metric_policy_id,
            "sample_count": self.sample_count,
            "evaluated_count": self.evaluated_count,
            "missing_count": self.missing_count,
            "excluded_count": self.excluded_count,
            "member_occurrences": [m.to_dict() for m in self.member_occurrences],
            "member_multiset_digest": self.member_multiset_digest,
            "context_digest": self.context_digest,
            "identified_member_count": self.identified_member_count,
            "unidentified_member_count": self.unidentified_member_count,
            "exact_population_member_identity_proven": self.exact_population_member_identity_proven,
            "duplicate_member_ids": list(self.duplicate_member_ids),
            "duplicate_member_identity_count": self.duplicate_member_identity_count,
            "witness_schema_version": self.witness_schema_version,
            "implementation_digest": self.implementation_digest,
        }


@dataclass(frozen=True)
class AggregationWithLineage:
    """The wrapper's return value: the frozen aggregator's own
    ``AggregateRecord`` (untouched, unmodified) plus UEF-6B's sidecar
    witness for it."""

    aggregate_record: object  # AggregateRecord -- typed loosely to avoid a hard import cycle in this module
    witness: AggregateLineageWitness


@dataclass(frozen=True)
class EpisodeVerificationResult:
    """Result of ``lineage_verify.verify_witness_against_episode_population``.
    Matches ONLY via exact ``evaluation_record_id`` -- never symbol/date/
    hypothesis/count."""

    evaluated_member_count: int
    evaluated_episode_match_count: int
    evaluated_episode_missing_count: int
    exact_evaluated_episode_membership_proven: bool
    matched_evaluation_record_ids: Sequence[str]
    missing_evaluation_record_ids: Sequence[str]

    def to_dict(self) -> dict:
        return {
            "evaluated_member_count": self.evaluated_member_count,
            "evaluated_episode_match_count": self.evaluated_episode_match_count,
            "evaluated_episode_missing_count": self.evaluated_episode_missing_count,
            "exact_evaluated_episode_membership_proven": self.exact_evaluated_episode_membership_proven,
            "matched_evaluation_record_ids": list(self.matched_evaluation_record_ids),
            "missing_evaluation_record_ids": list(self.missing_evaluation_record_ids),
        }
