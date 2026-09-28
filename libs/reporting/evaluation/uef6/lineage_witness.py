"""UEF-6B direct-evidence lineage wrapper.

``aggregate_canonical_samples_with_lineage`` calls the frozen UEF-3C
``aggregate_canonical_samples`` EXACTLY ONCE, over the SAME
``CanonicalSampleBatch`` objects the caller would otherwise pass to it
directly, and returns both the frozen, unmodified ``AggregateRecord`` AND
a UEF-6B ``AggregateLineageWitness`` built from those SAME batches.

Contains ZERO PF math, ZERO MDD math, ZERO net-return math, ZERO
strategy-specific (Q10/Q11/Q12/Opening/Alpha Board) branches -- verified
by inspection: this module never imports ``calculate_net_return``/
``calculate_profit_factor``/``calculate_max_drawdown`` and consumes only
``MetricAggregationContext``/``CanonicalSampleBatch``/
``CanonicalAggregationMember``/``AggregateRecord``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)
from libs.reporting.evaluation.canonical.metrics.policy import MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.contracts import ReturnUnit

from .lineage_model import (
    DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE,
    AggregateLineageWitness,
    AggregationWithLineage,
    MemberOccurrence,
    UEF6LineagePopulationMismatchError,
    WITNESS_SCHEMA_VERSION,
)

_IMPLEMENTATION_FILES = ("lineage_model.py", "lineage_witness.py", "lineage_verify.py")


def lineage_implementation_digest() -> str:
    package_dir = Path(__file__).resolve().parent
    parts = []
    for name in _IMPLEMENTATION_FILES:
        p = package_dir / name
        content = p.read_bytes() if p.is_file() else b"ABSENT"
        parts.append(name.encode("utf-8") + b":" + hashlib.sha256(content).hexdigest().encode("ascii"))
    return hashlib.sha256(b"|".join(parts)).hexdigest()


def lineage_status_without_direct_witness() -> str:
    """The ONLY lineage status obtainable without a direct
    ``aggregate_canonical_samples_with_lineage`` call at aggregation time.

    Takes NO arguments -- structurally cannot consult an
    ``AggregateRecord``'s or ``EpisodeRecord``'s day/symbol/hypothesis/
    horizon/counts to infer membership, because no such data ever reaches
    this function at all. This is the fixed, honest answer for "I only
    have UEF-5.2's persisted output -- what is this aggregate's UEF-6B
    lineage status?": always ``DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE``,
    never a heuristically-reconstructed witness."""

    return DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE


def _member_to_occurrence(member: CanonicalAggregationMember) -> MemberOccurrence:
    return MemberOccurrence(
        state=member.state.value,
        evaluation_record_id=member.evaluation_record_id,
        gross_return=member.gross_return,
        return_unit=member.return_unit.value if member.return_unit is not None else None,
        source_cost_semantics=member.source_cost_semantics.value if member.source_cost_semantics is not None else None,
        cost_policy_id=member.cost_policy.policy_id if member.cost_policy is not None else "",
        source_net_return=member.source_net_return,
        observed_timestamp=member.observed_timestamp,
        target_timestamp=member.target_timestamp,
    )


def member_multiset_digest(members: Sequence[CanonicalAggregationMember]) -> str:
    """Order-independent, multiplicity-sensitive digest over every member
    OCCURRENCE (never a set -- ``[A,B]`` and ``[A,B,B]`` MUST digest
    differently). Each occurrence is canonically serialized via
    ``MemberOccurrence.to_dict()`` (no ``repr()``, no ``hash()``, no
    object identity), the resulting canonical JSON strings are sorted
    (fixing a deterministic order regardless of input order), and the
    sorted list is hashed as one JSON array."""

    rows = sorted(
        json.dumps(_member_to_occurrence(m).to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        for m in members
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def context_digest(context: MetricAggregationContext) -> str:
    """Binds the ACTUAL COMPLETE ``MetricAggregationContext`` via its own
    frozen ``to_dict()`` -- never hand-picked fields."""

    payload = json.dumps(context.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_witness_id(
    canonical_aggregate_id: str,
    aggregate_evaluation_subject_id: str,
    aggregate_evaluation_record_id: str,
    context_digest_value: str,
    member_multiset_digest_value: str,
    witness_schema_version: str,
    implementation_digest_value: str,
) -> str:
    payload = json.dumps(
        {
            "canonical_aggregate_id": canonical_aggregate_id,
            "aggregate_evaluation_subject_id": aggregate_evaluation_subject_id,
            "aggregate_evaluation_record_id": aggregate_evaluation_record_id,
            "context_digest": context_digest_value,
            "member_multiset_digest": member_multiset_digest_value,
            "witness_schema_version": witness_schema_version,
            "implementation_digest": implementation_digest_value,
        },
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"UEF6BWITNESS_{digest}"


def _build_witness(context: MetricAggregationContext, batches: Sequence[CanonicalSampleBatch]) -> AggregateLineageWitness:
    all_members: list = []
    for batch in batches:
        all_members.extend(batch.members)

    sample_count = len(all_members)
    evaluated_count = sum(1 for m in all_members if m.state is SampleMemberState.EVALUATED)
    missing_count = sum(1 for m in all_members if m.state is SampleMemberState.MISSING)
    excluded_count = sum(1 for m in all_members if m.state is SampleMemberState.EXCLUDED)

    occurrences = tuple(_member_to_occurrence(m) for m in all_members)
    # Deterministic serialized ordering (item 19): sort occurrences by
    # their own canonical dict encoding, independent of input batch/member
    # order -- semantic multiset unchanged -> identical serialized order.
    occurrences = tuple(sorted(occurrences, key=lambda o: json.dumps(o.to_dict(), sort_keys=True, separators=(",", ":"))))

    identified = [m for m in all_members if m.evaluation_record_id]
    unidentified_count = sample_count - len(identified)
    identified_count = len(identified)
    exact_population_member_identity_proven = unidentified_count == 0

    id_counts: dict = {}
    for m in identified:
        id_counts[m.evaluation_record_id] = id_counts.get(m.evaluation_record_id, 0) + 1
    duplicate_member_ids = tuple(sorted(rid for rid, count in id_counts.items() if count > 1))
    duplicate_member_identity_count = sum(count - 1 for count in id_counts.values() if count > 1)

    mm_digest = member_multiset_digest(all_members)
    ctx_digest = context_digest(context)
    impl_digest = lineage_implementation_digest()
    identity = context.aggregate_identity
    witness_id = compute_witness_id(
        identity.canonical_aggregate_id, identity.evaluation_subject_id, identity.evaluation_record_id,
        ctx_digest, mm_digest, WITNESS_SCHEMA_VERSION, impl_digest,
    )

    return AggregateLineageWitness(
        witness_id=witness_id,
        canonical_aggregate_id=identity.canonical_aggregate_id,
        aggregate_evaluation_subject_id=identity.evaluation_subject_id,
        aggregate_evaluation_record_id=identity.evaluation_record_id,
        horizon_label=context.horizon_label,
        forward_policy_id=context.forward_policy_id,
        cost_policy_id=context.cost_policy_id,
        metric_policy_id=context.metric_policy_id,
        sample_count=sample_count,
        evaluated_count=evaluated_count,
        missing_count=missing_count,
        excluded_count=excluded_count,
        member_occurrences=occurrences,
        member_multiset_digest=mm_digest,
        context_digest=ctx_digest,
        identified_member_count=identified_count,
        unidentified_member_count=unidentified_count,
        exact_population_member_identity_proven=exact_population_member_identity_proven,
        duplicate_member_ids=duplicate_member_ids,
        duplicate_member_identity_count=duplicate_member_identity_count,
        witness_schema_version=WITNESS_SCHEMA_VERSION,
        implementation_digest=impl_digest,
    )


def _cross_check_population(witness: AggregateLineageWitness, aggregate_record) -> None:
    persisted = (aggregate_record.metrics or {}).get("sample_population") or {}
    witness_counts = {
        "sample_count": witness.sample_count,
        "evaluated_count": witness.evaluated_count,
        "missing_count": witness.missing_count,
        "excluded_count": witness.excluded_count,
    }
    for field_name, witness_value in witness_counts.items():
        persisted_value = persisted.get(field_name)
        if witness_value != persisted_value:
            raise UEF6LineagePopulationMismatchError(
                f"witness.{field_name}={witness_value} != AggregateRecord.metrics['sample_population']"
                f"[{field_name!r}]={persisted_value!r} -- the direct-witness member counts and the frozen "
                "aggregator's own persisted population counts disagree. FAIL CLOSED: neither side is trusted "
                "over the other and neither is repaired."
            )


def aggregate_canonical_samples_with_lineage(
    *,
    context: MetricAggregationContext,
    batches: Sequence[CanonicalSampleBatch],
    metric_policy: MetricPolicy,
    input_return_unit: ReturnUnit,
    aggregation_window_start: str,
    aggregation_window_end: str = "",
    excluded_note: str = "",
) -> AggregationWithLineage:
    """Calls frozen ``aggregate_canonical_samples`` EXACTLY ONCE over the
    SAME ``batches`` the caller supplies, and builds a UEF-6B
    ``AggregateLineageWitness`` from those SAME batches -- never a second,
    independently-constructed member list. After the frozen call returns,
    cross-checks the witness's own member-state counts against the frozen
    ``AggregateRecord``'s persisted ``metrics['sample_population']``; a
    mismatch fails closed (``UEF6LineagePopulationMismatchError``), never
    repaired."""

    aggregate_record = aggregate_canonical_samples(
        context=context, batches=batches, metric_policy=metric_policy, input_return_unit=input_return_unit,
        aggregation_window_start=aggregation_window_start, aggregation_window_end=aggregation_window_end,
        excluded_note=excluded_note,
    )
    witness = _build_witness(context, batches)
    _cross_check_population(witness, aggregate_record)
    return AggregationWithLineage(aggregate_record=aggregate_record, witness=witness)
