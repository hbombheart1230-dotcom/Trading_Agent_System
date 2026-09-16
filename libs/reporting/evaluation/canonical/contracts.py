"""UEF-1 Work Package A Fix2 -- canonical evaluation terminology.

Fix2 responds to Codex's independent re-audit of Fix1
(REJECT_WORK_PACKAGE_A, CRITICAL:0 HIGH:5 MEDIUM:5 LOW:1). Only the
identity *foundations* changed from Fix1 in this file:

- New ``IdentityKind`` (NATIVE/DERIVED) -- Fix2 abandons Fix1's
  "market_event_id = date+symbol+origin+minute-bucket" premise entirely.
  A real Strategist Stage2 30-second-polling artifact read for this pass
  proves that premise merges genuinely independent decisions (different
  ``decision_id``) that happen to land in the same wall-clock minute.
  Fix2's identity is now built preferring each source's own **native**
  stable id (``decision_id``/``run_id``/``trade_id``/... -- see
  ``identity.py::build_event_ref``), falling back to a **derived**
  composite key only when no native id exists.
- New ``LineageStatus`` (FULL/PARTIAL/UNKNOWN) -- replaces the
  ``source_lineage_known: bool`` boolean on ``AggregateRecord`` (Codex
  MEDIUM: a boolean cannot express "26 episodes claimed, only 5 ids
  actually on hand").
- New ``EventDateRelation`` -- makes the relationship between an
  episode's ``trading_date`` and its entry timestamp's actual calendar
  date explicit (same-day is the default assumption; overnight/T+1/T+2
  carries must say so, never silently pass or silently fail).
- ``EntryAuthority`` gains ``SUBMITTED_INTENT`` -- Codex found Fix1's
  Opening Controlled Probe roundtrip mislabeling a bare order-submission
  record (no confirmed fill evidence in that artifact) as ``MOCK_FILL``.
  A real 2026-09-10 pair of artifacts (``probe_submissions.json`` for
  symbol 024060, and the separate, later ``trade_read_model.json`` for
  the same real event) proves these are genuinely two different facts:
  "we submitted an order" vs. "an order was filled."

Everything else here (``RecordKind``, ``ObservationType``,
``EventOrigin``, ``ExecutionMode``, ``SampleStatus``, ``EvidenceStatus``,
``ResearchStatus``, ``CheckpointCompleteness``, ``ReturnUnit``) is
unchanged from Fix1 -- those were not flagged by Codex's re-audit. This
module still only names concepts; it computes nothing. Work Package B
remains the owner of any forward-return formula, cost profile, or
WR/PF/Avg aggregator.
"""

from __future__ import annotations

from enum import Enum


SCHEMA_VERSION = "uef1_evaluation_record.v3"


class IdentityKind(str, Enum):
    """Whether a canonical event id came from the source's own stable id, or was derived.

    NATIVE is always preferred (Fix2 #3/#4/#5): a source's own
    ``decision_id``/``run_id``/``trade_id``/``signal_id``/``candidate_id``/
    ``submission_id``/``cohort_id``/``episode_id`` already IS a stable,
    source-native identifier for "one independent evaluable event" --
    reusing it (namespaced by ``source_namespace`` so two programs' ids
    never collide) is strictly more trustworthy than deriving one from
    timestamp/symbol heuristics. DERIVED is the last resort, used only
    when a source genuinely has no such id (e.g. Q10 lead-market's
    fixed-clock checkpoints, which are identified by the discrete
    ``(day, target, clock_label)`` triple rather than any native id).
    """

    NATIVE = "NATIVE"
    DERIVED = "DERIVED"


class LineageStatus(str, Enum):
    """How completely an AggregateRecord's ``source_episode_ids`` covers its own ``episode_count``.

    Replaces Fix1's ``source_lineage_known: bool`` (Codex MEDIUM finding:
    a boolean cannot express partial coverage, which is the real, common
    case for legacy aggregate artifacts).
    """

    FULL = "FULL"  # len(source_episode_ids) == episode_count
    PARTIAL = "PARTIAL"  # 0 < len(source_episode_ids) < episode_count
    UNKNOWN = "UNKNOWN"  # the source artifact never recorded per-episode ids at all


class EventDateRelation(str, Enum):
    """The declared relationship between a record's ``trading_date`` and its entry timestamp's actual calendar date.

    SAME_DAY is the default and is validated against the actual
    timestamp (Fix2 #25) -- a mismatch with no explicit relation is
    rejected, and a declared non-SAME_DAY relation that turns out to
    actually be the same day is equally rejected (the field must be
    truthful, not just present).
    """

    SAME_DAY = "SAME_DAY"
    OVERNIGHT_CARRY = "OVERNIGHT_CARRY"
    T_PLUS_1 = "T_PLUS_1"
    T_PLUS_2 = "T_PLUS_2"
    OTHER_EXPLICIT = "OTHER_EXPLICIT"


class RecordKind(str, Enum):
    """Tagged-union discriminator for the canonical record family."""

    EPISODE = "EPISODE"
    PAIR = "PAIR"
    SEQUENCE = "SEQUENCE"
    AGGREGATE = "AGGREGATE"


class ObservationType(str, Enum):
    """What concrete shape one :class:`~.record.EpisodeRecord` has."""

    SIGNAL = "SIGNAL"
    CANDIDATE = "CANDIDATE"
    RANK_EVENT = "RANK_EVENT"
    ENTRY_OPPORTUNITY = "ENTRY_OPPORTUNITY"
    BLOCKED_OPPORTUNITY = "BLOCKED_OPPORTUNITY"
    SHADOW_ENTRY = "SHADOW_ENTRY"
    CONTROLLED_ENTRY = "CONTROLLED_ENTRY"
    ACTUAL_TRADE = "ACTUAL_TRADE"
    EXIT_EVENT = "EXIT_EVENT"
    DAY_SYMBOL = "DAY_SYMBOL"


