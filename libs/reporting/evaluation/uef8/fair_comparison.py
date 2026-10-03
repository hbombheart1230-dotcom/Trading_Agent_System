"""UEF-8 pure fair-comparison validator over an already-normalized UEF-7
Alpha Board payload.

Read-only: never recalculates UEF-7's own source groups, source bundle
ids, population statuses, or normalized metrics -- consumes them exactly
as UEF-7 provides them. Never reopens raw Alpha Board sources, Q
artifacts, or historical research reports.

Central distinction this module enforces in code (never only in prose):
comparison VALIDITY is not comparison RESULT. No metric performance value
is ever used to decide whether one candidate is "better" than another.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from typing import Any, Mapping, Sequence

from .model import (
    CONDITIONAL,
    COMPARABLE,
    EXPECTED_UEF7_SCHEMA_VERSION,
    FAIR_COMPARISON_POLICY_VERSION,
    HARD_BLOCKER_REASONS,
    NOT_COMPARABLE,
    OUTCOME_METRICS,
    REASON_ORDER,
    REPORT_SCHEMA_VERSION,
    ComparisonPair,
    FairComparisonRun,
    FairComparisonSummary,
)
from .run_identity import compute_uef8_run_id, uef7_normalized_rows_semantic_digest


class UEF8FairComparisonError(Exception):
    """Base class for UEF-8-local errors."""


class UEF8InputContractError(UEF8FairComparisonError):
    """Raised when the supplied UEF-7 normalized board does not satisfy
    UEF-7's own published structural/authority contract. UEF-8 never
    analyzes a structurally invalid or un-trustable UEF-7 input."""


class UEF8PairIdentityCollisionError(UEF8FairComparisonError):
    """Raised if two semantically DIFFERENT candidate pairs would ever
    receive the same ``comparison_pair_id``, or if the number of unique
    pair ids / unique canonical pair tuples ever disagrees with the
    expected pair count. Fails closed -- never silently overwrites,
    collapses, or keeps a first/last-seen pair."""


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _validate_uef7_input(board: Mapping[str, Any]) -> None:
    schema_version = board.get("schema_version")
    if schema_version != EXPECTED_UEF7_SCHEMA_VERSION:
        raise UEF8InputContractError(f"schema_version={schema_version!r} != {EXPECTED_UEF7_SCHEMA_VERSION!r}")

    rows = list(board.get("normalized_rows") or [])
    declared_count = board.get("candidate_row_count")
    if declared_count != len(rows):
        raise UEF8InputContractError(f"candidate_row_count={declared_count!r} != len(normalized_rows)={len(rows)!r}")

    row_ids = [str(_mapping(row).get("candidate_id")) for row in rows]
    if len(set(row_ids)) != len(row_ids):
        duplicates = sorted({cid for cid in row_ids if row_ids.count(cid) > 1})
        raise UEF8InputContractError(f"duplicate candidate_id(s) in normalized_rows: {duplicates}")

    declared_ids = list(board.get("candidate_ids") or [])
    if declared_ids != row_ids:
        raise UEF8InputContractError(
            f"board.candidate_ids={declared_ids!r} disagrees with normalized_rows[].candidate_id order={row_ids!r}"
        )

    authority = _mapping(board.get("authority"))
    required_false_flags = ("ranking_change_authorized", "strategy_change_authorized", "production_change_authorized")
    for flag in required_false_flags:
        if flag not in authority:
            raise UEF8InputContractError(f"board.authority is missing required flag {flag!r}")
        if authority[flag] is not False:
            raise UEF8InputContractError(f"board.authority[{flag!r}]={authority[flag]!r} -- UEF-7 must declare this False")


def _metric_availability(row: Mapping[str, Any]) -> frozenset:
    return frozenset(name for name in OUTCOME_METRICS if row.get(name) is not None)


def _canonical_pair_id(left_id: str, right_id: str) -> str:
    """Pair Identity Collision Bounded Fix: NEVER delimiter-concatenation
    (``f"{left}__{right}"`` collides -- e.g. ``("A", "B__C")`` and
    ``("A__B", "C")`` both produced ``UEF8PAIR_A__B__C``). Binds the
    canonical ORDERED pair as a structured payload, hashed -- structurally
    unambiguous regardless of what characters either candidate_id
    contains (delimiters, unicode, whitespace, anything). Sorts its own
    two inputs internally (defense in depth on top of the caller already
    passing a canonically-ordered pair), so ``pair_id(A, B) == pair_id(B,
    A)`` holds unconditionally, for any call order."""

    ordered_left, ordered_right = sorted((left_id, right_id))
    payload = json.dumps(
        {"left_candidate_id": ordered_left, "right_candidate_id": ordered_right},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"UEF8PAIR_{digest}"


def _evaluate_pair(left: Mapping[str, Any], right: Mapping[str, Any]) -> ComparisonPair:
    left_id, right_id = str(left.get("candidate_id")), str(right.get("candidate_id"))
    reasons: set = set()

    # --- hard scope dimensions (never look at metric performance values) ---
    if left.get("question_id") != right.get("question_id"):
        reasons.add("DIFFERENT_RESEARCH_QUESTION")
    if left.get("target_horizon") != right.get("target_horizon"):
        reasons.add("DIFFERENT_TARGET_HORIZON")

    cohort_left, cohort_right = left.get("evidence_cohort"), right.get("evidence_cohort")
    if cohort_left is None or cohort_right is None:
        reasons.add("EVIDENCE_COHORT_NOT_AVAILABLE")
    elif cohort_left != cohort_right:
        reasons.add("DIFFERENT_EVIDENCE_COHORT")

    avail_left = _metric_availability(left)
    avail_right = _metric_availability(right)
    shared = avail_left & avail_right
    if not shared:
        reasons.add("NO_SHARED_OUTCOME_METRIC")
    elif avail_left != avail_right:
        reasons.add("METRIC_AVAILABILITY_MISMATCH")

    sample_left, sample_right = left.get("sample_count"), right.get("sample_count")
    if not sample_left or not sample_right:
        reasons.add("INSUFFICIENT_SAMPLE_ACCOUNTING")

    pop_left = left.get("population_identity_status")
    pop_right = right.get("population_identity_status")
    # Population Relation Authority Bounded Fix: individual population
    # identity proof (UEF-7's own row-level population_identity_status)
    # does NOT establish the RELATION between two candidates' populations
    # -- two independently-proven populations could still be the same
    # population, a subset, or genuinely distinct, and nothing in either
    # row alone answers that. UEF-8 never infers a pair relation merely
    # because both sides independently report
    # DIRECT_POPULATION_IDENTITY_PROVEN.
    #
    # The frozen uef7.alpha_board_normalization.v1 schema exposes NO field
    # equivalent to a population id / canonical population id / pairwise
    # population relation whatsoever (inspected: NormalizedCandidateRow
    # carries only its OWN population_identity_status, never a relation to
    # any other row). Therefore, under the CURRENT schema,
    # POPULATION_RELATION_NOT_PROVEN is unconditional -- a schema-contract
    # property, not a today's-real-data observation. This makes COMPARABLE
    # structurally unreachable for ANY current valid UEF-7 input (real or
    # synthetic), while remaining a reserved UEF-8 status for a future
    # frozen UEF-7 schema extension that supplies explicit pairwise
    # population-relation authority -- UEF-8 never invents that authority
    # itself.
    reasons.add("POPULATION_RELATION_NOT_PROVEN")

    shared_group_ids = tuple(sorted(set(left.get("shared_source_group_ids") or ()) & set(right.get("shared_source_group_ids") or ())))
    if shared_group_ids:
        reasons.add("SHARED_SOURCE_PROVENANCE")

    ordered_reasons = tuple(r for r in REASON_ORDER if r in reasons)
    if any(r in HARD_BLOCKER_REASONS for r in ordered_reasons):
        status = NOT_COMPARABLE
    elif ordered_reasons:
        status = CONDITIONAL
    else:
        status = COMPARABLE

    return ComparisonPair(
        comparison_pair_id=_canonical_pair_id(left_id, right_id),
        left_candidate_id=left_id,
        right_candidate_id=right_id,
        question_id_left=str(left.get("question_id") or ""),
        question_id_right=str(right.get("question_id") or ""),
        target_horizon_left=str(left.get("target_horizon") or ""),
        target_horizon_right=str(right.get("target_horizon") or ""),
        evidence_cohort_left=cohort_left,
        evidence_cohort_right=cohort_right,
        sample_count_left=sample_left,
        sample_count_right=sample_right,
        metrics_available_left=tuple(sorted(avail_left)),
        metrics_available_right=tuple(sorted(avail_right)),
        shared_available_metrics=tuple(sorted(shared)),
        population_identity_status_left=str(pop_left or ""),
        population_identity_status_right=str(pop_right or ""),
        shared_source_group_ids=shared_group_ids,
        comparison_status=status,
        comparison_reasons=ordered_reasons,
    )


def _validate_pair_identity_uniqueness(pairs: Sequence[ComparisonPair], *, expected_pair_count: int) -> None:
    """Pair Identity Collision Bounded Fix items 5-7: fails closed unless
    unique comparison_pair_ids AND unique canonical (left, right) candidate
    tuples both exactly equal the expected pair count. Never silently
    overwrites, collapses, or keeps a first/last-seen pair on collision."""

    pair_ids = [p.comparison_pair_id for p in pairs]
    pair_tuples = [(p.left_candidate_id, p.right_candidate_id) for p in pairs]

    if len(pair_ids) != expected_pair_count:
        raise UEF8PairIdentityCollisionError(f"len(pairs)={len(pair_ids)} != expected_pair_count={expected_pair_count}")
    if len(set(pair_ids)) != expected_pair_count:
        duplicates = sorted({pid for pid in pair_ids if pair_ids.count(pid) > 1})
        raise UEF8PairIdentityCollisionError(
            f"comparison_pair_id collision(s) detected: {len(pair_ids)} pairs produced only "
            f"{len(set(pair_ids))} unique ids -- duplicate ids: {duplicates}"
        )
    if len(set(pair_tuples)) != expected_pair_count:
        duplicates = sorted({t for t in pair_tuples if pair_tuples.count(t) > 1})
        raise UEF8PairIdentityCollisionError(
            f"canonical (left, right) candidate pair tuple collision(s) detected: {len(pair_tuples)} "
            f"pairs produced only {len(set(pair_tuples))} unique tuples -- duplicates: {duplicates}"
        )


def _build_summary(candidate_count: int, pairs: Sequence[ComparisonPair]) -> FairComparisonSummary:
    reason_counts: dict = {name: 0 for name in REASON_ORDER}
    by_question: dict = {}
    by_horizon: dict = {}
    comparable = conditional = not_comparable = 0

    for pair in pairs:
        if pair.comparison_status == COMPARABLE:
            comparable += 1
        elif pair.comparison_status == CONDITIONAL:
            conditional += 1
        else:
            not_comparable += 1
        for reason in pair.comparison_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        question_key = pair.question_id_left if pair.question_id_left == pair.question_id_right else "MIXED"
        bucket = by_question.setdefault(question_key, {COMPARABLE: 0, CONDITIONAL: 0, NOT_COMPARABLE: 0})
        bucket[pair.comparison_status] += 1

        horizon_key = pair.target_horizon_left if pair.target_horizon_left == pair.target_horizon_right else "MIXED"
        bucket = by_horizon.setdefault(horizon_key, {COMPARABLE: 0, CONDITIONAL: 0, NOT_COMPARABLE: 0})
        bucket[pair.comparison_status] += 1

    return FairComparisonSummary(
        candidate_count=candidate_count,
        pair_count=len(pairs),
        comparable_count=comparable,
        conditional_count=conditional,
        not_comparable_count=not_comparable,
        reason_counts=reason_counts,
        by_question_id=by_question,
        by_target_horizon=by_horizon,
    )


def analyze_fair_comparisons(board: Mapping[str, Any], *, uef8_implementation_digest_value: str) -> FairComparisonRun:
    """Pure fair-comparison analysis over an already-normalized UEF-7 Alpha
    Board payload (from ``normalize_alpha_board().to_dict()`` -- never
    recalculated, never reopened at the raw-source level). Fails closed
    (``UEF8InputContractError``) on a structurally invalid or un-trustable
    UEF-7 input."""

    _validate_uef7_input(board)

    rows = list(board.get("normalized_rows") or [])
    candidate_ids = [str(_mapping(r).get("candidate_id")) for r in rows]
    rows_by_id = {str(_mapping(r).get("candidate_id")): _mapping(r) for r in rows}

    pairs = []
    for a, b in itertools.combinations(sorted(candidate_ids), 2):
        pairs.append(_evaluate_pair(rows_by_id[a], rows_by_id[b]))
    pairs.sort(key=lambda p: (p.left_candidate_id, p.right_candidate_id))

    expected_pair_count = len(candidate_ids) * (len(candidate_ids) - 1) // 2
    _validate_pair_identity_uniqueness(pairs, expected_pair_count=expected_pair_count)

    summary = _build_summary(len(rows), pairs)

    uef7_digest = uef7_normalized_rows_semantic_digest(rows)
    uef8_run_id = compute_uef8_run_id(
        source_uef7_run_id=str(board.get("uef7_run_id") or ""),
        uef7_normalized_semantic_digest=uef7_digest,
        uef8_implementation_digest_value=uef8_implementation_digest_value,
        schema_version=REPORT_SCHEMA_VERSION,
        fair_comparison_policy_version=FAIR_COMPARISON_POLICY_VERSION,
    )

    return FairComparisonRun(
        schema_version=REPORT_SCHEMA_VERSION,
        fair_comparison_policy_version=FAIR_COMPARISON_POLICY_VERSION,
        source_uef7_run_id=str(board.get("uef7_run_id") or ""),
        source_uef7_through_day=str(board.get("through_day") or ""),
        candidate_count=len(rows),
        candidate_ids=tuple(candidate_ids),
        pairs=tuple(pairs),
        summary=summary,
        uef7_normalized_semantic_digest=uef7_digest,
        uef8_implementation_digest=uef8_implementation_digest_value,
        uef8_run_id=uef8_run_id,
    )


__all__ = [
    "UEF8FairComparisonError",
    "UEF8InputContractError",
    "UEF8PairIdentityCollisionError",
    "analyze_fair_comparisons",
]
