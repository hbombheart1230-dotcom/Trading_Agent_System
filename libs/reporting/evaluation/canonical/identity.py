"""UEF-1 Work Package A Fix2 -- canonical identity.

Fix2 abandons Fix1's rejected identity premise entirely:

    market_event_id = date + symbol + event_origin + minute-bucket

Codex's re-audit (and a real artifact read for this pass,
``strategist_stage2_authority_review.json``) proves this premise is
wrong: Strategist Stage2 polls roughly every 30 seconds, so two
GENUINELY INDEPENDENT decisions (different ``decision_id``, different
``run_id``) routinely land in the same wall-clock minute for the same
symbol -- a minute bucket silently merges them into one identity.

FIX2 IDENTITY MODEL
--------------------
Every canonical event now carries an :class:`EventRef`, built by
:func:`build_event_ref` with a strict priority order:

    1. The source's own NATIVE stable id, if one exists --
       ``decision_id``/``run_id``/``signal_id``/``candidate_id``/
       ``trade_id``/``submission_id``/``cohort_id``/``episode_id``, or
       any other identifier the source system itself already treats as
       stable and unique for one independent event. This is always
       preferred: a source-native id is more trustworthy than anything
       this module could derive from timestamp/symbol heuristics.
    2. A DERIVED composite key, used ONLY when a source genuinely has no
       native id (e.g. Q10 lead-market's fixed-clock checkpoints, which
       are identified by the discrete ``(day, target, clock_label)``
       triple, not a native id).

``EventRef.canonical_event_id`` is a deterministic hash of
``(identity_kind, source_namespace, source_id, derivation_version)`` --
critically, ALL FOUR of those inputs are themselves stored on the
``EventRef``, so :func:`validate_event_ref` can *actually recompute and
compare* the hash (true identity-consistency-by-construction, Fix2 #19-21)
rather than merely checking a prefix/length as Fix1 did.

No timestamp bucketing of any kind participates in event identity any
more. A 60-second (or any-second) bucket is now available ONLY as an
explicitly separate, explicitly non-authoritative
:func:`cross_program_link_key` -- see that function's docstring for why
it can never be used for deduplication.

TIMESTAMP NORMALIZATION CONTRACT (retained from Fix1, still correct)
----------------------------------------------------------------------
Canonical timestamps are int Unix epoch seconds (UTC). Accepted inputs to
:func:`to_epoch_seconds`: int/float epoch seconds or milliseconds
(detected by magnitude); ISO 8601 strings (naive assumed ``Asia/Seoul``,
this system's own market timezone -- never UTC); raw ``YYYYMMDDHHMMSS``
strings (this system's own ``raw_ts`` convention); numeric strings (some
of this system's own artifacts quote an epoch as a JSON string, e.g.
``opening_rank1_controlled_probe``'s ``"recorded_at": "1789084812"``).

SYMBOL / DATE NORMALIZATION CONTRACT (UEF-1 FINAL CLOSURE PATCH H1 -- updated)
-------------------------------------------------------------------------------
``canonicalize_symbol`` defers to this repo's own
``libs.core.symbols.normalize_symbol(..., allow_test_symbols=False)`` --
the same production-only authority this repo's own real symbol consumers
(``kiwoom_portfolio_reader.py``, ``reporter_analysis.py``,
``trade_explain.py``) call. It handles the "005930" vs "A005930"
leading-zero/prefix problem correctly, and REJECTS a short numeric string
like "5930" outright -- that string is a test/synthetic-symbol
convention, never a real KRX code, and must never be silently accepted
(not even through the pseudo-symbol fallback -- a purely numeric string is
never treated as a legitimate pseudo-symbol either). Non-KRX pseudo-symbols
(index labels, cross-asset cohort labels) always contain at least one
letter (e.g. "KOSPI200", "BTC-WOORI") and fall back to an explicit,
validated pseudo-symbol path.
``canonicalize_trading_date`` now performs REAL calendar validation via
``datetime.date.fromisoformat`` (Fix2 #24: Fix1's regex accepted the
calendrically-impossible ``"2026-99-99"``).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from libs.core.symbols import normalize_symbol

from .contracts import IdentityKind


_HASH_LEN = 20  # 20 hex chars: collision-resistant at this scale, human-pasteable
MARKET_TIMEZONE = "Asia/Seoul"
_KST = ZoneInfo(MARKET_TIMEZONE)

_RAW_TS_RE = re.compile(r"^\d{14}$")
_PSEUDO_SYMBOL_RE = re.compile(r"^[A-Z0-9\-_.]{1,32}$")
_NAMESPACE_RE = re.compile(r"^[a-z0-9_]{1,64}$")


class TimestampNormalizationError(ValueError):
    """Raised when a value cannot be normalized into canonical epoch seconds."""


def to_epoch_seconds(value: Any) -> int:
    """Normalize any of this system's real timestamp shapes to int UTC epoch seconds."""

    if isinstance(value, (int, float)):
        raw = float(value)
        # this repo's own collectors mix epoch-seconds and epoch-milliseconds;
        # anything above ~10 billion seconds (year 2286) is certainly milliseconds.
        return int(raw / 1000.0) if raw > 10_000_000_000 else int(raw)
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=_KST)
        return int(dt.timestamp())
    text = str(value or "").strip()
    if not text:
        raise TimestampNormalizationError("empty timestamp value")
    if _RAW_TS_RE.fullmatch(text):
        dt = datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=_KST)
        return int(dt.timestamp())
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        # a JSON payload sometimes carries an epoch value as a quoted
        # string (e.g. this repo's own probe_submissions.json
        # "recorded_at": "1789084812") -- recurse through the numeric path.
        return to_epoch_seconds(float(text))
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TimestampNormalizationError(f"unrecognized timestamp shape: {text!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_KST)
    return int(dt.timestamp())


def epoch_seconds_to_kst_date(epoch_seconds: int) -> str:
    """The Asia/Seoul calendar date (``YYYY-MM-DD``) a given epoch falls on."""

    return datetime.fromtimestamp(int(epoch_seconds), tz=_KST).date().isoformat()


def canonicalize_symbol(symbol: Any) -> str:
    """Canonical symbol form: real KRX-authority first, explicit pseudo-symbol fallback second.

    UEF-1 FINAL CLOSURE PATCH H1: uses ``allow_test_symbols=False`` -- the
    same production-only authority this repo's own real symbol consumers
    (``kiwoom_portfolio_reader.py``, ``reporter_analysis.py``,
    ``trade_explain.py``) call. A short numeric form like ``"5930"`` is a
    test/synthetic-symbol convention, never a real KRX code, and is
    REJECTED outright -- it must never be silently accepted through the
    pseudo-symbol fallback below just because it happens to be composed of
    characters the pseudo-symbol pattern would otherwise allow. A genuine
    pseudo-symbol (an index label, a cross-asset cohort label) always
    contains at least one letter (e.g. ``"KOSPI200"``, ``"BTC-WOORI"``); a
    purely numeric string is never a legitimate pseudo-symbol and is
    rejected here, not silently promoted.
    """

    real = normalize_symbol(symbol, allow_test_symbols=False)
    if real:
        return real
    text = str(symbol or "").strip().upper()
    if not text:
        return ""
    if text.isdigit():
        raise ValueError(
            f"symbol {symbol!r} is a numeric string but not a valid production KRX code "
            "(production contract: \"005930\" valid, \"A005930\" -> \"005930\", a short numeric "
            "form like \"5930\" is REJECTED as a test/synthetic-symbol convention, never a real "
            "production representation) -- use an explicit non-numeric pseudo/test symbol if a "
            "non-production symbol is genuinely needed"
        )
    if not _PSEUDO_SYMBOL_RE.fullmatch(text):
        raise ValueError(f"symbol {symbol!r} is neither a recognizable KRX code nor a valid pseudo-symbol label")
    return text


def canonicalize_trading_date(value: Any) -> str:
    """Canonical trading_date form: always ``YYYY-MM-DD``, real-calendar validated."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"trading_date {value!r} is not a real calendar date in YYYY-MM-DD form") from exc


def normalize_enum_value(value: Any, enum_cls: type[Enum]) -> str:
    """Canonicalize either an Enum member or its raw string form to one ``.value``.

    Fix2 H1 fix: ``str(SomeStrEnum.MEMBER)`` returns the qualified repr
    (``"SomeStrEnum.MEMBER"``) on this Python version, NOT ``.value`` --
    confirmed empirically while diagnosing this defect. Every identity
    function that accepts an enum-shaped input MUST route it through this
    function first, so ``EventOrigin.CANDIDATE`` and the bare string
    ``"CANDIDATE"`` always canonicalize identically.
    """

    if isinstance(value, enum_cls):
        return value.value
    text = str(value or "").strip()
    try:
        return enum_cls(text).value
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a valid {enum_cls.__name__} value") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    """Deterministic canonical byte representation for stable hashing.

    Real structured JSON (sorted keys, explicit separators, UTF-8) --
    never a naive ``"|".join(...)``, which could collide if a field's own
    value contained the delimiter.
    """

    def _default(obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(f"not canonically serializable: {type(obj)!r}")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_default).encode("utf-8")


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()[:_HASH_LEN]


def canonicalize_namespace(source_namespace: Any) -> str:
    text = str(source_namespace or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not _NAMESPACE_RE.fullmatch(text):
        raise ValueError(f"source_namespace {source_namespace!r} must be lowercase snake_case, 1-64 chars")
    return text


class EventRef:
    """A reference to one independent, canonically identified real-world event.

    Reused wherever any record kind needs to point at "one event":
    ``EpisodeIdentity.event``, ``PairIdentity.left_event``/``right_event``,
    ``SequenceLeg.event``, ``AggregateIdentity.aggregate_ref``.

    Deliberately a plain (not frozen-dataclass) class with a tuple-based
    ``__eq__``/``__hash__`` so it round-trips cleanly through the
    canonical JSON serializer in ``record.py`` while still supporting
    ``==`` comparisons in tests -- kept minimal on purpose.
    """

    __slots__ = ("identity_kind", "source_namespace", "source_id", "canonical_event_id", "derivation_version")

    def __init__(self, *, identity_kind: IdentityKind, source_namespace: str, source_id: str,
                 canonical_event_id: str, derivation_version: str = "v1") -> None:
        self.identity_kind = identity_kind
        self.source_namespace = source_namespace
        self.source_id = source_id
        self.canonical_event_id = canonical_event_id
        self.derivation_version = derivation_version

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, EventRef):
            return NotImplemented
        return (
            self.identity_kind == other.identity_kind
            and self.source_namespace == other.source_namespace
            and self.source_id == other.source_id
            and self.canonical_event_id == other.canonical_event_id
            and self.derivation_version == other.derivation_version
        )

    def __hash__(self) -> int:
        return hash((self.identity_kind, self.source_namespace, self.source_id, self.canonical_event_id, self.derivation_version))

    def __repr__(self) -> str:
        return (
            f"EventRef(identity_kind={self.identity_kind!r}, source_namespace={self.source_namespace!r}, "
            f"source_id={self.source_id!r}, canonical_event_id={self.canonical_event_id!r}, "
            f"derivation_version={self.derivation_version!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_kind": self.identity_kind.value if isinstance(self.identity_kind, Enum) else str(self.identity_kind),
            "source_namespace": self.source_namespace,
            "source_id": self.source_id,
            "canonical_event_id": self.canonical_event_id,
            "derivation_version": self.derivation_version,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "EventRef":
        return EventRef(
            identity_kind=IdentityKind(payload["identity_kind"]),
            source_namespace=payload["source_namespace"],
            source_id=payload["source_id"],
            canonical_event_id=payload["canonical_event_id"],
            derivation_version=payload.get("derivation_version", "v1"),
        )


def _event_ref_hash_payload(*, identity_kind: IdentityKind, source_namespace: str, source_id: str, derivation_version: str) -> dict[str, str]:
    return {
        "identity_kind": identity_kind.value,
        "source_namespace": source_namespace,
        "source_id": source_id,
        "derivation_version": derivation_version,
    }


class DerivedFieldKind(str, Enum):
    """What a derived-identity field's value actually IS, so it can be routed
    through the right canonicalization authority before hashing (Closure
    Reset Group A: a raw, un-kinded dict let ``"005930"``/``"A005930"``
    hash to different ids through the generic path, even though the typed
    builders already fixed this for date/symbol/clock fields specifically).
    There is deliberately no bare "pass the dict as-is" path any more --
    every derived field must declare one of these.
    """

    SYMBOL = "SYMBOL"
    TRADING_DATE = "TRADING_DATE"
    FIXED_CLOCK_LABEL = "FIXED_CLOCK_LABEL"
    RAW = "RAW"  # already-canonical/opaque (e.g. a numeric epoch, a pre-normalized enum .value) -- passed through as-is


class DerivedIdentityPart:
    """One named, kind-tagged field going into a DERIVED identity hash.

    Plain class (not a dataclass) with explicit ``__eq__``/``__hash__`` --
    kept minimal and consistent with :class:`EventRef`'s own style.
    """

    __slots__ = ("kind", "value")

    def __init__(self, *, kind: DerivedFieldKind, value: Any) -> None:
        self.kind = kind
        self.value = value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, DerivedIdentityPart):
            return NotImplemented
        return self.kind == other.kind and self.value == other.value

    def __repr__(self) -> str:
        return f"DerivedIdentityPart(kind={self.kind!r}, value={self.value!r})"


def _canonicalize_derived_part(part: DerivedIdentityPart) -> Any:
    if part.kind is DerivedFieldKind.SYMBOL:
        return canonicalize_symbol(part.value)
    if part.kind is DerivedFieldKind.TRADING_DATE:
        return canonicalize_trading_date(part.value)
    if part.kind is DerivedFieldKind.FIXED_CLOCK_LABEL:
        return canonicalize_fixed_clock_label(part.value)
    if part.kind is DerivedFieldKind.RAW:
        return part.value
    raise ValueError(f"unknown DerivedFieldKind: {part.kind!r}")


# UEF-1 FINAL CLOSURE PATCH H2: field names that name a known canonical
# identity concept. A RAW-kinded part is REJECTED if its own name is one of
# these (RAW must never be used to bypass a domain field's own typed
# canonicalization authority), and its value is scanned recursively for a
# nested dict/mapping key of the same name (closing the "RAW {'symbol':
# 'A005930'}" and nested "RAW {'context': {'symbol': 'A005930'}}" bypass
# paths Codex's audit specifically required tested).
_RESERVED_CANONICAL_FIELD_NAMES = frozenset({
    "symbol", "trading_date", "date", "clock", "fixed_clock", "fixed_clock_label",
    "origin", "event_origin", "horizon_origin", "execution_mode", "observation_type",
})


def _find_reserved_field_name(value: Any) -> str | None:
    """Recursively scan a RAW-kinded value for a nested reserved canonical field name.

    A RAW part exists only for genuinely opaque values with no dedicated
    canonicalization authority of their own (e.g. a numeric epoch) -- it
    must never be used to smuggle a canonicalizable domain field (symbol,
    trading_date, ...) past its own typed authority by nesting it inside an
    arbitrary dict/list structure.
    """

    if isinstance(value, dict):
        for key, val in value.items():
            if str(key).strip().lower() in _RESERVED_CANONICAL_FIELD_NAMES:
                return str(key)
            nested = _find_reserved_field_name(val)
            if nested is not None:
                return nested
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested = _find_reserved_field_name(item)
            if nested is not None:
                return nested
    return None


def _validate_derived_field(name: str, part: "DerivedIdentityPart") -> None:
    if not isinstance(part, DerivedIdentityPart):
        raise ValueError(
            f"derived_fields[{name!r}] must be a DerivedIdentityPart (kind=SYMBOL/TRADING_DATE/"
            f"FIXED_CLOCK_LABEL/RAW), not {type(part)!r} -- a plain dict/list/value is never "
            "silently promoted to RAW; declare its DerivedFieldKind explicitly"
        )
    if part.kind is DerivedFieldKind.RAW:
        if str(name).strip().lower() in _RESERVED_CANONICAL_FIELD_NAMES:
            raise ValueError(
                f"derived_fields[{name!r}] is tagged RAW but its field name is a reserved canonical "
                "identity field (symbol/trading_date/date/clock/fixed_clock*/origin/execution_mode/"
                "observation_type) -- RAW must never bypass typed canonicalization for a known domain "
                "field; declare the correct DerivedFieldKind instead"
            )
        nested = _find_reserved_field_name(part.value)
        if nested is not None:
            raise ValueError(
                f"derived_fields[{name!r}] is tagged RAW but its value nests a reserved canonical "
                f"field name ({nested!r}) -- RAW must never be used to hide a canonicalizable domain "
                "field inside an arbitrary nested structure; declare it with its own DerivedFieldKind "
                "at the top level instead"
            )


def build_event_ref(
    *,
    source_namespace: str,
    native_id: Any = None,
    derived_fields: dict[str, "DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
) -> EventRef:
    """Build a canonical event reference, preferring a NATIVE id over a DERIVED one.

    ``native_id`` -- pass the source's own stable id (``decision_id``,
    ``trade_id``, ``run_id``, ``candidate_id``, ``submission_id``,
    ``cohort_id``, ``episode_id``, ...) whenever the source has one. This
    is the strongly preferred path.

    ``derived_fields`` -- used ONLY when ``native_id`` is not provided: a
    dict of ``{name: DerivedIdentityPart}``. Every value is tagged with a
    :class:`DerivedFieldKind` and routed through that kind's own
    canonicalization authority BEFORE hashing (Closure Reset Group A/#2-3:
    there is no longer a "raw arbitrary dict" path -- a ``SYMBOL``-kinded
    part always goes through :func:`canonicalize_symbol`, a
    ``TRADING_DATE``-kinded part through :func:`canonicalize_trading_date`,
    etc., so ``"005930"`` and ``"A005930"`` are now GUARANTEED to hash
    identically through this function too, not only through the typed
    convenience builders below). ``RAW`` remains for genuinely opaque,
    already-stable values (e.g. Q12's numeric ``target_epoch``) that have
    no dedicated canonicalization authority of their own.
    """

    namespace = canonicalize_namespace(source_namespace)
    if native_id is not None and str(native_id).strip():
        kind = IdentityKind.NATIVE
        source_id = str(native_id).strip()
    else:
        if not derived_fields:
            raise ValueError("build_event_ref requires either native_id or non-empty derived_fields")
        for name, part in derived_fields.items():
            _validate_derived_field(name, part)
        canonical_parts = {name: _canonicalize_derived_part(part) for name, part in derived_fields.items()}
        kind = IdentityKind.DERIVED
        source_id = _stable_hash(canonical_parts)
    canonical = f"EVT_{_stable_hash(_event_ref_hash_payload(identity_kind=kind, source_namespace=namespace, source_id=source_id, derivation_version=derivation_version))}"
    return EventRef(identity_kind=kind, source_namespace=namespace, source_id=source_id, canonical_event_id=canonical, derivation_version=derivation_version)


_CLOCK_HHMM_RE = re.compile(r"^(\d{2}):(\d{2})(?::(\d{2}))?$")
_CLOCK_LABEL_RE = re.compile(r"^[A-Z_]{1,16}$")


def canonicalize_fixed_clock_label(value: Any) -> str:
    """Canonical form of a FIXED_CLOCK checkpoint label (Fix3 H4/#14).

    ``"09:00"`` and ``"09:00:00"`` normalize to the same ``"HH:MM"`` form
    (seconds are dropped, never distinguish two labels that mean the same
    clock minute in this system's own checkpoint vocabulary). Non-numeric
    discrete labels (``"CLOSE"``, ``"OPEN"``) are validated and uppercased.
    An out-of-range clock time (e.g. ``"25:99"``) is rejected outright.
    """

    text = str(value or "").strip().upper()
    if not text:
        raise ValueError("fixed_clock_label must not be empty")
    match = _CLOCK_HHMM_RE.fullmatch(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"fixed_clock_label {value!r} is not a valid HH:MM clock time")
        return f"{hour:02d}:{minute:02d}"
    if not _CLOCK_LABEL_RE.fullmatch(text):
        raise ValueError(f"fixed_clock_label {value!r} is neither HH:MM(:SS) nor a valid discrete label")
    return text


def build_derived_event_ref(
    *,
    source_namespace: str,
    trading_date: str,
    symbol: str,
    extra_fields: dict[str, "DerivedIdentityPart"] | None = None,
    derivation_version: str = "v1",
) -> EventRef:
    """Typed derived-key builder: ``trading_date`` and ``symbol`` are tagged
    ``TRADING_DATE``/``SYMBOL`` and canonicalized before hashing, so
    ``"005930"``/``"A005930"`` and ``datetime.date(2026, 9, 11)``/``"2026-09-11"``
    collapse to the same id.

    UEF-1 FINAL CLOSURE PATCH H2: ``extra_fields`` no longer accepts a
    plain ``dict[str, Any]`` that gets silently wrapped whole into one RAW
    part (that was the actual defect Codex's audit found -- an arbitrary
    dict, including one containing a ``symbol``/``trading_date`` key,
    reaching the identity hash with zero canonicalization). Every value in
    ``extra_fields`` must now be an explicit, already-kinded
    ``DerivedIdentityPart`` -- e.g. a decision_id/side discriminator with
    no canonicalization authority of its own is ``DerivedFieldKind.RAW``;
    anything that is actually a symbol/date/clock label must declare that
    kind instead and go through its own typed authority.
    """

    fields: dict[str, DerivedIdentityPart] = {
        "trading_date": DerivedIdentityPart(kind=DerivedFieldKind.TRADING_DATE, value=trading_date),
        "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value=symbol),
    }
    if extra_fields:
        for name, part in extra_fields.items():
            if name in fields:
                raise ValueError(f"extra_fields key {name!r} collides with the built-in trading_date/symbol fields")
            fields[name] = part
    return build_event_ref(source_namespace=source_namespace, derived_fields=fields, derivation_version=derivation_version)


def build_fixed_clock_event_ref(
    *,
    source_namespace: str,
    trading_date: str,
    symbol: str,
    fixed_clock_label: str,
    derivation_version: str = "v1",
) -> EventRef:
    """Typed derived-key builder for FIXED_CLOCK checkpoints.

    Canonicalizes ``trading_date``, ``symbol``, AND ``fixed_clock_label``
    before hashing -- ``"09:00"`` and ``"09:00:00"`` for the same
    date/symbol are guaranteed to produce the identical ``canonical_event_id``.
    """

    fields = {
        "trading_date": DerivedIdentityPart(kind=DerivedFieldKind.TRADING_DATE, value=trading_date),
        "symbol": DerivedIdentityPart(kind=DerivedFieldKind.SYMBOL, value=symbol),
        "fixed_clock_label": DerivedIdentityPart(kind=DerivedFieldKind.FIXED_CLOCK_LABEL, value=fixed_clock_label),
    }
    return build_event_ref(source_namespace=source_namespace, derived_fields=fields, derivation_version=derivation_version)


def validate_event_ref(ref: EventRef) -> None:
    """TRUE recompute validation (Fix2 #19-21): re-derive canonical_event_id from the ref's own stored inputs and compare.

    This is not a format/prefix check -- it recomputes the exact hash a
    tampered or hand-typed ``EventRef`` would have to fake correctly,
    which is precisely what "identity consistency by construction" means.
    """

    expected = f"EVT_{_stable_hash(_event_ref_hash_payload(identity_kind=ref.identity_kind, source_namespace=ref.source_namespace, source_id=ref.source_id, derivation_version=ref.derivation_version))}"
    if expected != ref.canonical_event_id:
        raise ValueError(
            f"canonical_event_id={ref.canonical_event_id!r} does not match the hash of its own "
            f"(identity_kind={ref.identity_kind!r}, source_namespace={ref.source_namespace!r}, "
            f"source_id={ref.source_id!r}, derivation_version={ref.derivation_version!r}) -- "
            "use build_event_ref() rather than constructing/editing an EventRef by hand"
        )


def evaluation_subject_id(*, canonical_event_id: str, hypothesis_id: str, observation_type: Any) -> str:
    """Identify which program/hypothesis evaluates the event, as what kind of observation.

    Excludes ``evaluator_version`` and ``execution_mode`` -- both are
    attributes of a concrete record, not of the evaluation subject.
    ``observation_type`` is routed through :func:`normalize_enum_value`
    when it's an Enum member, otherwise used as the raw string (callers
    of this low-level function may legitimately pass either).
    """

    from .contracts import ObservationType

    normalized_type = normalize_enum_value(observation_type, ObservationType) if isinstance(observation_type, Enum) else str(observation_type)
    payload = {
        "canonical_event_id": str(canonical_event_id),
        "hypothesis_id": str(hypothesis_id or ""),
        "observation_type": normalized_type,
    }
    return f"SUBJ_{_stable_hash(payload)}"


def evaluation_record_id(*, evaluation_subject_id: str, execution_mode: Any) -> str:
    """Identify the concrete record: the subject plus its one identity-relevant attribute.

    ``evaluator_version`` is NEVER an input here -- pure provenance on the
    record, so recomputing the same record under a newer evaluator
    version yields the SAME ``evaluation_record_id``.
    """

    from .contracts import ExecutionMode

    normalized_mode = normalize_enum_value(execution_mode, ExecutionMode) if isinstance(execution_mode, Enum) else str(execution_mode)
    payload = {"evaluation_subject_id": str(evaluation_subject_id), "execution_mode": normalized_mode}
    return f"REC_{_stable_hash(payload)}"


_ID_FORMAT = {
    "evaluation_subject_id": re.compile(r"^SUBJ_[0-9a-f]{%d}$" % _HASH_LEN),
    "evaluation_record_id": re.compile(r"^REC_[0-9a-f]{%d}$" % _HASH_LEN),
}


def validate_evaluation_id_format(name: str, value: str) -> None:
    pattern = _ID_FORMAT.get(name)
    if pattern is None:
        raise ValueError(f"unknown id field: {name}")
    if not pattern.match(str(value or "")):
        raise ValueError(f"{name}={value!r} does not match the expected {name} format")


def cross_program_link_key(*, trading_date: str, symbol: str, context_label: str) -> str:
    """A NON-AUTHORITATIVE grouping key for reporting/context purposes only.

    Fix2 #6/#7/#8: this is deliberately NEVER an input to
    :func:`build_event_ref`, :func:`evaluation_subject_id`,
    :func:`evaluation_record_id`, or :func:`classify_duplicate_relation`.
    Two records can share a ``cross_program_link_key`` (e.g. "both
    happened during the market open on the same symbol") while having
    completely different ``canonical_event_id``s -- that is the CORRECT,
    intended outcome, not a bug. ``context_label`` is a caller-chosen
    discrete label (e.g. ``"OPENING_WINDOW"``, ``"MIDDAY"``), never a raw
    timestamp -- there is deliberately no numeric time-bucketing
    parameter here, so this function structurally cannot be mistaken for
    (or slide back into being) an identity mechanism.
    """

    payload = {
        "trading_date": canonicalize_trading_date(trading_date),
        "symbol": canonicalize_symbol(symbol),
        "context_label": str(context_label or "").strip().upper(),
    }
    return f"LINK_{_stable_hash(payload)}"


class DuplicateRelation(str, Enum):
    """The relationship between two canonical records."""

    ACCIDENTAL_DUPLICATE = "ACCIDENTAL_DUPLICATE"
    LEGITIMATE_MULTI_HYPOTHESIS = "LEGITIMATE_MULTI_HYPOTHESIS"
    REPEATED_SETUP = "REPEATED_SETUP"
    SAME_SYMBOL_DIFFERENT_EPISODE = "SAME_SYMBOL_DIFFERENT_EPISODE"
    DIFFERENT_SYMBOL = "DIFFERENT_SYMBOL"
    SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION = "SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION"
    SAME_SUBJECT_DIFFERENT_EXECUTION_MODE = "SAME_SUBJECT_DIFFERENT_EXECUTION_MODE"


def classify_duplicate_relation(
    *,
    canonical_event_id_a: str,
    evaluation_subject_id_a: str,
    evaluation_record_id_a: str,
    symbol_a: str,
    hypothesis_id_a: str,
    evaluator_version_a: str,
    canonical_event_id_b: str,
    evaluation_subject_id_b: str,
    evaluation_record_id_b: str,
    symbol_b: str,
    hypothesis_id_b: str,
    evaluator_version_b: str,
) -> DuplicateRelation:
    """Classify the relationship between two records for overlap/double-count auditing.

    Pure classification -- never filters, drops, or otherwise changes a
    record. Fix2 #23: a ``cross_program_link_key`` is deliberately not
    one of this function's parameters at all -- it must never participate
    in a duplicate/authority decision.
    """

    if evaluation_record_id_a == evaluation_record_id_b:
        if evaluator_version_a != evaluator_version_b:
            return DuplicateRelation.SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION
        return DuplicateRelation.ACCIDENTAL_DUPLICATE
    if evaluation_subject_id_a == evaluation_subject_id_b:
        return DuplicateRelation.SAME_SUBJECT_DIFFERENT_EXECUTION_MODE
    if canonical_event_id_a == canonical_event_id_b:
        return DuplicateRelation.LEGITIMATE_MULTI_HYPOTHESIS
    if canonicalize_symbol(symbol_a) != canonicalize_symbol(symbol_b):
        return DuplicateRelation.DIFFERENT_SYMBOL
    if hypothesis_id_a == hypothesis_id_b:
        return DuplicateRelation.REPEATED_SETUP
    return DuplicateRelation.SAME_SYMBOL_DIFFERENT_EPISODE


__all__ = [
    "MARKET_TIMEZONE",
    "TimestampNormalizationError",
    "to_epoch_seconds",
    "epoch_seconds_to_kst_date",
    "canonicalize_symbol",
    "canonicalize_trading_date",
    "canonicalize_namespace",
    "normalize_enum_value",
    "EventRef",
    "DerivedFieldKind",
    "DerivedIdentityPart",
    "build_event_ref",
    "build_derived_event_ref",
    "build_fixed_clock_event_ref",
    "canonicalize_fixed_clock_label",
    "validate_event_ref",
    "evaluation_subject_id",
    "evaluation_record_id",
    "validate_evaluation_id_format",
    "cross_program_link_key",
    "DuplicateRelation",
    "classify_duplicate_relation",
]
