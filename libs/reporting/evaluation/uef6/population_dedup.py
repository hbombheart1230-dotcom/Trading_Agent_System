"""UEF-6A pure population-dedup classifier.

Never depends on filesystem paths. Never re-implements the frozen UEF-1
duplicate-relation decision logic (``classify_duplicate_relation`` is
imported and called verbatim, never re-derived). Never filters, drops, or
merges an ``EpisodeRecord`` -- purely a read-only classifier that groups
and labels.

Overlap-candidate search operates primarily on records sharing
``canonical_event_id`` (a bounded, per-physical-event group), never a
naive all-pairs comparison across unrelated events -- pairwise
classification only ever runs WITHIN one event cluster.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from libs.reporting.evaluation.canonical import DuplicateRelation, EpisodeRecord, classify_duplicate_relation

from .report_model import DuplicateGroup, EventCluster, PopulationDedupReport

# The complete, bounded relation vocabulary this report always accounts
# for (every entry present in relation_counts, even at 0) -- fixed key
# order independent of encounter order, per the determinism requirement.
_ALL_RELATIONS = tuple(r.value for r in DuplicateRelation)


class UEF6PopulationDedupError(Exception):
    """Base class for UEF-6A-local integrity errors."""


class UEF6IdentityContentCollisionError(UEF6PopulationDedupError):
    """Raised when two episodes share ``evaluation_record_id`` AND
    ``evaluator_version`` but have different canonical content.

    This is NOT a harmless duplicate: it means the same claimed identity
    produced two different bodies. Fail closed -- never silently choose
    one row, never merge them, never classify as an ordinary
    ACCIDENTAL_DUPLICATE."""


class UEF6AccountingInvariantError(UEF6PopulationDedupError):
    """Raised if this module's own required accounting invariants
    (item 17) do not hold after classification -- an internal defensive
    check, should never fire if the classification logic above it is
    correct."""


def _canonical_content_digest(episode: EpisodeRecord) -> str:
    """Deterministic content digest of one episode's full canonical
    representation (via its own frozen ``to_dict()``), used ONLY to
    detect a genuine identity/content collision within an
    (evaluation_record_id, evaluator_version) group that is already
    expected to be byte-identical."""

    payload = json.dumps(episode.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def population_semantic_digest(episodes: Sequence[EpisodeRecord]) -> str:
    """Order-independent MULTISET digest of the loaded ``EpisodeRecord``
    population -- the identity that ``UEF6A_RUN_ID`` binds to (Order-
    Independent Run Identity Fix). Never depends on filesystem row order:
    permuting the input yields the identical digest.

    Deliberately a MULTISET, not a set -- ``[A, A]`` and ``[A]`` MUST
    digest differently, since duplicate occurrence count is itself
    semantic input to UEF-6A's own dedup detection (an accidental
    duplicate's ``occurrence_count`` would otherwise be invisible to the
    run identity). Each episode is independently canonicalized via its own
    frozen ``to_dict()`` (the exact same canonicalization
    ``_canonical_content_digest`` uses), the resulting canonical JSON
    strings are sorted (fixing a deterministic order regardless of input
    order), and the sorted list is hashed as one JSON array -- never a
    naive ``"|".join(...)``, which could collide if one row's own
    serialized form contained the delimiter."""

    rows = sorted(
        json.dumps(ep.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True) for ep in episodes
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _EpisodeRow:
    """The small, stable set of identity/provenance fields this module
    actually reasons over for one episode -- extracted once so the rest
    of this module never re-reaches into ``EpisodeRecord.identity`` by
    hand in more than one place."""

    canonical_event_id: str
    evaluation_subject_id: str
    evaluation_record_id: str
    hypothesis_id: str
    evaluator_version: str
    execution_mode: str
    symbol: str
    trading_date: str
    episode: EpisodeRecord


def _extract_row(episode: EpisodeRecord) -> _EpisodeRow:
    identity = episode.identity
    return _EpisodeRow(
        canonical_event_id=identity.event.canonical_event_id,
        evaluation_subject_id=identity.evaluation_subject_id,
        evaluation_record_id=identity.evaluation_record_id,
        hypothesis_id=identity.hypothesis_id,
        evaluator_version=identity.evaluator_version,
        execution_mode=episode.execution_mode.value if hasattr(episode.execution_mode, "value") else str(episode.execution_mode),
        symbol=episode.symbol,
        trading_date=episode.trading_date,
        episode=episode,
    )


def _classify_pair(a: "_EpisodeRow", b: "_EpisodeRow") -> DuplicateRelation:
    return classify_duplicate_relation(
        canonical_event_id_a=a.canonical_event_id, evaluation_subject_id_a=a.evaluation_subject_id,
        evaluation_record_id_a=a.evaluation_record_id, symbol_a=a.symbol, hypothesis_id_a=a.hypothesis_id,
        evaluator_version_a=a.evaluator_version,
        canonical_event_id_b=b.canonical_event_id, evaluation_subject_id_b=b.evaluation_subject_id,
        evaluation_record_id_b=b.evaluation_record_id, symbol_b=b.symbol, hypothesis_id_b=b.hypothesis_id,
        evaluator_version_b=b.evaluator_version,
    )


def _build_duplicate_groups(rows_by_record_id: Mapping[str, Sequence["_EpisodeRow"]]) -> list:
    """A ``duplicate_groups`` entry represents an ACTUAL exact repeated
    evaluation ONLY (occurrence_count > 1 rows sharing the same
    ``evaluation_record_id`` AND the same ``evaluator_version``, verified
    byte-identical). An evaluator-version variant is NOT, by itself, a
    duplicate group (Evaluator-Version Contract Micro-Fix item 5) --
    ``evaluator_version`` is deliberately excluded from
    ``evaluation_record_id`` (frozen ``evaluation_record_id()`` contract),
    so two rows sharing one ``evaluation_record_id`` under two different
    evaluator versions are legitimate, distinct observed rows, never
    collapsed and never collision-checked against each other. Within an
    ``evaluation_record_id`` group, every ``evaluator_version`` sub-group is
    handled independently."""

    groups = []
    for record_id in sorted(rows_by_record_id.keys()):
        rows = rows_by_record_id[record_id]
        if len(rows) < 2:
            continue

        rows_by_version: dict = {}
        for row in rows:
            rows_by_version.setdefault(row.evaluator_version, []).append(row)

        for version in sorted(rows_by_version.keys()):
            version_rows = rows_by_version[version]
            if len(version_rows) < 2:
                # A single row under this evaluator_version is not, by
                # itself, a duplicate -- it may be paired with a
                # different-version sibling (SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION,
                # visible in relation_counts via the pairwise event-cluster
                # classification), but that is not a "duplicate group".
                continue

            # Same record id, same evaluator_version: these MUST be
            # byte-identical reproductions of the same computation. Verify,
            # never assume.
            digests = sorted({_canonical_content_digest(r.episode) for r in version_rows})
            if len(digests) > 1:
                raise UEF6IdentityContentCollisionError(
                    f"evaluation_record_id={record_id!r} (evaluator_version={version!r}) has "
                    f"{len(digests)} distinct content digests across {len(version_rows)} rows -- same "
                    "claimed identity AND same evaluator_version, different canonical content. Never "
                    "silently choosing one row or merging: this is an identity/content integrity "
                    "violation, not an ordinary accidental duplicate and not a legitimate "
                    "evaluator-version variant (those differ by version, not silently by body under the "
                    "same version)."
                )
            occurrence_count = len(version_rows)
            groups.append(
                DuplicateGroup(
                    evaluation_record_id=record_id,
                    evaluation_subject_id=version_rows[0].evaluation_subject_id,
                    canonical_event_id=version_rows[0].canonical_event_id,
                    occurrence_count=occurrence_count,
                    duplicate_excess_count=occurrence_count - 1,
                    content_digest=digests[0],
                    relation=DuplicateRelation.ACCIDENTAL_DUPLICATE.value,
                )
            )
    return groups


def _build_event_clusters(rows_by_event_id: Mapping[str, Sequence["_EpisodeRow"]]) -> list:
    clusters = []
    for event_id in sorted(rows_by_event_id.keys()):
        rows = rows_by_event_id[event_id]
        relation_summary: dict = {}
        # Pairwise classification WITHIN this one event's own rows only
        # (bounded by this physical event's own cardinality -- never
        # across unrelated events).
        n = len(rows)
        for i in range(n):
            for j in range(i + 1, n):
                relation = _classify_pair(rows[i], rows[j])
                relation_summary[relation.value] = relation_summary.get(relation.value, 0) + 1
        subject_ids = sorted({r.evaluation_subject_id for r in rows})
        record_ids = sorted({r.evaluation_record_id for r in rows})
        clusters.append(
            EventCluster(
                canonical_event_id=event_id,
                symbols=tuple(sorted({r.symbol for r in rows})),
                trading_dates=tuple(sorted({r.trading_date for r in rows})),
                evaluation_subject_ids=tuple(subject_ids),
                evaluation_record_ids=tuple(record_ids),
                hypothesis_ids=tuple(sorted({r.hypothesis_id for r in rows})),
                execution_modes=tuple(sorted({r.execution_mode for r in rows})),
                evaluator_versions=tuple(sorted({r.evaluator_version for r in rows})),
                row_count=n,
                unique_subject_count=len(subject_ids),
                unique_record_count=len(record_ids),
                relation_summary=relation_summary,
            )
        )
    return clusters


def analyze_episode_population(episodes: Sequence[EpisodeRecord]) -> PopulationDedupReport:
    """Pure population-dedup analysis over an already-loaded, already-
    identity-validated sequence of ``EpisodeRecord``.

    No filesystem access. No mutation of any input record. Raises
    ``UEF6IdentityContentCollisionError`` (fail-closed, no report
    produced) if a genuine identity/content collision is found.
    """

    rows = [_extract_row(ep) for ep in episodes]
    raw_row_count = len(rows)

    rows_by_event_id: dict = {}
    rows_by_record_id: dict = {}
    for row in rows:
        rows_by_event_id.setdefault(row.canonical_event_id, []).append(row)
        rows_by_record_id.setdefault(row.evaluation_record_id, []).append(row)

    # Fail-closed collision check happens before anything else is finalized.
    duplicate_groups = _build_duplicate_groups(rows_by_record_id)
    event_clusters = _build_event_clusters(rows_by_event_id)

    unique_canonical_event_count = len(rows_by_event_id)
    unique_evaluation_subject_count = len({row.evaluation_subject_id for row in rows})
    unique_evaluation_record_count = len(rows_by_record_id)

    # relation_counts is derived ONLY from the event-cluster pairwise
    # classification (the exhaustive, non-double-counted pairwise
    # enumeration within each physical event -- a repeated evaluation_record_id
    # pair is classified ACCIDENTAL_DUPLICATE/SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION
    # there too, since it shares canonical_event_id by construction). The
    # duplicate_groups list is a SEPARATE, group-level (not pair-level) view
    # of the same underlying repeats -- summing both here would double-count.
    relation_counts = {name: 0 for name in _ALL_RELATIONS}
    for cluster in event_clusters:
        for relation_name, count in cluster.relation_summary.items():
            relation_counts[relation_name] = relation_counts.get(relation_name, 0) + count

    duplicate_excess_row_count = sum(g.duplicate_excess_count for g in duplicate_groups)
    events_with_multiple_subjects = sum(1 for c in event_clusters if c.unique_subject_count > 1)
    events_with_multiple_records = sum(1 for c in event_clusters if c.unique_record_count > 1)

    # --- item 17: required accounting invariants ---
    if sum(c.row_count for c in event_clusters) != raw_row_count:
        raise UEF6AccountingInvariantError("sum(cluster.row_count) != raw_row_count")
    if unique_canonical_event_count != len(event_clusters):
        raise UEF6AccountingInvariantError("unique_canonical_event_count != number of event clusters")
    if unique_evaluation_subject_count != len({row.evaluation_subject_id for row in rows}):
        raise UEF6AccountingInvariantError("unique_evaluation_subject_count mismatch")
    if unique_evaluation_record_count != len(rows_by_record_id):
        raise UEF6AccountingInvariantError("unique_evaluation_record_count mismatch")
    # NOTE (Evaluator-Version Contract Micro-Fix item 4): the general
    # invariant `duplicate_excess_row_count == raw_row_count -
    # unique_evaluation_record_count` is INVALID and deliberately removed.
    # It only holds when every repeated evaluation_record_id is an
    # accidental duplicate and no legitimate evaluator-version variants
    # exist. duplicate_excess_row_count instead is, and must remain,
    # exactly `sum(occurrence_count - 1 for g in duplicate_groups)` --
    # evaluator-version variants contribute 0 to it, by construction of
    # _build_duplicate_groups. `raw_row_count` and
    # `unique_evaluation_record_count` remain separate cardinalities; no
    # cross-invariant between them and duplicate_excess_row_count is
    # asserted here.
    expected_excess_from_groups = sum(g.duplicate_excess_count for g in duplicate_groups)
    if duplicate_excess_row_count != expected_excess_from_groups:
        raise UEF6AccountingInvariantError(
            f"duplicate_excess_row_count={duplicate_excess_row_count} != "
            f"sum(duplicate_groups excess)={expected_excess_from_groups}"
        )

    return PopulationDedupReport(
        raw_row_count=raw_row_count,
        unique_canonical_event_count=unique_canonical_event_count,
        unique_evaluation_subject_count=unique_evaluation_subject_count,
        unique_evaluation_record_count=unique_evaluation_record_count,
        duplicate_group_count=len(duplicate_groups),
        duplicate_excess_row_count=duplicate_excess_row_count,
        relation_counts=relation_counts,
        event_cluster_count=len(event_clusters),
        multi_evaluation_event_count=events_with_multiple_subjects,
        events_with_multiple_subjects=events_with_multiple_subjects,
        events_with_multiple_records=events_with_multiple_records,
        event_clusters=tuple(event_clusters),
        duplicate_groups=tuple(duplicate_groups),
    )
