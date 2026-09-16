"""UEF-1A Closure Reset -- Group B: collection-level referential validation.

``record.py::RecordLink`` only validates itself STRUCTURALLY (relation_type
is one of the allowed values, target_record_id is well-formed, a link
cannot self-reference) -- it has no way to know whether the record it
points at actually exists, is the right kind, or carries the evidence a
given relation_type implies. That is REFERENTIAL validation, and it needs
the whole set of records being considered together, which is exactly what
this module's :func:`validate_record_links` does.

This is still a pure validator: it never creates, fills in, or repairs a
record; it only raises on a relation that cannot possibly be true given
the records actually provided. Nothing here computes a return, cost, or
metric -- Work Package B's boundary is unchanged.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .contracts import EntryAuthority, IdentityKind
from .record import CanonicalEvaluationRecord, EpisodeRecord, PairRecord, RecordLink, SequenceRecord


class RecordRelationValidationError(ValueError):
    """Raised when a relation cannot be true given the records actually provided."""


_FILL_AUTHORITIES = frozenset({EntryAuthority.MOCK_FILL, EntryAuthority.BROKER_FILL})

# UEF-1 FINAL CLOSURE PATCH item 10: named, diagnostic-friendly reasons for
# _has_compatible_submission_fill_provenance -- kept deliberately small (a
# plain string constant, not an enum-per-evidence-type framework) since
# only one real, verified evidence kind exists in this repo's own real
# artifacts today (a shared run_id). Adding a second recognized evidence
# kind later means adding one more branch here, not redesigning this.
PROVENANCE_MATCH_RUN_ID = "MATCH_RUN_ID"
PROVENANCE_NO_SHARED_PROVENANCE = "NO_SHARED_PROVENANCE"


def _index_by_record_id(records: Sequence[CanonicalEvaluationRecord]) -> Mapping[str, CanonicalEvaluationRecord]:
    index: dict[str, CanonicalEvaluationRecord] = {}
    for record in records:
        record_id = getattr(record.identity, "evaluation_record_id", "")
        if not record_id:
            continue
        if record_id in index:
            raise RecordRelationValidationError(
                f"duplicate evaluation_record_id={record_id!r} found in the given record collection -- "
                "each canonical record id must be unique within a validated collection; a repeated id "
                "would let referential validation silently pick whichever record happened to be indexed "
                "last"
            )
        index[record_id] = record
    return index


def validate_record_links(records: Sequence[CanonicalEvaluationRecord]) -> None:
    """Validate every ``related_records`` entry across the given record collection.

    Only ``EpisodeRecord`` carries ``related_records`` as of this Closure
    Reset. Raises :class:`RecordRelationValidationError` on the first
    relation that cannot be substantiated by the records actually
    provided; returns ``None`` (no findings) otherwise.
    """

    index = _index_by_record_id(records)
    for record in records:
        for link in getattr(record, "related_records", ()) or ():
            if link.relation_type == "SUBMISSION_TO_FILL":
                _validate_submission_to_fill(record, link, index)
            else:  # pragma: no cover -- ALLOWED_RECORD_RELATION_TYPES currently has exactly one member
                raise RecordRelationValidationError(f"no referential validator registered for relation_type={link.relation_type!r}")


def _has_compatible_submission_fill_provenance(source: EpisodeRecord, target: EpisodeRecord) -> tuple[bool, str]:
    """UEF-1 FINAL CLOSURE PATCH H3: does ``target`` share real, source-native
    linkage evidence with ``source``, beyond same symbol/same trading_date?

    Same symbol + same trading_date is not enough on its own -- two
    genuinely unrelated submissions for the same stock on the same day
    would otherwise satisfy every check ``_validate_submission_to_fill``
    had before this patch. Investigated against the real 2026-09-10 024060
    artifacts (``probe_submissions.json``'s ``submissions[0].run_id`` and
    ``trade_read_model.json``'s ``selection.strategist_run_id``): both
    genuinely carry the SAME run id for the same real event -- this is the
    one real, verified shared-provenance fact this repo's own artifacts
    provide, and both ``build_episode_record()`` calls for that pair must
    be given ``source_run_id=`` that value for this check to recognize
    them as linked. No other evidence kind (decision_id, order_id,
    client_order_id, ...) is invented here -- neither artifact carries one
    that is not already just a formatted copy of the same run_id (e.g.
    ``q9_decision_id = f"Q9_{day}_{run_id}"``), so only ``source_run_id`` is
    checked.
    """

    source_run_id = str(source.identity.source_run_id or "").strip()
    target_run_id = str(target.identity.source_run_id or "").strip()
    if source_run_id and target_run_id and source_run_id == target_run_id:
        return True, PROVENANCE_MATCH_RUN_ID
    return False, PROVENANCE_NO_SHARED_PROVENANCE


def _validate_submission_to_fill(source: CanonicalEvaluationRecord, link: RecordLink, index: Mapping[str, CanonicalEvaluationRecord]) -> None:
    if not isinstance(source, EpisodeRecord):
        raise RecordRelationValidationError("SUBMISSION_TO_FILL source must be an EpisodeRecord")
    if source.entry is None or source.entry.entry_authority is not EntryAuthority.SUBMITTED_INTENT:
        raise RecordRelationValidationError(
            "SUBMISSION_TO_FILL source must have entry.entry_authority == SUBMITTED_INTENT "
            "(the record declaring this relation must actually BE a submission)"
        )
    target = index.get(link.target_record_id)
    if target is None:
        raise RecordRelationValidationError(
            f"SUBMISSION_TO_FILL target_record_id={link.target_record_id!r} does not exist in the given record collection "
            "(a syntactically valid REC_ id is not evidence that the record it names was ever provided)"
        )
    if not isinstance(target, EpisodeRecord):
        raise RecordRelationValidationError("SUBMISSION_TO_FILL target must be an EpisodeRecord")
    if target.entry is None or target.entry.entry_authority not in _FILL_AUTHORITIES:
        raise RecordRelationValidationError(
            "SUBMISSION_TO_FILL target must show confirmed fill evidence "
            "(entry.entry_authority in {MOCK_FILL, BROKER_FILL}) -- linking to another submission, "
            "or to a record with no fill evidence at all, is not a valid SUBMISSION_TO_FILL relation"
        )
    if target.symbol != source.symbol:
        raise RecordRelationValidationError(
            f"SUBMISSION_TO_FILL target.symbol={target.symbol!r} does not match source.symbol={source.symbol!r}"
        )
    if target.trading_date != source.trading_date:
        raise RecordRelationValidationError(
            f"SUBMISSION_TO_FILL target.trading_date={target.trading_date!r} does not match source.trading_date={source.trading_date!r}"
        )
    compatible, reason = _has_compatible_submission_fill_provenance(source, target)
    if not compatible:
        raise RecordRelationValidationError(
            f"SUBMISSION_TO_FILL requires shared source-native linkage evidence beyond symbol/trading_date "
            f"(e.g. the same identity.source_run_id) -- got reason={reason!r}; same symbol and same "
            "trading_date alone is not evidence that this submission and this fill are the same "
            "real-world event"
        )


# --------------------------------------------------------------------------
# UEF-1 FINAL CLOSURE PATCH item 18-21: native identity collision boundary
# check. UEF-1's own contract (see identity.py) ASSUMES a NATIVE
# (source_namespace, source_id) pair is already event-level unique within
# its source namespace -- verifying that a specific real legacy source
# actually upholds that assumption for every historical record is UEF-4's
# job (the adapter layer), never UEF-1's. This function only catches the
# narrower, in-scope case: the SAME (namespace, source_id) appearing twice
# in ONE given collection against two different symbol/trading_date facts,
# which can only mean a genuine upstream collision or a caller-side bug --
# never a general legacy-source audit.
# --------------------------------------------------------------------------


def _native_fact_rows(record: CanonicalEvaluationRecord):
    if isinstance(record, EpisodeRecord):
        yield record.identity.event, record.symbol, record.trading_date
    elif isinstance(record, PairRecord):
        yield record.identity.left_event, record.left.symbol, record.trading_date
        yield record.identity.right_event, record.right.symbol, record.trading_date
    elif isinstance(record, SequenceRecord):
        for leg in record.legs:
            yield leg.event, record.symbol, record.trading_date


def validate_native_event_identity_consistency(records: Sequence[CanonicalEvaluationRecord]) -> None:
    """Detect a NATIVE ``(source_namespace, source_id)`` reused, within the
    given collection, against two different symbol/trading_date facts.

    Deliberately scoped to ``EpisodeRecord.identity.event``,
    ``PairRecord.identity.left_event``/``right_event`` (each side has its
    own symbol), and each ``SequenceRecord`` leg's ``event`` -- a
    ``PairRecord``'s own ``pair_event`` and an ``AggregateRecord``'s
    ``aggregate_ref`` are not symbol-scoped and are out of scope for this
    check (see the module docstring above for why this stays minimal).
    """

    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for record in records:
        for ref, symbol, trading_date in _native_fact_rows(record):
            if ref.identity_kind is not IdentityKind.NATIVE:
                continue
            key = (ref.source_namespace, ref.source_id)
            fact = (symbol, trading_date)
            if key in seen and seen[key] != fact:
                raise RecordRelationValidationError(
                    f"native identity collision: (source_namespace={ref.source_namespace!r}, "
                    f"source_id={ref.source_id!r}) is used for both {seen[key]!r} and {fact!r} "
                    "(symbol, trading_date) within this collection -- a NATIVE id must be "
                    "event-level unique within its source namespace"
                )
            seen[key] = fact


__all__ = [
    "RecordRelationValidationError",
    "PROVENANCE_MATCH_RUN_ID",
    "PROVENANCE_NO_SHARED_PROVENANCE",
    "validate_record_links",
    "validate_native_event_identity_consistency",
]
