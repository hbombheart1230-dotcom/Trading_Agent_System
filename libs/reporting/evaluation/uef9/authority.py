"""Fail-closed binding verifier for frozen UEF-7 and UEF-8 authority."""

from __future__ import annotations

import itertools
from collections import Counter
from typing import Any, Mapping

from libs.reporting.evaluation.uef7.model import REPORT_SCHEMA_VERSION as UEF7_SCHEMA_VERSION
from libs.reporting.evaluation.uef7.run_identity import compute_uef7_run_id
from libs.reporting.evaluation.uef8.model import (
    COMPARABLE,
    CONDITIONAL,
    NOT_COMPARABLE,
    REPORT_SCHEMA_VERSION as UEF8_SCHEMA_VERSION,
)
from libs.reporting.evaluation.uef8.run_identity import uef7_normalized_rows_semantic_digest
from libs.reporting.evaluation.uef8.run_identity import compute_uef8_run_id

from .model import (
    AUTHORITY_CONTRACT_VERSION,
    REPORT_SCHEMA_VERSION,
    VALID,
    FormalEvaluationAuthority,
    UEF9AuthorityError,
)
from .run_identity import (
    canonical_uef8_authority_digest,
    canonical_string_sequence_digest,
    compute_uef9_run_id,
)


_VALID_COMPARISON_STATUSES = frozenset((COMPARABLE, CONDITIONAL, NOT_COMPARABLE))

# Neither UEF-7 nor UEF-8's own frozen output carries a single exported
# "COMPARABLE is reachable" capability flag (adding one would mean
# modifying already-frozen UEF-7/UEF-8 files, which this phase must not
# do) -- so this is UEF-9's own schema-contract-level declaration, gated
# on the EXACT frozen schema version strings this module independently
# validates (UEF7_SCHEMA_VERSION/UEF8_SCHEMA_VERSION, checked in
# _validate_uef7/_validate_uef8_schema_and_binding before this constant is
# ever consulted). A future schema version bump is rejected at the schema
# check itself, never silently reinterpreted through this flag -- so this
# is never a "hidden second fair-comparison engine," only a frozen
# capability declaration bound to a specific, already-verified schema
# pair.
_CURRENT_SCHEMA_COMPARABLE_REACHABLE = False


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _fail(message: str) -> None:
    raise UEF9AuthorityError(message)


