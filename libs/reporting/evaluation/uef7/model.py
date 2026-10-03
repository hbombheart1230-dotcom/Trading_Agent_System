"""UEF-7 normalized output model.

Every dataclass here is a DERIVED VIEW dataclass, never a new canonical
identity or metric authority. No field here overrides, recomputes, or
reinterprets an Alpha Research Board v2 value -- fields that copy a board
value do so verbatim (see ``alpha_board_normalization.py``'s own explicit
equality re-verification).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Sequence

REPORT_SCHEMA_VERSION = "uef7.alpha_board_normalization.v1"

METRIC_AUTHORITY_DERIVED_VIEW = "ALPHA_BOARD_V2_DERIVED_VIEW"

CANONICAL_METRIC_LINK_NOT_PROVEN = "NOT_PROVEN"

POPULATION_DIRECT_PROVEN = "DIRECT_POPULATION_IDENTITY_PROVEN"
POPULATION_NOT_PROVABLE = "NOT_PROVABLE_FROM_ALPHA_BOARD_V2"

INDEPENDENCE_PROVEN_SHARED = "PROVEN_SHARED_POPULATION"
INDEPENDENCE_PROVEN_DISTINCT = "PROVEN_DISTINCT_POPULATION"
INDEPENDENCE_NOT_PROVEN = "INDEPENDENCE_NOT_PROVEN"


class UEF7ModelError(Exception):
    """Base class for UEF-7-local model/contract errors."""


@dataclass(frozen=True)
class SourceReference:
    """One board-row source-provenance citation, copied verbatim from the
    board's own ``source_artifacts`` entry. A provenance STRING/pointer
    only -- never a claim that the exact historical bytes behind ``path``
    are still what they were when the board row was built."""

    source_key: str
    path: Optional[str]
    available: Optional[bool]
    error: Optional[str]

    def to_dict(self) -> dict:
        return {"source_key": self.source_key, "path": self.path, "available": self.available, "error": self.error}


def canonical_source_reference(ref: SourceReference) -> str:
    """The ONE canonical serialization of a full ``SourceReference`` --
    binds ALL FOUR normalized fields (``source_key``, ``path``,
    ``available``, ``error``), never a partial key. Two references that
    agree on ``source_key``/``path`` but disagree on ``available``/``error``
    (e.g. a source that later became unavailable, or a re-observed source
    error) are DIFFERENT full references and must never be treated as
    identical by any grouping or bundle-identity computation. Used as the
    single shared identity authority for source-group membership,
    duplicate-reference detection, and ``source_bundle_id`` -- never a
    separate partial-key definition for any of those three."""

    return json.dumps(ref.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def source_reference_digest(ref: SourceReference) -> str:
    return hashlib.sha256(canonical_source_reference(ref).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceOverlapGroup:
    """Candidate rows that cite the exact SAME full source provenance
    reference (``source_key`` + ``path`` + ``available`` + ``error`` --
    the full canonical ``SourceReference``, never a partial key). Means
    ONLY "these rows reuse the same source provenance" -- never same
    population, duplicate row, invalid candidate, or same hypothesis. Only
    ever emitted for ``candidate_count > 1``."""

    source_group_id: str
    source_key: str
    path: Optional[str]
    available: Optional[bool]
    error: Optional[str]
    candidate_ids: tuple[str, ...]
    candidate_count: int

    def to_dict(self) -> dict:
        return {
            "source_group_id": self.source_group_id,
            "source_key": self.source_key,
            "path": self.path,
            "available": self.available,
            "error": self.error,
            "candidate_ids": list(self.candidate_ids),
            "candidate_count": self.candidate_count,
        }


@dataclass(frozen=True)
class NormalizedCandidateRow:
    # Copied verbatim from Alpha Board v2 -- no UEF-7 reinterpretation.
    question_id: str
    candidate_id: str
    target_horizon: str
    status: str
    operation_status: str
    fixed_validation_status: str
    production_promotion_status: str
    decision: str

    # Structural metric-shape normalization only -- values copied verbatim
    # from the board's own ``net_metrics``; None/missing stays None/missing,
    # 0 is never invented, nothing is recomputed or re-scaled.
    evidence_cohort: Optional[str]
    sample_count: Optional[int]
    window_count: Optional[int]
    win_rate: Optional[float]
    avg_net_return_pct: Optional[float]
    profit_factor: Optional[float]
    max_drawdown_pct: Optional[float]
    coverage: Optional[float]
    avg_mfe_pct: Optional[float]
    avg_mae_pct: Optional[float]

    metric_authority: str
    canonical_metric_link_status: str

    source_references: tuple[SourceReference, ...]
    source_anomalies: tuple[str, ...]
    source_bundle_id: str
    shared_source_group_ids: tuple[str, ...]
    shared_source_candidate_ids: tuple[str, ...]

    population_identity_status: str
    evidence_independence_status: str

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "candidate_id": self.candidate_id,
            "target_horizon": self.target_horizon,
            "status": self.status,
            "operation_status": self.operation_status,
            "fixed_validation_status": self.fixed_validation_status,
            "production_promotion_status": self.production_promotion_status,
            "decision": self.decision,
            "evidence_cohort": self.evidence_cohort,
            "sample_count": self.sample_count,
            "window_count": self.window_count,
            "win_rate": self.win_rate,
            "avg_net_return_pct": self.avg_net_return_pct,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "coverage": self.coverage,
            "avg_mfe_pct": self.avg_mfe_pct,
            "avg_mae_pct": self.avg_mae_pct,
            "metric_authority": self.metric_authority,
            "canonical_metric_link_status": self.canonical_metric_link_status,
            "source_references": [r.to_dict() for r in self.source_references],
            "source_anomalies": list(self.source_anomalies),
            "source_bundle_id": self.source_bundle_id,
            "shared_source_group_ids": list(self.shared_source_group_ids),
            "shared_source_candidate_ids": list(self.shared_source_candidate_ids),
            "population_identity_status": self.population_identity_status,
            "evidence_independence_status": self.evidence_independence_status,
        }


_FIXED_AUTHORITY = {
    "source_overlap_is_not_population_equivalence": True,
    "candidate_rows_are_not_independent_evidence_units": True,
    "population_identity_requires_direct_authority": True,
    "ranking_change_authorized": False,
    "strategy_change_authorized": False,
    "production_change_authorized": False,
}


@dataclass(frozen=True)
class NormalizationSummary:
    candidate_row_count: int
    shared_source_group_count: int
    rows_with_shared_source_count: int
    proven_population_group_count: int
    unresolved_population_candidate_count: int

    def to_dict(self) -> dict:
        return {
            "candidate_row_count": self.candidate_row_count,
            "shared_source_group_count": self.shared_source_group_count,
            "rows_with_shared_source_count": self.rows_with_shared_source_count,
            "proven_population_group_count": self.proven_population_group_count,
            "unresolved_population_candidate_count": self.unresolved_population_candidate_count,
        }


@dataclass(frozen=True)
class NormalizedAlphaBoard:
    schema_version: str
    source_board_schema_version: str
    source_board_contract_version: str
    through_day: str

    candidate_row_count: int
    candidate_ids: tuple[str, ...]

    normalized_rows: tuple[NormalizedCandidateRow, ...]
    source_groups: tuple[SourceOverlapGroup, ...]
    normalization_summary: NormalizationSummary

    source_board_semantic_digest: str
    normalizer_implementation_digest: str
    uef7_run_id: str

    authority: dict = field(default_factory=lambda: dict(_FIXED_AUTHORITY))

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_board_schema_version": self.source_board_schema_version,
            "source_board_contract_version": self.source_board_contract_version,
            "through_day": self.through_day,
            "candidate_row_count": self.candidate_row_count,
            "candidate_ids": list(self.candidate_ids),
            "normalized_rows": [r.to_dict() for r in self.normalized_rows],
            "source_groups": [g.to_dict() for g in self.source_groups],
            "normalization_summary": self.normalization_summary.to_dict(),
            "authority": dict(self.authority),
            "source_board_semantic_digest": self.source_board_semantic_digest,
            "normalizer_implementation_digest": self.normalizer_implementation_digest,
            "uef7_run_id": self.uef7_run_id,
        }


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "METRIC_AUTHORITY_DERIVED_VIEW",
    "CANONICAL_METRIC_LINK_NOT_PROVEN",
    "POPULATION_DIRECT_PROVEN",
    "POPULATION_NOT_PROVABLE",
    "INDEPENDENCE_PROVEN_SHARED",
    "INDEPENDENCE_PROVEN_DISTINCT",
    "INDEPENDENCE_NOT_PROVEN",
    "UEF7ModelError",
    "SourceReference",
    "canonical_source_reference",
    "source_reference_digest",
    "SourceOverlapGroup",
    "NormalizedCandidateRow",
    "NormalizationSummary",
    "NormalizedAlphaBoard",
]
