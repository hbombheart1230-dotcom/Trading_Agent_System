"""UEF-6C historical lineage coverage aggregation.

Pure functions over already-captured ``AggregateLineageWitness`` objects,
already-loaded ``EpisodeRecord``s, and the frozen pipeline's own persisted
``(AggregateRecord, meta)`` tuples. No filesystem access, no mutation of
any input, no heuristic membership inference -- every mapping here is via
exact existing identity (``evaluation_record_id`` / ``canonical_event_id``
/ ``canonical_aggregate_id``) only.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from .lineage_model import AggregateLineageWitness
from .lineage_verify import verify_witness_against_episode_population


class UEF6CoverageError(Exception):
    """Base class for UEF-6C lineage-coverage-local integrity errors."""


class UEF6AggregateIdentityConsistencyError(UEF6CoverageError):
    """Raised when a persisted ``AggregateRecord``'s own ``identity`` field
    disagrees with the aggregate identity carried inside its own
    ``metrics['context']['aggregate_identity']`` (both are, by the frozen
    ``aggregate_canonical_samples`` construction, meant to originate from
    the exact same ``MetricAggregationContext.aggregate_identity`` object --
    disagreement means the persisted record is internally inconsistent).
    FAIL CLOSED: a match key is never built from contradictory identities."""


# ---------------------------------------------------------------------------
# Witness <-> persisted-aggregate accounting (items 10-16, Final Audit
# items C/11-16) -- FULL semantic match key, multiset (occurrence-
# preserving) accounting. Never matches on evaluation_record_id alone:
# two persisted aggregates can legitimately share evaluation_record_id
# while differing in aggregation context (different horizon/cost/metric
# policy), and must never be treated as interchangeable for coverage
# purposes.
# ---------------------------------------------------------------------------


def _canonical_context_digest(context: Mapping) -> str:
    """Same canonicalization ``lineage_witness.context_digest`` uses over a
    live ``MetricAggregationContext.to_dict()`` -- applied here to the
    PERSISTED ``AggregateRecord.metrics['context']`` dict directly (which,
    for a legitimately-produced record, IS that exact ``to_dict()`` output,
    since ``aggregate_canonical_samples`` writes ``context.to_dict()``
    verbatim into ``metrics['context']``). This makes a witness's own
    ``context_digest`` and a persisted aggregate's derived digest directly
    comparable for the SAME real aggregation."""

    payload = json.dumps(dict(context), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_aggregate_identity_consistency(aggregate_record) -> None:
    """Item 13: the identity embedded in ``AggregateRecord.identity`` must
    agree with the identity embedded in its own
    ``metrics['context']['aggregate_identity']``. FAIL CLOSED on any
    disagreement -- never silently prefer one side."""

    context = (aggregate_record.metrics or {}).get("context") or {}
    ctx_identity = context.get("aggregate_identity") or {}
    record_identity = aggregate_record.identity

    checks = (
        ("canonical_aggregate_id", ctx_identity.get("canonical_aggregate_id"), record_identity.canonical_aggregate_id),
        ("aggregation_scope", ctx_identity.get("aggregation_scope"), record_identity.aggregation_scope),
        ("hypothesis_id", ctx_identity.get("hypothesis_id"), record_identity.hypothesis_id),
        ("evaluator_version", ctx_identity.get("evaluator_version"), record_identity.evaluator_version),
    )
    mismatches = [name for name, ctx_val, rec_val in checks if ctx_val != rec_val]
    if mismatches:
        raise UEF6AggregateIdentityConsistencyError(
            f"AggregateRecord.identity vs metrics.context.aggregate_identity disagree on {mismatches} "
            f"(record canonical_aggregate_id={record_identity.canonical_aggregate_id!r}) -- refusing to "
            "build a witness-match key from a contradictory identity"
        )


def _aggregate_full_key(aggregate_record) -> tuple:
    """Item 12's full semantic match key: (evaluation_record_id,
    canonical_aggregate_id, context_digest) -- never evaluation_record_id
    alone, which two differently-contexted aggregates can share."""

    context = (aggregate_record.metrics or {}).get("context") or {}
    return (
        aggregate_record.identity.evaluation_record_id,
        aggregate_record.identity.canonical_aggregate_id,
        _canonical_context_digest(context),
    )


def _witness_full_key(witness: AggregateLineageWitness) -> tuple:
    return (witness.aggregate_evaluation_record_id, witness.canonical_aggregate_id, witness.context_digest)


@dataclass(frozen=True)
class WitnessAggregateAccounting:
    aggregate_call_count: int
    captured_witness_count: int
    persisted_aggregate_count: int

    matched_occurrence_count: int
    missing_aggregate_occurrence_count: int
    orphan_witness_occurrence_count: int
    missing_aggregate_occurrences: Sequence[dict]
    orphan_witness_occurrences: Sequence[dict]

    def to_dict(self) -> dict:
        return {
            "aggregate_call_count": self.aggregate_call_count,
            "captured_witness_count": self.captured_witness_count,
            "persisted_aggregate_count": self.persisted_aggregate_count,
            "matched_occurrence_count": self.matched_occurrence_count,
            "missing_aggregate_occurrence_count": self.missing_aggregate_occurrence_count,
            "orphan_witness_occurrence_count": self.orphan_witness_occurrence_count,
            "missing_aggregate_occurrences": list(self.missing_aggregate_occurrences),
            "orphan_witness_occurrences": list(self.orphan_witness_occurrences),
        }


def account_witnesses_against_aggregates(
    witnesses: Sequence[AggregateLineageWitness],
    persisted_aggregates: Sequence[tuple],  # (AggregateRecord, meta) as historical_recompute.RecomputeRun.aggregates
) -> WitnessAggregateAccounting:
    """Multiset (Counter-based) accounting over the FULL semantic match key
    (item 14) -- never a set/dict keyed only by evaluation_record_id, which
    would let one witness occurrence falsely cover two context-different
    persisted aggregate occurrences (or vice versa). One witness occurrence
    covers AT MOST one persisted aggregate occurrence of the identical key,
    and vice versa."""

    for aggregate_record, _meta in persisted_aggregates:
        _verify_aggregate_identity_consistency(aggregate_record)

    persisted_keys = [_aggregate_full_key(agg) for agg, _meta in persisted_aggregates]
    witness_keys = [_witness_full_key(w) for w in witnesses]

    persisted_counter = Counter(persisted_keys)
    witness_counter = Counter(witness_keys)

    def _key_dict(key: tuple) -> dict:
        return {"evaluation_record_id": key[0], "canonical_aggregate_id": key[1], "context_digest": key[2]}

    matched = 0
    missing_occurrences: list = []
    orphan_occurrences: list = []
    for key in sorted(set(persisted_counter) | set(witness_counter)):
        p_count = persisted_counter.get(key, 0)
        w_count = witness_counter.get(key, 0)
        matched += min(p_count, w_count)
        if p_count > w_count:
            missing_occurrences.extend([_key_dict(key)] * (p_count - w_count))
        elif w_count > p_count:
            orphan_occurrences.extend([_key_dict(key)] * (w_count - p_count))

    return WitnessAggregateAccounting(
        aggregate_call_count=len(witnesses),
        captured_witness_count=len(witnesses),
        persisted_aggregate_count=len(persisted_aggregates),
        matched_occurrence_count=matched,
        missing_aggregate_occurrence_count=len(missing_occurrences),
        orphan_witness_occurrence_count=len(orphan_occurrences),
        missing_aggregate_occurrences=tuple(missing_occurrences),
        orphan_witness_occurrences=tuple(orphan_occurrences),
    )


# ---------------------------------------------------------------------------
# Population lineage coverage (items 12-13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WitnessCoverageDetail:
    witness_id: str
    canonical_aggregate_id: str
    family: str

    sample_count: int
    evaluated_count: int
    missing_count: int
    excluded_count: int

    identified_member_count: int
    unidentified_member_count: int
    exact_population_member_identity_proven: bool

    evaluated_member_count: int
    evaluated_episode_match_count: int
    evaluated_episode_missing_count: int
    exact_evaluated_episode_membership_proven: bool

    def to_dict(self) -> dict:
        return {
            "witness_id": self.witness_id,
            "canonical_aggregate_id": self.canonical_aggregate_id,
            "family": self.family,
            "sample_count": self.sample_count,
            "evaluated_count": self.evaluated_count,
            "missing_count": self.missing_count,
            "excluded_count": self.excluded_count,
            "identified_member_count": self.identified_member_count,
            "unidentified_member_count": self.unidentified_member_count,
            "exact_population_member_identity_proven": self.exact_population_member_identity_proven,
            "evaluated_member_count": self.evaluated_member_count,
            "evaluated_episode_match_count": self.evaluated_episode_match_count,
            "evaluated_episode_missing_count": self.evaluated_episode_missing_count,
            "exact_evaluated_episode_membership_proven": self.exact_evaluated_episode_membership_proven,
        }


def compute_witness_coverage(
    witnesses: Sequence[AggregateLineageWitness],
    episodes: Sequence,
    family_by_record_id: Mapping[str, str],
) -> list:
    """One ``WitnessCoverageDetail`` per witness. ``exact_evaluated_episode_membership_proven``
    and ``exact_population_member_identity_proven`` are DELIBERATELY kept
    distinct (item 13) -- neither is derived from the other."""

    details = []
    for w in witnesses:
        verification = verify_witness_against_episode_population(w, episodes)
        details.append(
            WitnessCoverageDetail(
                witness_id=w.witness_id,
                canonical_aggregate_id=w.canonical_aggregate_id,
                family=family_by_record_id.get(w.aggregate_evaluation_record_id, ""),
                sample_count=w.sample_count, evaluated_count=w.evaluated_count,
                missing_count=w.missing_count, excluded_count=w.excluded_count,
                identified_member_count=w.identified_member_count,
                unidentified_member_count=w.unidentified_member_count,
                exact_population_member_identity_proven=w.exact_population_member_identity_proven,
                evaluated_member_count=verification.evaluated_member_count,
                evaluated_episode_match_count=verification.evaluated_episode_match_count,
                evaluated_episode_missing_count=verification.evaluated_episode_missing_count,
                exact_evaluated_episode_membership_proven=verification.exact_evaluated_episode_membership_proven,
            )
        )
    return details


def aggregate_coverage_totals(details: Sequence[WitnessCoverageDetail]) -> dict:
    """Overall + per-family totals. No estimates -- plain sums/counts."""

    def _totals(rows):
        return {
            "witness_count": len(rows),
            "sample_count": sum(r.sample_count for r in rows),
            "evaluated_count": sum(r.evaluated_count for r in rows),
            "missing_count": sum(r.missing_count for r in rows),
            "excluded_count": sum(r.excluded_count for r in rows),
            "exact_population_member_identity_proven_count": sum(1 for r in rows if r.exact_population_member_identity_proven),
            "exact_evaluated_episode_membership_proven_count": sum(1 for r in rows if r.exact_evaluated_episode_membership_proven),
            "not_provable_count": sum(1 for r in rows if not r.exact_evaluated_episode_membership_proven),
        }

    overall = _totals(details)
    by_family: dict = {}
    for r in details:
        by_family.setdefault(r.family, []).append(r)
    per_family = {family: _totals(rows) for family, rows in sorted(by_family.items())}
    return {"overall": overall, "by_family": per_family}


# ---------------------------------------------------------------------------
# Duplicate-member historical scan (item 14)
# ---------------------------------------------------------------------------


def scan_duplicate_members(witnesses: Sequence[AggregateLineageWitness]) -> dict:
    """Final Audit item D/17-19: ``duplicate member identity kinds`` (how
    many DISTINCT evaluation_record_ids repeat within one aggregate) and
    ``duplicate member excess occurrences`` (how many occurrences beyond
    the first, summed across those repeating ids) are DIFFERENT numbers
    and must never be conflated.

    Per witness (UEF-6B, unmodified, already approved), ``duplicate_member_ids``
    is the tuple of repeating evaluation_record_ids -- its LENGTH is the
    kind count. ``duplicate_member_identity_count`` is UEF-6B's own already-
    computed EXCESS sum (``sum(count - 1 for repeating ids)``, per
    ``lineage_witness._build_witness``) despite its name -- UEF-6C reads
    that existing witness field for the excess total, and separately reads
    ``len(duplicate_member_ids)`` for the kind total; neither total is
    derived from the other."""

    with_duplicates = [w for w in witnesses if w.duplicate_member_ids]
    return {
        "aggregates_with_duplicate_member_ids": len(with_duplicates),
        "duplicate_member_identity_count_total": sum(len(w.duplicate_member_ids) for w in witnesses),
        "duplicate_member_excess_count_total": sum(w.duplicate_member_identity_count for w in witnesses),
        "per_aggregate_detail": [
            {
                "witness_id": w.witness_id,
                "canonical_aggregate_id": w.canonical_aggregate_id,
                "duplicate_member_ids": list(w.duplicate_member_ids),
                "duplicate_member_identity_count": len(w.duplicate_member_ids),
                "duplicate_member_excess_count": w.duplicate_member_identity_count,
            }
            for w in with_duplicates
        ],
    }


# ---------------------------------------------------------------------------
# Cross-aggregate evidence reuse (items 15-16)
# ---------------------------------------------------------------------------


def find_cross_aggregate_record_reuse(witnesses: Sequence[AggregateLineageWitness]) -> list:
    """Descriptive only -- reuse across aggregates is NOT automatically
    classified as an error (item 15)."""

    by_record_id: dict = {}
    for w in witnesses:
        for occ in w.member_occurrences:
            if occ.state == "EVALUATED" and occ.evaluation_record_id:
                by_record_id.setdefault(occ.evaluation_record_id, set()).add(w.canonical_aggregate_id)

    entries = []
    for record_id, aggregate_ids in sorted(by_record_id.items()):
        if len(aggregate_ids) > 1:
            entries.append({"evaluation_record_id": record_id, "aggregate_ids": sorted(aggregate_ids)})
    return entries


def find_cross_aggregate_physical_event_reuse(
    witnesses: Sequence[AggregateLineageWitness],
    episode_by_record_id: Mapping[str, object],  # evaluation_record_id -> EpisodeRecord
) -> list:
    """Resolves evaluated members to EpisodeRecords (where possible, via
    exact evaluation_record_id only) and reports reuse of the SAME
    canonical_event_id (physical event) across DIFFERENT aggregate
    witnesses -- kept explicitly distinct from evaluation-record reuse."""

    by_event_id: dict = {}
    for w in witnesses:
        for occ in w.member_occurrences:
            if occ.state != "EVALUATED" or not occ.evaluation_record_id:
                continue
            episode = episode_by_record_id.get(occ.evaluation_record_id)
            if episode is None:
                continue
            event_id = episode.identity.event.canonical_event_id
            by_event_id.setdefault(event_id, set()).add(w.canonical_aggregate_id)

    entries = []
    for event_id, aggregate_ids in sorted(by_event_id.items()):
        if len(aggregate_ids) > 1:
            entries.append({"canonical_event_id": event_id, "aggregate_ids": sorted(aggregate_ids)})
    return entries