def _unique_ids(values: list[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        _fail(f"duplicate {label}: {sorted(key for key, count in Counter(values).items() if count > 1)}")


def _validate_uef7(uef7: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str], str]:
    if uef7.get("schema_version") != UEF7_SCHEMA_VERSION:
        _fail(f"wrong UEF-7 schema: {uef7.get('schema_version')!r}")
    rows = [_mapping(row) for row in list(uef7.get("normalized_rows") or [])]
    if uef7.get("candidate_row_count") != len(rows):
        _fail("UEF-7 candidate_row_count mismatch")
    candidate_ids = [str(row.get("candidate_id") or "") for row in rows]
    if any(not candidate_id for candidate_id in candidate_ids):
        _fail("UEF-7 candidate_id missing")
    _unique_ids(candidate_ids, label="UEF-7 candidate_id")
    if list(uef7.get("candidate_ids") or []) != candidate_ids:
        _fail("UEF-7 candidate_ids disagree with normalized rows")
    expected_run_id = compute_uef7_run_id(
        source_board_semantic_digest=str(uef7.get("source_board_semantic_digest") or ""),
        normalizer_implementation_digest_value=str(uef7.get("normalizer_implementation_digest") or ""),
        normalization_schema_version=UEF7_SCHEMA_VERSION,
    )
    if str(uef7.get("uef7_run_id") or "") != expected_run_id:
        _fail("UEF-7 run id does not match frozen UEF-7 identity")
    return rows, candidate_ids, uef7_normalized_rows_semantic_digest(rows)


def _validate_uef8_schema_and_binding(
    uef8: Mapping[str, Any], *, source_uef7_run_id: str, normalized_rows_digest: str, source_uef7_through_day: str
) -> None:
    if uef8.get("schema_version") != UEF8_SCHEMA_VERSION:
        _fail(f"wrong UEF-8 schema: {uef8.get('schema_version')!r}")
    if str(uef8.get("source_uef7_run_id") or "") != source_uef7_run_id:
        _fail("UEF-8 source_uef7_run_id mismatch")
    if str(uef8.get("uef7_normalized_semantic_digest") or "") != normalized_rows_digest:
        _fail("UEF-8 uef7_normalized_semantic_digest mismatch")
    if str(uef8.get("source_uef7_through_day") or "") != source_uef7_through_day:
        _fail("UEF-8 source_uef7_through_day mismatch")
    expected_run_id = compute_uef8_run_id(
        source_uef7_run_id=source_uef7_run_id,
        uef7_normalized_semantic_digest=normalized_rows_digest,
        uef8_implementation_digest_value=str(uef8.get("uef8_implementation_digest") or ""),
        schema_version=UEF8_SCHEMA_VERSION,
        fair_comparison_policy_version=str(uef8.get("fair_comparison_policy_version") or ""),
    )
    if str(uef8.get("uef8_run_id") or "") != expected_run_id:
        _fail("UEF-8 run id does not match frozen UEF-8 identity")


def _validate_pair_universe(uef8: Mapping[str, Any], candidate_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    if uef8.get("candidate_count") != len(candidate_ids):
        _fail("UEF-8 candidate_count mismatch")
    uef8_ids = [str(value or "") for value in list(uef8.get("candidate_ids") or [])]
    _unique_ids(uef8_ids, label="UEF-8 candidate_id")
    if set(uef8_ids) != set(candidate_ids) or len(uef8_ids) != len(candidate_ids):
        _fail("UEF-7/UEF-8 candidate universe mismatch")

    pairs = [_mapping(pair) for pair in list(uef8.get("pairs") or [])]
    expected_pairs = {tuple(pair) for pair in itertools.combinations(sorted(candidate_ids), 2)}
    expected_count = len(expected_pairs)
    if len(pairs) != expected_count:
        _fail("UEF-8 pair count does not match candidate universe")

    actual_pairs: list[tuple[str, str]] = []
    pair_ids: list[str] = []
    statuses: list[str] = []
    candidate_set = set(candidate_ids)
    for pair in pairs:
        left = str(pair.get("left_candidate_id") or "")
        right = str(pair.get("right_candidate_id") or "")
        if left not in candidate_set or right not in candidate_set:
            _fail("UEF-8 pair references unknown candidate")
        if left == right:
            _fail("UEF-8 self-pair")
        actual_pairs.append(tuple(sorted((left, right))))
        pair_id = str(pair.get("comparison_pair_id") or "")
        if not pair_id:
            _fail("UEF-8 comparison_pair_id missing")
        pair_ids.append(pair_id)
        status = str(pair.get("comparison_status") or "")
        if status not in _VALID_COMPARISON_STATUSES:
            _fail(f"unknown UEF-8 comparison status: {status!r}")
        statuses.append(status)

    _unique_ids(pair_ids, label="UEF-8 comparison_pair_id")
    if len(set(actual_pairs)) != expected_count:
        _fail("duplicate semantic UEF-8 pair")
    if set(actual_pairs) != expected_pairs:
        _fail("UEF-8 semantic pair universe mismatch")

    summary = _mapping(uef8.get("summary"))
    if summary.get("pair_count") != expected_count:
        _fail("UEF-8 summary pair_count mismatch")
    counts = {status: statuses.count(status) for status in (COMPARABLE, CONDITIONAL, NOT_COMPARABLE)}
    if expected_count != sum(counts.values()):
        _fail("UEF-8 status-count conservation failure")
    for status, count in counts.items():
        if summary.get(f"{status.lower()}_count") != count:
            _fail(f"UEF-8 summary {status} count mismatch")
    if not _CURRENT_SCHEMA_COMPARABLE_REACHABLE and counts[COMPARABLE] != 0:
        _fail("current UEF-7 schema declares COMPARABLE unreachable")
    return pairs, counts, pair_ids


def verify_formal_evaluation_authority(
    uef7: Mapping[str, Any], *, uef8: Mapping[str, Any], uef9_implementation_digest_value: str
) -> FormalEvaluationAuthority:
    """Verify upstream authority linkage and return a valid final manifest.

    The function never returns an ``INVALID`` manifest: any contradiction
    raises ``UEF9AuthorityError`` so callers cannot treat a partial result as
    authoritative.
    """

    rows, candidate_ids, normalized_rows_digest = _validate_uef7(uef7)
    source_uef7_run_id = str(uef7.get("uef7_run_id") or "")
    source_uef7_through_day = str(uef7.get("through_day") or "")
    if not source_uef7_run_id:
        _fail("UEF-7 run id missing")
    _validate_uef8_schema_and_binding(
        uef8,
        source_uef7_run_id=source_uef7_run_id,
        normalized_rows_digest=normalized_rows_digest,
        source_uef7_through_day=source_uef7_through_day,
    )
    _pairs, status_counts, pair_ids = _validate_pair_universe(uef8, candidate_ids)

    candidate_ids_digest = canonical_string_sequence_digest(candidate_ids)
    comparison_pair_ids_digest = canonical_string_sequence_digest(pair_ids)
    # UEF-8 v1 exposes no native semantic-digest field. This is explicitly
    # a UEF-9 verifier digest over its supplied frozen authority object.
    uef8_authority_digest = canonical_uef8_authority_digest(_mapping(uef8))
    source_uef8_run_id = str(uef8.get("uef8_run_id") or "")
    if not source_uef8_run_id:
        _fail("UEF-8 run id missing")
    run_id = compute_uef9_run_id(
        source_uef7_run_id=source_uef7_run_id,
        verified_uef7_normalized_rows_digest=normalized_rows_digest,
        source_uef8_run_id=source_uef8_run_id,
        uef9_derived_uef8_authority_digest=uef8_authority_digest,
        candidate_ids_digest=candidate_ids_digest,
        comparison_pair_ids_digest=comparison_pair_ids_digest,
        uef9_implementation_digest_value=uef9_implementation_digest_value,
        schema_version=REPORT_SCHEMA_VERSION,
        authority_contract_version=AUTHORITY_CONTRACT_VERSION,
    )
    return FormalEvaluationAuthority(
        schema_version=REPORT_SCHEMA_VERSION,
        authority_contract_version=AUTHORITY_CONTRACT_VERSION,
        authority_status=VALID,
        source_uef7_schema_version=UEF7_SCHEMA_VERSION,
        source_uef7_run_id=source_uef7_run_id,
        source_uef7_source_board_semantic_digest=str(uef7.get("source_board_semantic_digest") or ""),
        verified_uef7_normalized_rows_digest=normalized_rows_digest,
        source_uef8_schema_version=UEF8_SCHEMA_VERSION,
        source_uef8_run_id=source_uef8_run_id,
        source_uef8_native_semantic_digest_available=False,
        uef9_derived_uef8_authority_digest=uef8_authority_digest,
        candidate_count=len(candidate_ids),
        candidate_ids_digest=candidate_ids_digest,
        pair_count=len(pair_ids),
        comparison_pair_ids_digest=comparison_pair_ids_digest,
        comparison_status_counts=status_counts,
        comparable_reachable_with_current_uef7_schema=_CURRENT_SCHEMA_COMPARABLE_REACHABLE,
        authority_surfaces={
            "candidate_evaluation_authority": "UEF-7",
            "pairwise_comparison_authority": "UEF-8",
            "final_authority_binding": "UEF-9",
        },
        prohibitions={
            "ranking_authority": "NONE",
            "promotion_authority": "NONE",
            "trading_execution_authority": "NONE",
        },
        uef9_implementation_digest=uef9_implementation_digest_value,
        uef9_run_id=run_id,
    )


__all__ = ["UEF9AuthorityError", "verify_formal_evaluation_authority"]
