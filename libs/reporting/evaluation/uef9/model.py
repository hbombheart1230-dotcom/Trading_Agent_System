"""Immutable UEF-9 authority-contract model.

UEF-9 owns only final authority-chain verification.  Candidate facts remain
owned by UEF-7 and comparison-validity facts remain owned by UEF-8.
"""

from __future__ import annotations

from dataclasses import dataclass


REPORT_SCHEMA_VERSION = "uef9.formal_evaluation_authority.v1"
AUTHORITY_CONTRACT_VERSION = "uef9_formal_authority_contract.v1"

VALID = "VALID"
INVALID = "INVALID"


class UEF9AuthorityError(Exception):
    """Raised when a frozen authority-chain invariant is contradicted."""


@dataclass(frozen=True)
class FormalEvaluationAuthority:
    schema_version: str
    authority_contract_version: str
    authority_status: str

    source_uef7_schema_version: str
    source_uef7_run_id: str
    source_uef7_source_board_semantic_digest: str
    verified_uef7_normalized_rows_digest: str

    source_uef8_schema_version: str
    source_uef8_run_id: str
    source_uef8_native_semantic_digest_available: bool
    uef9_derived_uef8_authority_digest: str

    candidate_count: int
    candidate_ids_digest: str
    pair_count: int
    comparison_pair_ids_digest: str
    comparison_status_counts: dict[str, int]
    comparable_reachable_with_current_uef7_schema: bool

    authority_surfaces: dict[str, str]
    prohibitions: dict[str, str]

    uef9_implementation_digest: str
    uef9_run_id: str

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "authority_contract_version": self.authority_contract_version,
            "authority_status": self.authority_status,
            "source_uef7_schema_version": self.source_uef7_schema_version,
            "source_uef7_run_id": self.source_uef7_run_id,
            "source_uef7_source_board_semantic_digest": self.source_uef7_source_board_semantic_digest,
            "verified_uef7_normalized_rows_digest": self.verified_uef7_normalized_rows_digest,
            "source_uef8_schema_version": self.source_uef8_schema_version,
            "source_uef8_run_id": self.source_uef8_run_id,
            "source_uef8_native_semantic_digest_available": self.source_uef8_native_semantic_digest_available,
            "uef9_derived_uef8_authority_digest": self.uef9_derived_uef8_authority_digest,
            "candidate_count": self.candidate_count,
            "candidate_ids_digest": self.candidate_ids_digest,
            "pair_count": self.pair_count,
            "comparison_pair_ids_digest": self.comparison_pair_ids_digest,
            "comparison_status_counts": dict(self.comparison_status_counts),
            "comparable_reachable_with_current_uef7_schema": self.comparable_reachable_with_current_uef7_schema,
            "authority_surfaces": dict(self.authority_surfaces),
            "prohibitions": dict(self.prohibitions),
            "uef9_implementation_digest": self.uef9_implementation_digest,
            "uef9_run_id": self.uef9_run_id,
        }


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "AUTHORITY_CONTRACT_VERSION",
    "VALID",
    "INVALID",
    "UEF9AuthorityError",
    "FormalEvaluationAuthority",
]