class EventOrigin(str, Enum):
    """What real-world event a timestamp is anchored to."""

    SIGNAL = "SIGNAL"
    CANDIDATE = "CANDIDATE"
    MONITOR_DECISION = "MONITOR_DECISION"
    ENTRY = "ENTRY"
    ACTUAL_FILL = "ACTUAL_FILL"
    ACTUAL_EXIT = "ACTUAL_EXIT"
    OPEN = "OPEN"
    FIXED_CLOCK = "FIXED_CLOCK"
    CUSTOM = "CUSTOM"


class EntryAuthority(str, Enum):
    """Where a price/time observation actually came from.

    Fix2 adds ``SUBMITTED_INTENT`` (see module docstring): an order/probe
    submission record with no confirmed fill evidence must never be
    represented with ``MOCK_FILL``/``BROKER_FILL`` -- those mean a fill
    is confirmed to have happened.
    """

    SIGNAL_PRICE = "SIGNAL_PRICE"
    CANDIDATE_PRICE = "CANDIDATE_PRICE"
    SCANNER_REFERENCE = "SCANNER_REFERENCE"
    MONITOR_REFERENCE = "MONITOR_REFERENCE"
    MARKET_QUOTE = "MARKET_QUOTE"
    BEST_ASK = "BEST_ASK"
    SIMULATED_FILL = "SIMULATED_FILL"
    SUBMITTED_INTENT = "SUBMITTED_INTENT"
    MOCK_FILL = "MOCK_FILL"
    BROKER_FILL = "BROKER_FILL"
    OPEN_PRICE = "OPEN_PRICE"
    FIXED_CLOCK_PRICE = "FIXED_CLOCK_PRICE"


class ExecutionMode(str, Enum):
    """What actually happened (or could happen) at the broker."""

    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    SHADOW = "SHADOW"
    CONTROLLED_MOCK = "CONTROLLED_MOCK"
    BROKER_LIVE = "BROKER_LIVE"
    DIAGNOSTIC = "DIAGNOSTIC"


class SampleStatus(str, Enum):
    """Per-record data completeness -- did THIS record's own data arrive intact?"""

    ELIGIBLE = "ELIGIBLE"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"
    EXCLUDED = "EXCLUDED"
    CONTAMINATED = "CONTAMINATED"
    DUPLICATE = "DUPLICATE"


class EvidenceStatus(str, Enum):
    """Statistical/validation maturity of the evidence a program has accumulated so far."""

    INSUFFICIENT = "INSUFFICIENT"
    COLLECTING = "COLLECTING"
    SUFFICIENT = "SUFFICIENT"
    CONFLICTED = "CONFLICTED"


class ResearchStatus(str, Enum):
    """Hypothesis/program lifecycle vocabulary. Not a field on any record class -- see record.py."""

    PROSPECTIVE = "PROSPECTIVE"
    VALIDATING = "VALIDATING"
    RETAIN = "RETAIN"
    DEPRECATE_REVIEW = "DEPRECATE_REVIEW"
    CLOSED = "CLOSED"


class CheckpointCompleteness(str, Enum):
    """Per-checkpoint (not per-record) observation completeness."""

    OBSERVED = "OBSERVED"
    PENDING = "PENDING"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class CheckpointMetricKind(str, Enum):
    """Whether a checkpoint's outcome fields are anchored to an observed price, or not (Fix3 M3).

    ``PRICE_BASED`` (the default, and every real checkpoint read from
    this codebase's own Q9-Q18/Opening Alpha artifacts) requires
    ``observed_price`` whenever any return/MFE/MAE outcome field is
    present. ``AGGREGATE_ONLY`` is the explicit escape hatch for a
    checkpoint-shaped value that is not itself anchored to one observed
    price (e.g. a pre-aggregated statistic) -- it must be declared, never
    silently assumed.
    """

    PRICE_BASED = "PRICE_BASED"
    AGGREGATE_ONLY = "AGGREGATE_ONLY"


# Fix3 M4: the minimal allowed set of cross-record relation types. Kept as
# a plain string constant set (not an Enum) so this can grow later without
# an enum-explosion review each time -- but growth still requires editing
# this one authoritative list, so a typo/ad hoc string can never silently
# pass validation.
ALLOWED_RECORD_RELATION_TYPES = frozenset({"SUBMISSION_TO_FILL"})


class ReturnUnit(str, Enum):
    """Explicit unit convention for any return/cost figure."""

    PERCENTAGE_POINTS = "PERCENTAGE_POINTS"  # 1.25 means +1.25%
    FRACTION = "FRACTION"  # 0.0125 means +1.25%


CANONICAL_RETURN_UNIT = ReturnUnit.PERCENTAGE_POINTS


__all__ = [
    "SCHEMA_VERSION",
    "CANONICAL_RETURN_UNIT",
    "IdentityKind",
    "LineageStatus",
    "EventDateRelation",
    "RecordKind",
    "ObservationType",
    "EventOrigin",
    "EntryAuthority",
    "ExecutionMode",
    "SampleStatus",
    "EvidenceStatus",
    "ResearchStatus",
    "CheckpointCompleteness",
    "CheckpointMetricKind",
    "ALLOWED_RECORD_RELATION_TYPES",
    "ReturnUnit",
]
