"""UEF-1A -- the canonical record family (Closure Reset revision).

UEF-1A's own responsibility boundary (see the "UEF Phase Boundary" table
in ``docs/research/unified_evaluation_foundation.md``): Contract / Record
/ Identity / Representability. Full legacy adapters, forward-return
calculation, and cost/metric engines are explicitly UEF-2/3/4, not here.

Each record kind has its OWN identity shape, built on the native-id-
preferred ``EventRef`` (see ``identity.py``):

    EpisodeIdentity   -- one EventRef (the episode's own event)
    PairIdentity      -- THREE EventRefs (the pair's own event, plus a
                         left_event and right_event each -- Fix2 #13:
                         Strategist Stage2's real before/after candidates
                         each have their OWN native decision context, not
                         one shared "episode" identity)
    SequenceIdentity  -- one EventRef for the sequence itself; each leg
                         (SequenceLeg) carries its own EventRef pointing
                         at that leg's own real trade
    AggregateIdentity -- one EventRef for the aggregate itself; NEVER
                         requires a symbol/trading_date-based market
                         event (Fix2 #16: an aggregate has no market
                         event identity of its own)

Still true, unchanged from Work Package A's original mandate: no function
in this module computes gross/net return, MFE, MAE, or any aggregate
statistic from raw price data. Nothing here is imported by any existing
evaluator, report script, or runtime node -- additive only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Union

from . import identity as _identity
from .identity import EventRef
from .contracts import (
    ALLOWED_RECORD_RELATION_TYPES,
    SCHEMA_VERSION,
    CANONICAL_RETURN_UNIT,
    CheckpointCompleteness,
    CheckpointMetricKind,
    EntryAuthority,
    EventDateRelation,
    EventOrigin,
    EvidenceStatus,
    ExecutionMode,
    IdentityKind,
    LineageStatus,
    ObservationType,
    RecordKind,
    ReturnUnit,
    SampleStatus,
)


class CanonicalRecordValidationError(ValueError):
    """Raised only for combinations that are unambiguously self-contradictory.

    A data contract, not a policy engine.
    """


class CanonicalSerializationError(TypeError):
    """Raised when a value cannot be represented in the canonical JSON-safe form.

    No silent stringification -- an unsupported type raises here, naming
    the offending field.
    """


def _validate_evaluation_ids(*, canonical_event_id: str, hypothesis_id: str, observation_type: Any,
                              execution_mode: Any, evaluation_subject_id: str, evaluation_record_id: str) -> None:
    """Recompute both evaluation_subject_id and evaluation_record_id from the record's
    OTHER already-present fields, and compare -- true consistency-by-construction,
    not a format check."""

    try:
        expected_subject = _identity.evaluation_subject_id(
            canonical_event_id=canonical_event_id, hypothesis_id=hypothesis_id, observation_type=observation_type,
        )
        if expected_subject != evaluation_subject_id:
            raise CanonicalRecordValidationError(
                f"evaluation_subject_id={evaluation_subject_id!r} does not match the recomputed value from "
                f"(canonical_event_id, hypothesis_id, observation_type) -- use the build_*_record() helpers "
                "rather than typing an identity by hand"
            )
        expected_record = _identity.evaluation_record_id(evaluation_subject_id=evaluation_subject_id, execution_mode=execution_mode)
        if expected_record != evaluation_record_id:
            raise CanonicalRecordValidationError(
                f"evaluation_record_id={evaluation_record_id!r} does not match the recomputed value from "
                "(evaluation_subject_id, execution_mode)"
            )
    except ValueError as exc:
        if isinstance(exc, CanonicalRecordValidationError):
            raise
        raise CanonicalRecordValidationError(str(exc)) from exc


def _validate_event_ref(ref: EventRef) -> None:
    try:
        _identity.validate_event_ref(ref)
    except ValueError as exc:
        raise CanonicalRecordValidationError(str(exc)) from exc


# --------------------------------------------------------------------------
# Shared building blocks
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    legacy_program: str = ""
    legacy_schema: str = ""
    source_artifact: str = ""
    source_function: str = ""


@dataclass(frozen=True)
class EntryObservation:
    entry_time: int | None = None
    entry_price: float | None = None
    entry_authority: EntryAuthority = EntryAuthority.CANDIDATE_PRICE


@dataclass(frozen=True)
class ExitObservation:
    exit_time: int | None = None
    exit_price: float | None = None
    exit_price_authority: EntryAuthority = EntryAuthority.CANDIDATE_PRICE
    exit_reason: str = ""


@dataclass(frozen=True)
class Checkpoint:
    """``horizon_set_id`` (Fix2 #30/#31) preserves which of a source's possibly-multiple,
    mutually-disagreeing horizon families (e.g. Q12's own ``HORIZONS`` vs.
    ``HYPOTHESIS_HORIZONS``) a given checkpoint belongs to, so both sets'
    distinct provenance survive rather than being flattened into one list."""

    horizon_label: str
    horizon_origin: EventOrigin
    target_timestamp: int | None = None
    observed_timestamp: int | None = None
    observed_price: float | None = None
    gross_return: float | None = None
    net_return: float | None = None
    mfe: float | None = None
    mae: float | None = None
    completeness: CheckpointCompleteness = CheckpointCompleteness.MISSING
    source: str = ""
    return_unit: ReturnUnit = CANONICAL_RETURN_UNIT
    horizon_set_id: str = ""
    metric_kind: CheckpointMetricKind = CheckpointMetricKind.PRICE_BASED


@dataclass(frozen=True)
class EvaluationCost:
    cost_profile_id: str = ""
    applied_cost: float | None = None
    cost_unit: ReturnUnit = CANONICAL_RETURN_UNIT


@dataclass(frozen=True)
class EvaluationQuality:
    sample_status: SampleStatus = SampleStatus.ELIGIBLE
    evidence_status: EvidenceStatus = EvidenceStatus.INSUFFICIENT
    contaminated: bool = False
    exclusion_reason: str = ""
    completeness: str = ""


@dataclass(frozen=True)
class RecordLink:
    """A minimal, non-identity-affecting cross-record relation (Fix3 M4).

    e.g. an Opening Controlled Probe submission record links
    ``SUBMISSION_TO_FILL`` to the separate, later record representing its
    confirmed fill -- two genuinely distinct canonical events/records the
    whole time; this link is purely an additional, optional fact about
    their relationship, never a merge or an identity input.
    """

    relation_type: str
    target_record_id: str
    provenance: str = ""

    def __post_init__(self) -> None:
        """STRUCTURAL validation only (Closure Reset Group B): format and
        self-reference checks that need no other record. Whether the
        target actually exists, is the right record kind, or carries the
        evidence a given relation_type implies (e.g. SUBMISSION_TO_FILL's
        target must show a confirmed fill) is REFERENTIAL validation --
        that requires the whole record collection and lives in
        ``relations.py::validate_record_links()``, never here.
        """

        if self.relation_type not in ALLOWED_RECORD_RELATION_TYPES:
            raise CanonicalRecordValidationError(
                f"relation_type={self.relation_type!r} is not one of the allowed types: {sorted(ALLOWED_RECORD_RELATION_TYPES)}"
            )
        if not self.target_record_id:
            raise CanonicalRecordValidationError("RecordLink.target_record_id is required")
        try:
            _identity.validate_evaluation_id_format("evaluation_record_id", self.target_record_id)
        except ValueError as exc:
            raise CanonicalRecordValidationError(str(exc)) from exc


# --------------------------------------------------------------------------
# JSON-safe canonical serialization
# --------------------------------------------------------------------------

_JSON_SAFE_PRIMITIVES = (str, int, float, bool, type(None))


def _to_json_safe(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, EventRef):
        return value.to_dict()
    if isinstance(value, _JSON_SAFE_PRIMITIVES):
        return value
    if isinstance(value, Mapping):
        return {str(key): _to_json_safe(val, path=f"{path}.{key}") for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _to_json_safe(getattr(value, name), path=f"{path}.{name}")
            for name in value.__dataclass_fields__
        }
    if isinstance(value, (datetime, date)):
        raise CanonicalSerializationError(
            f"{path}: datetime/date objects are not canonically serializable -- "
            "convert via identity.to_epoch_seconds() before storing"
        )
    raise CanonicalSerializationError(f"{path}: unsupported type {type(value)!r} in canonical record")


def _as_plain_dict(record: Any) -> dict[str, Any]:
    return {name: getattr(record, name) for name in record.__dataclass_fields__}


def _checkpoint_from_dict(row: Mapping[str, Any]) -> Checkpoint:
    return Checkpoint(
        horizon_label=row["horizon_label"],
        horizon_origin=EventOrigin(row["horizon_origin"]),
        target_timestamp=row.get("target_timestamp"),
        observed_timestamp=row.get("observed_timestamp"),
        observed_price=row.get("observed_price"),
        gross_return=row.get("gross_return"),
        net_return=row.get("net_return"),
        mfe=row.get("mfe"),
        mae=row.get("mae"),
        completeness=CheckpointCompleteness(row.get("completeness", CheckpointCompleteness.MISSING.value)),
        source=row.get("source", ""),
        return_unit=ReturnUnit(row.get("return_unit", CANONICAL_RETURN_UNIT.value)),
        horizon_set_id=row.get("horizon_set_id", ""),
        metric_kind=CheckpointMetricKind(row.get("metric_kind", CheckpointMetricKind.PRICE_BASED.value)),
    )


def _record_link_from_dict(row: Mapping[str, Any]) -> RecordLink:
    raw = dict(row)
    return RecordLink(relation_type=raw["relation_type"], target_record_id=raw["target_record_id"], provenance=raw.get("provenance", ""))


def _entry_from_dict(row: Mapping[str, Any] | None) -> EntryObservation | None:
    if row is None:
        return None
    return EntryObservation(
        entry_time=row.get("entry_time"),
        entry_price=row.get("entry_price"),
        entry_authority=EntryAuthority(row.get("entry_authority", EntryAuthority.CANDIDATE_PRICE.value)),
    )


def _exit_from_dict(row: Mapping[str, Any] | None) -> ExitObservation | None:
    if row is None:
        return None
    return ExitObservation(
        exit_time=row.get("exit_time"),
        exit_price=row.get("exit_price"),
        exit_price_authority=EntryAuthority(row.get("exit_price_authority", EntryAuthority.CANDIDATE_PRICE.value)),
        exit_reason=row.get("exit_reason", ""),
    )


def _quality_from_dict(row: Mapping[str, Any] | None) -> EvaluationQuality:
    row = dict(row or {})
    return EvaluationQuality(
        sample_status=SampleStatus(row.get("sample_status", SampleStatus.ELIGIBLE.value)),
        evidence_status=EvidenceStatus(row.get("evidence_status", EvidenceStatus.INSUFFICIENT.value)),
        contaminated=bool(row.get("contaminated", False)),
        exclusion_reason=row.get("exclusion_reason", ""),
        completeness=row.get("completeness", ""),
    )


def _cost_from_dict(row: Mapping[str, Any] | None) -> EvaluationCost:
    row = dict(row or {})
    return EvaluationCost(
        cost_profile_id=row.get("cost_profile_id", ""),
        applied_cost=row.get("applied_cost"),
        cost_unit=ReturnUnit(row.get("cost_unit", CANONICAL_RETURN_UNIT.value)),
    )


def _provenance_from_dict(row: Mapping[str, Any] | None) -> Provenance:
    return Provenance(**dict(row or {}))


def _event_ref_from_dict(row: Mapping[str, Any]) -> EventRef:
    return EventRef.from_dict(dict(row))


# --------------------------------------------------------------------------
# EpisodeRecord
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EpisodeIdentity:
    event: EventRef
    hypothesis_id: str = ""
    experiment_id: str = ""
    evaluator_version: str = ""
    evaluation_subject_id: str = ""
    evaluation_record_id: str = ""
    cross_program_link_key: str = ""
    source_run_id: str = ""


def _episode_identity_from_dict(row: Mapping[str, Any]) -> EpisodeIdentity:
    raw = dict(row)
    return EpisodeIdentity(
        event=_event_ref_from_dict(raw["event"]),
        hypothesis_id=raw.get("hypothesis_id", ""),
        experiment_id=raw.get("experiment_id", ""),
        evaluator_version=raw.get("evaluator_version", ""),
        evaluation_subject_id=raw.get("evaluation_subject_id", ""),
        evaluation_record_id=raw.get("evaluation_record_id", ""),
        cross_program_link_key=raw.get("cross_program_link_key", ""),
        source_run_id=raw.get("source_run_id", ""),
    )


@dataclass(frozen=True)
class EpisodeRecord:
    RECORD_KIND = RecordKind.EPISODE

    identity: EpisodeIdentity
    trading_date: str
    symbol: str
    observation_type: ObservationType
    execution_mode: ExecutionMode
    side: str = ""
    entry: EntryObservation | None = None
    exit: ExitObservation | None = None
    event_date_relation: EventDateRelation = EventDateRelation.SAME_DAY
    checkpoints: tuple[Checkpoint, ...] = field(default_factory=tuple)
    cost: EvaluationCost = field(default_factory=EvaluationCost)
    quality: EvaluationQuality = field(default_factory=EvaluationQuality)
    provenance: Provenance = field(default_factory=Provenance)
    related_records: tuple[RecordLink, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_episode(self)

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe(_as_plain_dict(self) | {"record_kind": self.RECORD_KIND.value})

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "EpisodeRecord":
        raw = dict(payload)
        return EpisodeRecord(
            identity=_episode_identity_from_dict(raw["identity"]),
            trading_date=raw["trading_date"],
            symbol=raw["symbol"],
            observation_type=ObservationType(raw["observation_type"]),
            execution_mode=ExecutionMode(raw["execution_mode"]),
            side=raw.get("side", ""),
            entry=_entry_from_dict(raw.get("entry")),
            exit=_exit_from_dict(raw.get("exit")),
            event_date_relation=EventDateRelation(raw.get("event_date_relation", EventDateRelation.SAME_DAY.value)),
            checkpoints=tuple(_checkpoint_from_dict(row) for row in raw.get("checkpoints") or ()),
            cost=_cost_from_dict(raw.get("cost")),
            quality=_quality_from_dict(raw.get("quality")),
            provenance=_provenance_from_dict(raw.get("provenance")),
            related_records=tuple(_record_link_from_dict(row) for row in raw.get("related_records") or ()),
            metadata=dict(raw.get("metadata") or {}),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
        )


_OBSERVATION_ONLY_FORBIDDEN_AUTHORITY = frozenset({EntryAuthority.BROKER_FILL, EntryAuthority.MOCK_FILL})
_SHADOW_FORBIDDEN_AUTHORITY = frozenset({EntryAuthority.BROKER_FILL, EntryAuthority.MOCK_FILL})
_ENTRY_TYPES_INCOMPATIBLE_WITH_DIAGNOSTIC = frozenset({ObservationType.CONTROLLED_ENTRY})
_PENDING_LIKE_COMPLETENESS = frozenset(
    {CheckpointCompleteness.PENDING, CheckpointCompleteness.STALE, CheckpointCompleteness.PARTIAL, CheckpointCompleteness.MISSING}
)
_SAME_DAY_ONLY = frozenset({EventDateRelation.SAME_DAY})
_PRICE_OUTCOME_FIELDS = ("gross_return", "net_return", "mfe", "mae")


def _validate_checkpoint_provenance(checkpoint: Checkpoint) -> None:
    """Fix3 M3: an OBSERVED, PRICE_BASED checkpoint carrying ANY outcome field
    (gross_return/net_return/mfe/mae -- not just gross_return, as Fix2 only
    checked) must have both observed_timestamp and observed_price. An
    AGGREGATE_ONLY checkpoint is the explicit, declared escape hatch."""

    if checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return
    if checkpoint.observed_timestamp is None:
        raise CanonicalRecordValidationError(
            f"checkpoint {checkpoint.horizon_label!r} is OBSERVED but has no observed_timestamp"
        )
    if checkpoint.metric_kind is CheckpointMetricKind.AGGREGATE_ONLY:
        return
    has_outcome = any(getattr(checkpoint, name) is not None for name in _PRICE_OUTCOME_FIELDS)
    if has_outcome and checkpoint.observed_price is None:
        raise CanonicalRecordValidationError(
            f"checkpoint {checkpoint.horizon_label!r} is OBSERVED/PRICE_BASED with an outcome field "
            f"({[name for name in _PRICE_OUTCOME_FIELDS if getattr(checkpoint, name) is not None]}) but no observed_price"
        )


def _validate_episode(episode: EpisodeRecord) -> None:
    if not episode.symbol:
        raise CanonicalRecordValidationError("EpisodeRecord.symbol is required (use AggregateRecord for symbol-less statistics)")
    canonical_symbol = _identity.canonicalize_symbol(episode.symbol)
    if canonical_symbol != episode.symbol:
        raise CanonicalRecordValidationError(
            f"symbol={episode.symbol!r} is not in canonical form (expected {canonical_symbol!r}) -- "
            "use build_episode_record() rather than constructing the record with a raw symbol"
        )
    canonical_date = _identity.canonicalize_trading_date(episode.trading_date)
    if canonical_date != episode.trading_date:
        raise CanonicalRecordValidationError(f"trading_date={episode.trading_date!r} is not in canonical YYYY-MM-DD form")
    # episode.related_records: RecordLink.__post_init__ already validated
    # relation_type/target_record_id format. The remaining structural (not
    # referential -- see relations.py) check possible at this level alone:
    for link in episode.related_records:
        if link.target_record_id == episode.identity.evaluation_record_id:
            raise CanonicalRecordValidationError(
                f"related_records entry targets its own record ({link.target_record_id!r}) -- a relation cannot self-reference"
            )

    _validate_event_ref(episode.identity.event)
    _validate_evaluation_ids(
        canonical_event_id=episode.identity.event.canonical_event_id,
        hypothesis_id=episode.identity.hypothesis_id,
        observation_type=episode.observation_type,
        execution_mode=episode.execution_mode,
        evaluation_subject_id=episode.identity.evaluation_subject_id,
        evaluation_record_id=episode.identity.evaluation_record_id,
    )

    mode = episode.execution_mode
    if episode.observation_type is ObservationType.ACTUAL_TRADE and episode.entry is None:
        raise CanonicalRecordValidationError("ACTUAL_TRADE requires an entry observation")
    if episode.observation_type is ObservationType.EXIT_EVENT and episode.exit is None:
        raise CanonicalRecordValidationError("EXIT_EVENT requires an exit observation")

    if episode.entry is not None:
        authority = episode.entry.entry_authority
        if mode is ExecutionMode.OBSERVATION_ONLY and authority in _OBSERVATION_ONLY_FORBIDDEN_AUTHORITY:
            raise CanonicalRecordValidationError(
                f"execution_mode=OBSERVATION_ONLY cannot pair with entry_authority={authority.value} "
                "(an observation episode cannot claim an authoritative real or mock fill occurred)"
            )
        if mode is ExecutionMode.SHADOW and authority in _SHADOW_FORBIDDEN_AUTHORITY:
            raise CanonicalRecordValidationError(
                f"execution_mode=SHADOW cannot pair with entry_authority={authority.value} "
                "(a shadow episode never actually executed anything)"
            )
        if episode.observation_type is ObservationType.ACTUAL_TRADE:
            if authority in (EntryAuthority.BROKER_FILL, EntryAuthority.MOCK_FILL) and episode.entry.entry_price is None:
                raise CanonicalRecordValidationError(
                    f"ACTUAL_TRADE with {authority.value} entry_authority requires an entry_price"
                )
        if authority is EntryAuthority.SUBMITTED_INTENT and mode not in (ExecutionMode.CONTROLLED_MOCK, ExecutionMode.BROKER_LIVE, ExecutionMode.DIAGNOSTIC):
            raise CanonicalRecordValidationError(
                "entry_authority=SUBMITTED_INTENT requires execution_mode in {CONTROLLED_MOCK, BROKER_LIVE, DIAGNOSTIC} "
                "(a submission implies a real order attempt was made, even if unconfirmed)"
            )
        if episode.entry.entry_time is not None:
            _validate_event_date_relation(
                trading_date=episode.trading_date, entry_time=episode.entry.entry_time,
                event_date_relation=episode.event_date_relation,
            )

    if episode.observation_type in _ENTRY_TYPES_INCOMPATIBLE_WITH_DIAGNOSTIC and mode is ExecutionMode.DIAGNOSTIC:
        raise CanonicalRecordValidationError(
            f"observation_type={episode.observation_type.value} cannot pair with execution_mode=DIAGNOSTIC "
            "(a controlled entry is a real order attempt, never merely diagnostic)"
        )

    for checkpoint in episode.checkpoints:
        _validate_checkpoint_provenance(checkpoint)

    if episode.quality.sample_status is SampleStatus.COMPLETE:
        pending = [cp.horizon_label for cp in episode.checkpoints if cp.completeness in _PENDING_LIKE_COMPLETENESS]
        if pending:
            raise CanonicalRecordValidationError(
                f"quality.sample_status=COMPLETE contradicts non-observed checkpoint(s): {pending}"
            )


def _validate_event_date_relation(*, trading_date: str, entry_time: int, event_date_relation: EventDateRelation) -> None:
    actual_date = _identity.epoch_seconds_to_kst_date(entry_time)
    same_day = actual_date == trading_date
    declared_same_day = event_date_relation in _SAME_DAY_ONLY
    if same_day and not declared_same_day:
        raise CanonicalRecordValidationError(
            f"event_date_relation={event_date_relation.value} was declared but entry_time's KST date "
            f"({actual_date}) actually equals trading_date ({trading_date}) -- declare SAME_DAY instead"
        )
    if not same_day and declared_same_day:
        raise CanonicalRecordValidationError(
            f"event_date_relation=SAME_DAY but entry_time's KST date ({actual_date}) does not match "
            f"trading_date ({trading_date}) -- declare OVERNIGHT_CARRY/T_PLUS_1/T_PLUS_2/OTHER_EXPLICIT"
        )


# --------------------------------------------------------------------------
# PairRecord
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PairIdentity:
    pair_event: EventRef
    left_event: EventRef
    right_event: EventRef
    pair_type: str = ""
    hypothesis_id: str = ""
    evaluator_version: str = ""
    evaluation_subject_id: str = ""
    evaluation_record_id: str = ""
    cross_program_link_key: str = ""


def _pair_identity_from_dict(row: Mapping[str, Any]) -> PairIdentity:
    raw = dict(row)
    return PairIdentity(
        pair_event=_event_ref_from_dict(raw["pair_event"]),
        left_event=_event_ref_from_dict(raw["left_event"]),
        right_event=_event_ref_from_dict(raw["right_event"]),
        pair_type=raw.get("pair_type", ""),
        hypothesis_id=raw.get("hypothesis_id", ""),
        evaluator_version=raw.get("evaluator_version", ""),
        evaluation_subject_id=raw.get("evaluation_subject_id", ""),
        evaluation_record_id=raw.get("evaluation_record_id", ""),
        cross_program_link_key=raw.get("cross_program_link_key", ""),
    )


@dataclass(frozen=True)
class PairSide:
    """Fix2 #13: each side carries its OWN event reference, symbol, and timestamp --
    a real Strategist Stage2 record confirms left/right can be different symbols
    with independently-timed native decisions, never one shared identity."""

    event: EventRef
    symbol: str
    observation_type: ObservationType
    execution_mode: ExecutionMode
    entry: EntryObservation | None = None
    checkpoints: tuple[Checkpoint, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # UEF-1 PAIRSIDE FINAL PATCH: the public PairSide constructor must
        # reject a production-invalid symbol (e.g. "5930") on its own --
        # PairRecord.__post_init__ already enforces strict canonical-form
        # equality once both sides are wrapped, but that check never ran
        # for a bare PairSide built outside a PairRecord. This call reuses
        # the same production symbol authority (canonicalize_symbol, which
        # itself defers to normalize_symbol(allow_test_symbols=False)) only
        # to reject symbols that are not a legitimate representation at
        # all; it deliberately does not require self.symbol to already be
        # in canonical form (e.g. "A005930" still passes here), since that
        # stricter equality check remains PairRecord's own responsibility.
        if not self.symbol:
            raise CanonicalRecordValidationError("PairSide.symbol is required")
        _identity.canonicalize_symbol(self.symbol)


def _pair_side_from_dict(row: Mapping[str, Any]) -> PairSide:
    raw = dict(row)
    return PairSide(
        event=_event_ref_from_dict(raw["event"]),
        symbol=raw["symbol"],
        observation_type=ObservationType(raw["observation_type"]),
        execution_mode=ExecutionMode(raw["execution_mode"]),
        entry=_entry_from_dict(raw.get("entry")),
        checkpoints=tuple(_checkpoint_from_dict(row) for row in raw.get("checkpoints") or ()),
    )


@dataclass(frozen=True)
class PairRecord:
    RECORD_KIND = RecordKind.PAIR

    identity: PairIdentity
    trading_date: str
    left: PairSide
    right: PairSide
    pair_execution_mode: ExecutionMode = ExecutionMode.DIAGNOSTIC
    delta_metric_label: str = ""
    delta_value: float | None = None
    delta_horizon: str = ""
    quality: EvaluationQuality = field(default_factory=EvaluationQuality)
    cost: EvaluationCost = field(default_factory=EvaluationCost)
    provenance: Provenance = field(default_factory=Provenance)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.trading_date:
            raise CanonicalRecordValidationError("PairRecord.trading_date is required")
        if not self.left.symbol or not self.right.symbol:
            raise CanonicalRecordValidationError("PairRecord requires both left.symbol and right.symbol")
        for side_name, side in (("left", self.left), ("right", self.right)):
            canonical = _identity.canonicalize_symbol(side.symbol)
            if canonical != side.symbol:
                raise CanonicalRecordValidationError(
                    f"{side_name}.symbol={side.symbol!r} is not in canonical form (expected {canonical!r})"
                )
            for checkpoint in side.checkpoints:
                _validate_checkpoint_provenance(checkpoint)
        for ref in (self.identity.pair_event, self.identity.left_event, self.identity.right_event, self.left.event, self.right.event):
            _validate_event_ref(ref)
        if self.identity.left_event.canonical_event_id != self.left.event.canonical_event_id:
            raise CanonicalRecordValidationError("identity.left_event must match left.event")
        if self.identity.right_event.canonical_event_id != self.right.event.canonical_event_id:
            raise CanonicalRecordValidationError("identity.right_event must match right.event")
        _validate_evaluation_ids(
            canonical_event_id=self.identity.pair_event.canonical_event_id,
            hypothesis_id=self.identity.hypothesis_id,
            observation_type="PAIR",
            execution_mode=self.pair_execution_mode,  # Closure Reset Group #15: the pair's OWN execution
            # semantics, independent of either side -- never derived from
            # whichever side happens to be "left" by construction accident.
            evaluation_subject_id=self.identity.evaluation_subject_id,
            evaluation_record_id=self.identity.evaluation_record_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe(_as_plain_dict(self) | {"record_kind": self.RECORD_KIND.value})

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "PairRecord":
        raw = dict(payload)
        return PairRecord(
            identity=_pair_identity_from_dict(raw["identity"]),
            trading_date=raw["trading_date"],
            left=_pair_side_from_dict(raw["left"]),
            right=_pair_side_from_dict(raw["right"]),
            pair_execution_mode=ExecutionMode(raw.get("pair_execution_mode", ExecutionMode.DIAGNOSTIC.value)),
            delta_metric_label=raw.get("delta_metric_label", ""),
            delta_value=raw.get("delta_value"),
            delta_horizon=raw.get("delta_horizon", ""),
            quality=_quality_from_dict(raw.get("quality")),
            cost=_cost_from_dict(raw.get("cost")),
            provenance=_provenance_from_dict(raw.get("provenance")),
            metadata=dict(raw.get("metadata") or {}),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
        )


# --------------------------------------------------------------------------
# SequenceRecord
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SequenceIdentity:
    sequence_event: EventRef
    hypothesis_id: str = ""
    evaluator_version: str = ""
    evaluation_subject_id: str = ""
    evaluation_record_id: str = ""
    cross_program_link_key: str = ""


def _sequence_identity_from_dict(row: Mapping[str, Any]) -> SequenceIdentity:
    raw = dict(row)
    return SequenceIdentity(
        sequence_event=_event_ref_from_dict(raw["sequence_event"]),
        hypothesis_id=raw.get("hypothesis_id", ""),
        evaluator_version=raw.get("evaluator_version", ""),
        evaluation_subject_id=raw.get("evaluation_subject_id", ""),
        evaluation_record_id=raw.get("evaluation_record_id", ""),
        cross_program_link_key=raw.get("cross_program_link_key", ""),
    )


@dataclass(frozen=True)
class SequenceLeg:
    leg_id: str
    event: EventRef
    order_index: int
    parent_leg_id: str = ""
    relation_to_previous: str = ""


def _sequence_leg_from_dict(row: Mapping[str, Any]) -> SequenceLeg:
    raw = dict(row)
    return SequenceLeg(
        leg_id=raw["leg_id"],
        event=_event_ref_from_dict(raw["event"]),
        order_index=int(raw["order_index"]),
        parent_leg_id=raw.get("parent_leg_id", ""),
        relation_to_previous=raw.get("relation_to_previous", ""),
    )


_NO_PARENT_RELATION_ALLOWED = frozenset({"", "NOT_APPLICABLE"})


def _validate_sequence_legs(legs: tuple["SequenceLeg", ...]) -> None:
    """Fix3 M2/#18-20: unique leg_id, unique+positive+strictly-increasing
    order_index, parent_leg_id must reference an actual leg in this same
    sequence and must precede its child, no self-parent, and a leg
    declaring no parent must not simultaneously declare a real
    relation_to_previous (a minimal consistency check -- not a trading
    policy)."""

    leg_ids = [leg.leg_id for leg in legs]
    if len(set(leg_ids)) != len(leg_ids):
        raise CanonicalRecordValidationError("SequenceRecord.legs must have unique leg_id values")
    orders = [leg.order_index for leg in legs]
    if len(set(orders)) != len(orders):
        raise CanonicalRecordValidationError("SequenceRecord.legs must have unique order_index values")
    if any(order <= 0 for order in orders):
        raise CanonicalRecordValidationError("SequenceRecord.legs order_index must be a positive integer")
    if orders != sorted(orders):
        raise CanonicalRecordValidationError("SequenceRecord.legs must be ordered by order_index")

    order_by_leg_id = {leg.leg_id: leg.order_index for leg in legs}
    for leg in legs:
        if leg.parent_leg_id:
            if leg.parent_leg_id == leg.leg_id:
                raise CanonicalRecordValidationError(f"leg {leg.leg_id!r} cannot declare itself as its own parent_leg_id")
            if leg.parent_leg_id not in order_by_leg_id:
                raise CanonicalRecordValidationError(
                    f"leg {leg.leg_id!r} references parent_leg_id={leg.parent_leg_id!r}, which is not a leg in this sequence"
                )
            if order_by_leg_id[leg.parent_leg_id] >= leg.order_index:
                raise CanonicalRecordValidationError(
                    f"leg {leg.leg_id!r}'s parent_leg_id={leg.parent_leg_id!r} must precede it "
                    f"(parent.order_index={order_by_leg_id[leg.parent_leg_id]} >= this leg's order_index={leg.order_index})"
                )
        elif leg.relation_to_previous not in _NO_PARENT_RELATION_ALLOWED:
            raise CanonicalRecordValidationError(
                f"leg {leg.leg_id!r} has no parent_leg_id but declares relation_to_previous={leg.relation_to_previous!r}"
            )


@dataclass(frozen=True)
class SequenceRecord:
    """Fix2 #15: legs carry their own EventRef (pointing at that leg's own real trade)
    plus explicit order_index/parent_leg_id/relation_to_previous -- a real
    same_symbol_sequences artifact with >=2 legs is required to exercise this
    (see tests), a single-leg fixture is not accepted as proof."""

    RECORD_KIND = RecordKind.SEQUENCE

    identity: SequenceIdentity
    trading_date: str
    symbol: str
    legs: tuple[SequenceLeg, ...] = field(default_factory=tuple)
    sequence_metrics: Mapping[str, Any] = field(default_factory=dict)
    quality: EvaluationQuality = field(default_factory=EvaluationQuality)
    provenance: Provenance = field(default_factory=Provenance)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.symbol:
            raise CanonicalRecordValidationError("SequenceRecord.symbol is required")
        canonical_symbol = _identity.canonicalize_symbol(self.symbol)
        if canonical_symbol != self.symbol:
            raise CanonicalRecordValidationError(f"symbol={self.symbol!r} is not in canonical form (expected {canonical_symbol!r})")
        if not self.trading_date:
            raise CanonicalRecordValidationError("SequenceRecord.trading_date is required")
        _validate_event_ref(self.identity.sequence_event)
        for leg in self.legs:
            _validate_event_ref(leg.event)
        _validate_sequence_legs(self.legs)
        _validate_evaluation_ids(
            canonical_event_id=self.identity.sequence_event.canonical_event_id,
            hypothesis_id=self.identity.hypothesis_id,
            observation_type="SEQUENCE",
            execution_mode="BROKER_LIVE",
            evaluation_subject_id=self.identity.evaluation_subject_id,
            evaluation_record_id=self.identity.evaluation_record_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe(_as_plain_dict(self) | {"record_kind": self.RECORD_KIND.value})

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "SequenceRecord":
        raw = dict(payload)
        return SequenceRecord(
            identity=_sequence_identity_from_dict(raw["identity"]),
            trading_date=raw["trading_date"],
            symbol=raw["symbol"],
            legs=tuple(_sequence_leg_from_dict(row) for row in raw.get("legs") or ()),
            sequence_metrics=dict(raw.get("sequence_metrics") or {}),
            quality=_quality_from_dict(raw.get("quality")),
            provenance=_provenance_from_dict(raw.get("provenance")),
            metadata=dict(raw.get("metadata") or {}),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
        )


# --------------------------------------------------------------------------
# AggregateRecord
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateIdentity:
    aggregate_ref: EventRef
    aggregation_scope: str = ""
    hypothesis_id: str = ""
    evaluator_version: str = ""
    evaluation_subject_id: str = ""
    evaluation_record_id: str = ""

    @property
    def canonical_aggregate_id(self) -> str:
        """Closure Reset LOW/#16: the semantically-correct name for this value.

        ``aggregate_ref.canonical_event_id`` is the underlying field (the
        same ``EventRef`` shape is reused across all four record kinds for
        implementation consistency), but an aggregate has no market
        *event* -- calling it a "canonical_event_id" invites exactly the
        Work-Package-B mistake of treating an aggregate as if it were one
        episode. This property is the name every caller should actually
        read and write in code/docs; the underlying field name is kept
        only for internal structural consistency with ``EventRef``.
        """

        return self.aggregate_ref.canonical_event_id


def _aggregate_identity_from_dict(row: Mapping[str, Any]) -> AggregateIdentity:
    raw = dict(row)
    return AggregateIdentity(
        aggregate_ref=_event_ref_from_dict(raw["aggregate_ref"]),
        aggregation_scope=raw.get("aggregation_scope", ""),
        hypothesis_id=raw.get("hypothesis_id", ""),
        evaluator_version=raw.get("evaluator_version", ""),
        evaluation_subject_id=raw.get("evaluation_subject_id", ""),
        evaluation_record_id=raw.get("evaluation_record_id", ""),
    )


@dataclass(frozen=True)
class AggregateRecord:
    """Fix2 #16/#17/#18: never requires a market-event identity (no symbol/trading_date
    forced onto ``identity``). ``lineage_status`` (FULL/PARTIAL/UNKNOWN) replaces
    Fix1's boolean and is validated for internal consistency against
    ``episode_count``/``source_episode_ids``."""

    RECORD_KIND = RecordKind.AGGREGATE

    identity: AggregateIdentity
    aggregation_window_start: str
    aggregation_window_end: str = ""
    symbol: str = ""
    episode_count: int = 0
    source_episode_ids: tuple[str, ...] = field(default_factory=tuple)
    lineage_status: LineageStatus = LineageStatus.UNKNOWN
    metric_semantics: str = "LEGACY_SOURCE"
    metrics: Mapping[str, Any] = field(default_factory=dict)
    quality: EvaluationQuality = field(default_factory=EvaluationQuality)
    provenance: Provenance = field(default_factory=Provenance)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.identity.aggregation_scope:
            raise CanonicalRecordValidationError("AggregateIdentity.aggregation_scope is required")
        if not self.aggregation_window_start:
            raise CanonicalRecordValidationError("AggregateRecord.aggregation_window_start is required")
        _validate_event_ref(self.identity.aggregate_ref)
        _validate_evaluation_ids(
            canonical_event_id=self.identity.aggregate_ref.canonical_event_id,
            hypothesis_id=self.identity.hypothesis_id,
            observation_type="AGGREGATE",
            execution_mode="OBSERVATION_ONLY",
            evaluation_subject_id=self.identity.evaluation_subject_id,
            evaluation_record_id=self.identity.evaluation_record_id,
        )
        if self.symbol:
            canonical_symbol = _identity.canonicalize_symbol(self.symbol)
            if canonical_symbol != self.symbol:
                raise CanonicalRecordValidationError(f"symbol={self.symbol!r} is not in canonical form (expected {canonical_symbol!r})")
        if self.episode_count < 0:
            raise CanonicalRecordValidationError("AggregateRecord.episode_count must be >= 0")
        if len(set(self.source_episode_ids)) != len(self.source_episode_ids):
            raise CanonicalRecordValidationError(
                "AggregateRecord.source_episode_ids must not contain duplicates "
                "(a repeated id would inflate lineage coverage beyond what is actually known)"
            )
        coverage = len(self.source_episode_ids)
        if self.episode_count == 0 and self.lineage_status is not LineageStatus.UNKNOWN:
            raise CanonicalRecordValidationError(
                f"episode_count=0 is only compatible with lineage_status=UNKNOWN, got {self.lineage_status.value}"
            )
        if self.lineage_status is LineageStatus.FULL:
            if coverage != self.episode_count:
                raise CanonicalRecordValidationError(
                    f"lineage_status=FULL requires len(source_episode_ids)==episode_count, got {coverage} vs {self.episode_count}"
                )
        elif self.lineage_status is LineageStatus.PARTIAL:
            if not (0 < coverage < self.episode_count):
                raise CanonicalRecordValidationError(
                    f"lineage_status=PARTIAL requires 0 < len(source_episode_ids) < episode_count, got {coverage} vs {self.episode_count}"
                )
        elif self.lineage_status is LineageStatus.UNKNOWN:
            if coverage != 0:
                raise CanonicalRecordValidationError(
                    "lineage_status=UNKNOWN requires source_episode_ids to be empty (nothing is actually known)"
                )

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe(_as_plain_dict(self) | {"record_kind": self.RECORD_KIND.value})

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "AggregateRecord":
        raw = dict(payload)
        return AggregateRecord(
            identity=_aggregate_identity_from_dict(raw["identity"]),
            aggregation_window_start=raw["aggregation_window_start"],
            aggregation_window_end=raw.get("aggregation_window_end", ""),
            symbol=raw.get("symbol", ""),
            episode_count=int(raw.get("episode_count", 0)),
            source_episode_ids=tuple(raw.get("source_episode_ids") or ()),
            lineage_status=LineageStatus(raw.get("lineage_status", LineageStatus.UNKNOWN.value)),
            metric_semantics=raw.get("metric_semantics", "LEGACY_SOURCE"),
            metrics=dict(raw.get("metrics") or {}),
            quality=_quality_from_dict(raw.get("quality")),
            provenance=_provenance_from_dict(raw.get("provenance")),
            metadata=dict(raw.get("metadata") or {}),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
        )


CanonicalEvaluationRecord = Union[EpisodeRecord, PairRecord, SequenceRecord, AggregateRecord]

_RECORD_CLASS_BY_KIND = {
    RecordKind.EPISODE.value: EpisodeRecord,
    RecordKind.PAIR.value: PairRecord,
    RecordKind.SEQUENCE.value: SequenceRecord,
    RecordKind.AGGREGATE.value: AggregateRecord,
}


def serialize_record(record: CanonicalEvaluationRecord) -> dict[str, Any]:
    return record.to_dict()


def deserialize_record(payload: Mapping[str, Any]) -> CanonicalEvaluationRecord:
    kind = str(payload.get("record_kind") or "")
    record_class = _RECORD_CLASS_BY_KIND.get(kind)
    if record_class is None:
        raise CanonicalRecordValidationError(f"unknown record_kind: {kind!r}")
    return record_class.from_dict(payload)


# --------------------------------------------------------------------------
# Builder helpers -- the recommended construction path (Fix2 #44)
# --------------------------------------------------------------------------


def build_episode_record(
    *,
    source_namespace: str,
    hypothesis_id: str,
    observation_type: ObservationType,
    execution_mode: ExecutionMode,
    trading_date: str,
    symbol: str,
    native_id: Any = None,
    derived_fields: dict[str, "_identity.DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
    event_ref: EventRef | None = None,
    evaluator_version: str = "",
    experiment_id: str = "",
    source_run_id: str = "",
    **episode_kwargs: Any,
) -> EpisodeRecord:
    """Build an ``EpisodeRecord`` with a fully self-consistent identity in one call.

    ``event_ref`` -- pass an already-built ``EventRef`` (e.g. from
    :func:`~.identity.build_fixed_clock_event_ref` or
    :func:`~.identity.build_derived_event_ref`) to use it directly instead
    of building one from ``native_id``/``derived_fields`` here. Prefer
    this whenever a typed builder applies -- it is the only way to get
    Fix3's date/symbol/clock-label canonicalization for the episode's own
    identity.
    """

    event = event_ref if event_ref is not None else _identity.build_event_ref(
        source_namespace=source_namespace, native_id=native_id,
        derived_fields=derived_fields, derivation_version=derivation_version,
    )
    subject = _identity.evaluation_subject_id(
        canonical_event_id=event.canonical_event_id, hypothesis_id=hypothesis_id, observation_type=observation_type,
    )
    record_id = _identity.evaluation_record_id(evaluation_subject_id=subject, execution_mode=execution_mode)
    identity = EpisodeIdentity(
        event=event, hypothesis_id=hypothesis_id, experiment_id=experiment_id, evaluator_version=evaluator_version,
        evaluation_subject_id=subject, evaluation_record_id=record_id, source_run_id=source_run_id,
    )
    return EpisodeRecord(
        identity=identity, trading_date=_identity.canonicalize_trading_date(trading_date),
        symbol=_identity.canonicalize_symbol(symbol),
        observation_type=observation_type, execution_mode=execution_mode, **episode_kwargs,
    )


def build_pair_record(
    *,
    source_namespace: str,
    hypothesis_id: str,
    pair_type: str,
    trading_date: str,
    left: PairSide,
    right: PairSide,
    native_id: Any = None,
    derived_fields: dict[str, "_identity.DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
    evaluator_version: str = "",
    pair_execution_mode: ExecutionMode = ExecutionMode.DIAGNOSTIC,
    **pair_kwargs: Any,
) -> PairRecord:
    """Build a ``PairRecord`` with a fully self-consistent identity in one call.

    ``left.event``/``right.event`` are taken as already-built (each side's
    own native/derived event) -- the pair's OWN event (``pair_event``) is
    built here from ``native_id``/``derived_fields`` (e.g. the Q9
    decision_id that spawned the before/after refresh comparison).

    ``pair_execution_mode`` is the pair's OWN execution semantics (Closure
    Reset Group #15) -- independent of ``left.execution_mode``/
    ``right.execution_mode``, which describe each SIDE, not the
    comparison as a whole. Defaults to ``DIAGNOSTIC`` (every real pair
    use-case so far -- Strategist Stage2's before/after comparison -- is a
    diagnostic, never an execution attempt in its own right).
    """

    pair_event = _identity.build_event_ref(
        source_namespace=source_namespace, native_id=native_id,
        derived_fields=derived_fields, derivation_version=derivation_version,
    )
    subject = _identity.evaluation_subject_id(canonical_event_id=pair_event.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="PAIR")
    record_id = _identity.evaluation_record_id(evaluation_subject_id=subject, execution_mode=pair_execution_mode)
    identity = PairIdentity(
        pair_event=pair_event, left_event=left.event, right_event=right.event, pair_type=pair_type,
        hypothesis_id=hypothesis_id, evaluator_version=evaluator_version,
        evaluation_subject_id=subject, evaluation_record_id=record_id,
    )
    return PairRecord(identity=identity, trading_date=trading_date, left=left, right=right, pair_execution_mode=pair_execution_mode, **pair_kwargs)


def build_sequence_record(
    *,
    source_namespace: str,
    hypothesis_id: str,
    trading_date: str,
    symbol: str,
    legs: tuple[SequenceLeg, ...],
    native_id: Any = None,
    derived_fields: dict[str, "_identity.DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
    evaluator_version: str = "",
    **sequence_kwargs: Any,
) -> SequenceRecord:
    """Build a ``SequenceRecord`` with a fully self-consistent identity in one call."""

    sequence_event = _identity.build_event_ref(
        source_namespace=source_namespace, native_id=native_id,
        derived_fields=derived_fields, derivation_version=derivation_version,
    )
    subject = _identity.evaluation_subject_id(canonical_event_id=sequence_event.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="SEQUENCE")
    record_id = _identity.evaluation_record_id(evaluation_subject_id=subject, execution_mode="BROKER_LIVE")
    identity = SequenceIdentity(
        sequence_event=sequence_event, hypothesis_id=hypothesis_id, evaluator_version=evaluator_version,
        evaluation_subject_id=subject, evaluation_record_id=record_id,
    )
    return SequenceRecord(
        identity=identity, trading_date=_identity.canonicalize_trading_date(trading_date),
        symbol=_identity.canonicalize_symbol(symbol), legs=legs, **sequence_kwargs,
    )


def build_aggregate_record(
    *,
    source_namespace: str,
    hypothesis_id: str,
    aggregation_scope: str,
    aggregation_window_start: str,
    native_id: Any = None,
    derived_fields: dict[str, "_identity.DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
    evaluator_version: str = "",
    **aggregate_kwargs: Any,
) -> AggregateRecord:
    """Build an ``AggregateRecord`` with a fully self-consistent identity in one call.

    Never requires (or accepts) a symbol/trading_date as part of identity --
    an aggregate has no market event of its own (Fix2 #16).
    """

    aggregate_ref = _identity.build_event_ref(
        source_namespace=source_namespace, native_id=native_id,
        derived_fields=derived_fields, derivation_version=derivation_version,
    )
    subject = _identity.evaluation_subject_id(canonical_event_id=aggregate_ref.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="AGGREGATE")
    record_id = _identity.evaluation_record_id(evaluation_subject_id=subject, execution_mode="OBSERVATION_ONLY")
    identity = AggregateIdentity(
        aggregate_ref=aggregate_ref, aggregation_scope=aggregation_scope, hypothesis_id=hypothesis_id,
        evaluator_version=evaluator_version, evaluation_subject_id=subject, evaluation_record_id=record_id,
    )
    return AggregateRecord(identity=identity, aggregation_window_start=aggregation_window_start, **aggregate_kwargs)


__all__ = [
    "CanonicalRecordValidationError",
    "CanonicalSerializationError",
    "CanonicalEvaluationRecord",
    "Provenance",
    "EntryObservation",
    "ExitObservation",
    "Checkpoint",
    "EvaluationCost",
    "EvaluationQuality",
    "RecordLink",
    "EpisodeIdentity",
    "EpisodeRecord",
    "PairIdentity",
    "PairSide",
    "PairRecord",
    "SequenceIdentity",
    "SequenceLeg",
    "SequenceRecord",
    "AggregateIdentity",
    "AggregateRecord",
    "serialize_record",
    "deserialize_record",
    "build_episode_record",
    "build_pair_record",
    "build_sequence_record",
    "build_aggregate_record",
]
