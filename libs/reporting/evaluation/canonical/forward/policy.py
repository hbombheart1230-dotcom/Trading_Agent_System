"""UEF-2A BOUNDARY CLOSURE -- generic Canonical Forward Calculation-Recipe contract.

This module is the GENERIC FORWARD CORE only: every dataclass here must
remain readable without knowing any program name (Q9/Q10/Q11/Q12/Opening).
Program-specific declarative recipes live in `profiles.py` instead, built
purely by composing these primitives -- never the reverse. A `ForwardPolicy`
is not "which enums are legal" -- it is a declared CALCULATION RECIPE, in
three explicitly separated layers:

    A. Reference / Origin Resolution  (`ReferenceResolutionPolicy`)
       -- HOW the episode's own t=0 timestamp and reference price were
       established. Episode-wide, lives on `ForwardPolicy`.
    B. Checkpoint Observation Resolution  (`ObservationPolicy`)
       -- HOW one checkpoint's own target/search/price/missing rule works.
       Per-`HorizonSpec`.
    C. Excursion Resolution  (`ExcursionPolicy`)
       -- HOW one checkpoint's MFE/MAE (if any) is scanned. Per-`HorizonSpec`,
       fully separate from B (Codex's own explicit instruction: do not
       re-merge these into one "observation" object).

Every ordered price chain (`PriceResolutionPolicy`) is used identically in
all three layers -- reference price, checkpoint price, and excursion
price are all "try these `PriceCandidate`s, in this order" chains; there is
exactly one chain primitive in this module, reused three ways, never three
different ad hoc mechanisms.

Still computes nothing -- no resolver/engine lives here (UEF-2B's job).
UEF-1's own vocabulary (`EventOrigin`, `ReturnUnit`, `MARKET_TIMEZONE`,
`canonicalize_fixed_clock_label`, `Checkpoint.horizon_set_id`) is reused
throughout, never duplicated or redefined.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contracts import EventOrigin, ReturnUnit
from ..identity import MARKET_TIMEZONE, canonicalize_fixed_clock_label
from .contracts import (
    FORWARD_POLICY_SCHEMA_VERSION,
    DataCompletenessKind,
    EvidenceVerificationState,
    ForwardSessionResolverAuthority,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingResolutionPolicy,
    PriceCandidate,
    ObservationSelectionMode,
    ReferenceResolutionKind,
    SourceResultCostSemantics,
    TradeDirection,
)


class ForwardPolicyValidationError(ValueError):
    """Raised when a ForwardPolicy or one of its parts violates its own invariants."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ForwardPolicyValidationError(message)


def _require_enum_member(value: Any, enum_cls: type, field_name: str) -> None:
    """Direct-constructor type safety (Boundary Closure item 32/33, Codex MEDIUM finding).

    Dataclasses do not enforce field types at runtime; without this,
    ``PriceResolutionPolicy(authorities=("BOGUS",))`` or any other raw
    string/invalid-type value would be silently accepted by the public
    constructor (not just by a `from_dict` deserialization path). Every
    enum-typed field in this module is guarded by this at construction.
    """

    _require(isinstance(value, enum_cls), f"{field_name}={value!r} must be a real {enum_cls.__name__} member, not a raw {type(value).__name__}")


# The only production-supported values found anywhere in the inventory.
_SUPPORTED_TIMEZONES = frozenset({MARKET_TIMEZONE})
_SUPPORTED_SESSIONS = frozenset({"KRX_REGULAR_SESSION"})


@dataclass(frozen=True)
class FixedClockSpec:
    """An absolute wall-clock target, with a validated timezone/session context.

    ``clock_label`` is canonicalized via UEF-1's OWN existing authority
    (``identity.py::canonicalize_fixed_clock_label``). ``timezone``/``session``
    are validated against the only real production values found.
    """

    clock_label: str
    timezone: str = MARKET_TIMEZONE
    session: str = "KRX_REGULAR_SESSION"

    def __post_init__(self) -> None:
        try:
            canonical = canonicalize_fixed_clock_label(self.clock_label)
        except ValueError as exc:
            raise ForwardPolicyValidationError(str(exc)) from exc
        object.__setattr__(self, "clock_label", canonical)
        _require(self.timezone in _SUPPORTED_TIMEZONES, f"FixedClockSpec.timezone={self.timezone!r} is not production-supported ({sorted(_SUPPORTED_TIMEZONES)!r})")
        _require(self.session in _SUPPORTED_SESSIONS, f"FixedClockSpec.session={self.session!r} is not production-supported ({sorted(_SUPPORTED_SESSIONS)!r})")

    def to_dict(self) -> dict[str, Any]:
        return {"clock_label": self.clock_label, "timezone": self.timezone, "session": self.session}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "FixedClockSpec":
        raw = dict(row)
        return FixedClockSpec(clock_label=raw["clock_label"], timezone=raw.get("timezone", MARKET_TIMEZONE), session=raw.get("session", "KRX_REGULAR_SESSION"))


@dataclass(frozen=True)
class PriceResolutionPolicy:
    """An ORDERED, non-empty chain of `PriceCandidate`s to try in sequence.

    Order is load-bearing and preserved through serialization. A length-1
    chain (the majority of real checkpoints) is the honest single authority
    that checkpoint has, not a "fallback" claim. Reused identically for
    reference prices, checkpoint prices, AND excursion (MFE/MAE) prices --
    one chain primitive, three uses.
    """

    authorities: tuple[PriceCandidate, ...]

    def __post_init__(self) -> None:
        _require(len(self.authorities) > 0, "PriceResolutionPolicy.authorities must not be empty")
        for authority in self.authorities:
            _require_enum_member(authority, PriceCandidate, "PriceResolutionPolicy.authorities[*]")
        _require(len(set(self.authorities)) == len(self.authorities), "PriceResolutionPolicy.authorities must not contain duplicate authorities")

    def to_dict(self) -> dict[str, Any]:
        return {"authorities": [authority.value for authority in self.authorities]}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "PriceResolutionPolicy":
        return PriceResolutionPolicy(authorities=tuple(PriceCandidate(value) for value in row["authorities"]))

    @staticmethod
    def single(candidate: PriceCandidate) -> "PriceResolutionPolicy":
        return PriceResolutionPolicy(authorities=(candidate,))


@dataclass(frozen=True)
class SessionCloseSpec:
    """The concrete session-close authority a ``USE_SESSION_CLOSE_FALLBACK`` rule substitutes."""

    close_clock: FixedClockSpec
    price_resolution: PriceResolutionPolicy

    def to_dict(self) -> dict[str, Any]:
        return {"close_clock": self.close_clock.to_dict(), "price_resolution": self.price_resolution.to_dict()}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "SessionCloseSpec":
        raw = dict(row)
        return SessionCloseSpec(close_clock=FixedClockSpec.from_dict(raw["close_clock"]), price_resolution=PriceResolutionPolicy.from_dict(raw["price_resolution"]))


@dataclass(frozen=True)
class ForwardSessionSpec:
    """FORWARD_SESSION's own bounded-traversal contract (Reset items 21-23).

    Evidence: Opening Shadow's `delayed_path` -- `future_days = [day for day
    in trading_calendar if day > event_day]`, `selected_days =
    future_days[:horizon]`, and `d{n}_status = "INSUFFICIENT_FUTURE_DAYS"`
    whenever `len(selected_days) < horizon OR any(day not in grouped for day
    in selected_days)` (`delayed_outcomes.py:77-81,117-130`). This means
    `d3` requires ALL of the first 3 future sessions to be genuinely present,
    not merely the 3rd one -- `required_available_sessions` names this
    intermediate-completeness requirement explicitly, never assumed.
    """

    resolver_authority: ForwardSessionResolverAuthority
    session_offset: int
    required_available_sessions: int

    def __post_init__(self) -> None:
        _require_enum_member(self.resolver_authority, ForwardSessionResolverAuthority, "ForwardSessionSpec.resolver_authority")
        _require(self.session_offset > 0, "ForwardSessionSpec.session_offset must be positive")
        _require(self.required_available_sessions > 0, "ForwardSessionSpec.required_available_sessions must be positive")
        _require(
            self.required_available_sessions <= self.session_offset,
            "ForwardSessionSpec.required_available_sessions cannot exceed session_offset -- at most `session_offset` intermediate sessions can ever be required",
        )

    def to_dict(self) -> dict[str, Any]:
        return {"resolver_authority": self.resolver_authority.value, "session_offset": self.session_offset, "required_available_sessions": self.required_available_sessions}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "ForwardSessionSpec":
        raw = dict(row)
        return ForwardSessionSpec(resolver_authority=ForwardSessionResolverAuthority(raw["resolver_authority"]), session_offset=raw["session_offset"], required_available_sessions=raw["required_available_sessions"])


@dataclass(frozen=True)
class DataCompletenessPolicy:
    """Gap-check on an EXCURSION scan's own intermediate observations (Boundary Closure item 12/13).

    Evidence: Q12 vnext's `outcomes.py::forward` -- `expected = (target - t)
    // 60 + (1 if horizon == 'EOD' else 0)`, `complete = len(window) ==
    expected` (`vnext/outcomes.py:23-24`), then `mfe_pct`/`mae_pct` are
    `None` unless `complete` (`:28-29`). This governs ONLY the excursion
    scan's own window (never the checkpoint's own single-target
    observation, which is governed by `ObservationPolicy`/
    `MissingResolutionPolicy` instead) -- Q12 vnext still reports its
    checkpoint's own `return_pct`/`net_return_pct` even when the
    intermediate window is incomplete.
    """

    kind: DataCompletenessKind
    interval_seconds: float
    require_all_expected_observations: bool = True

    def __post_init__(self) -> None:
        _require_enum_member(self.kind, DataCompletenessKind, "DataCompletenessPolicy.kind")
        _require(self.interval_seconds > 0, "DataCompletenessPolicy.interval_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "interval_seconds": self.interval_seconds, "require_all_expected_observations": self.require_all_expected_observations}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "DataCompletenessPolicy":
        raw = dict(row)
        return DataCompletenessPolicy(
            kind=DataCompletenessKind(raw["kind"]),
            interval_seconds=raw["interval_seconds"],
            require_all_expected_observations=bool(raw.get("require_all_expected_observations", True)),
        )


@dataclass(frozen=True)
class ObservationPolicy:
    """ONE checkpoint's complete observation-resolution rule (Layer B).

    ``evidence_requirement``/typed collector-variant closure (Reset item
    18): a `VERIFIED` variant must resolve via QUOTE alone (the collector's
    live snapshot is the only thing a VERIFIED state actually returns,
    `reaction_reader.py:410-417`); an `ABSENT` variant must NEVER resolve
    via QUOTE (by definition no collector snapshot was ever captured) --
    both enforced at construction, not left to a generic bool-combination
    validator to catch later.
    """

    selection_mode: ObservationSelectionMode
    price_resolution: PriceResolutionPolicy
    missing_resolution: MissingResolutionPolicy
    lookback_seconds: float = 0.0
    lookahead_seconds: float | None = None
    require_positive_volume: bool = False
    require_positive_price: bool = False
    evidence_requirement: EvidenceVerificationState | None = None
    session_close_fallback: SessionCloseSpec | None = None

    def __post_init__(self) -> None:
        _require_enum_member(self.selection_mode, ObservationSelectionMode, "ObservationPolicy.selection_mode")
        _require_enum_member(self.missing_resolution, MissingResolutionPolicy, "ObservationPolicy.missing_resolution")
        if self.evidence_requirement is not None:
            _require_enum_member(self.evidence_requirement, EvidenceVerificationState, "ObservationPolicy.evidence_requirement")
        _require(self.lookback_seconds >= 0, "ObservationPolicy.lookback_seconds must not be negative")
        if self.lookahead_seconds is not None:
            _require(self.lookahead_seconds >= 0, "ObservationPolicy.lookahead_seconds must not be negative")
        if self.selection_mode is ObservationSelectionMode.EXACT:
            _require(self.lookback_seconds == 0, "ObservationSelectionMode.EXACT cannot carry a lookback_seconds")
            _require(self.lookahead_seconds is None or self.lookahead_seconds == 0, "ObservationSelectionMode.EXACT cannot carry a lookahead_seconds")
        if self.missing_resolution is MissingResolutionPolicy.KEEP_PENDING:
            _require(self.lookahead_seconds is None, "MissingResolutionPolicy.KEEP_PENDING requires an unbounded lookahead_seconds (None)")
        if self.missing_resolution is MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE:
            _require(self.lookahead_seconds is not None, "MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE requires a bounded lookahead_seconds")
        if self.missing_resolution is MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK:
            _require(self.session_close_fallback is not None, "MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK requires a concrete SessionCloseSpec")
        elif self.session_close_fallback is not None:
            _require(False, "ObservationPolicy.session_close_fallback is only meaningful when missing_resolution=USE_SESSION_CLOSE_FALLBACK")
        if self.evidence_requirement is EvidenceVerificationState.INVALID:
            _require(self.missing_resolution is MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY, "EvidenceVerificationState.INVALID must use MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY")
        if self.evidence_requirement is EvidenceVerificationState.VERIFIED:
            _require(self.price_resolution.authorities == (PriceCandidate.QUOTE,), "EvidenceVerificationState.VERIFIED must resolve via QUOTE alone -- a verified collector state never returns anything else")
        if self.evidence_requirement is EvidenceVerificationState.ABSENT:
            _require(PriceCandidate.QUOTE not in self.price_resolution.authorities, "EvidenceVerificationState.ABSENT must never resolve via QUOTE -- by definition no collector snapshot was ever captured")

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_mode": self.selection_mode.value,
            "price_resolution": self.price_resolution.to_dict(),
            "missing_resolution": self.missing_resolution.value,
            "lookback_seconds": self.lookback_seconds,
            "lookahead_seconds": self.lookahead_seconds,
            "require_positive_volume": self.require_positive_volume,
            "require_positive_price": self.require_positive_price,
            "evidence_requirement": self.evidence_requirement.value if self.evidence_requirement is not None else None,
            "session_close_fallback": self.session_close_fallback.to_dict() if self.session_close_fallback is not None else None,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "ObservationPolicy":
        raw = dict(row)
        evidence_requirement = raw.get("evidence_requirement")
        session_close_fallback = raw.get("session_close_fallback")
        return ObservationPolicy(
            selection_mode=ObservationSelectionMode(raw["selection_mode"]),
            price_resolution=PriceResolutionPolicy.from_dict(raw["price_resolution"]),
            missing_resolution=MissingResolutionPolicy(raw["missing_resolution"]),
            lookback_seconds=raw.get("lookback_seconds", 0.0),
            lookahead_seconds=raw.get("lookahead_seconds"),
            require_positive_volume=bool(raw.get("require_positive_volume", False)),
            require_positive_price=bool(raw.get("require_positive_price", False)),
            evidence_requirement=EvidenceVerificationState(evidence_requirement) if evidence_requirement else None,
            session_close_fallback=SessionCloseSpec.from_dict(session_close_fallback) if session_close_fallback else None,
        )


@dataclass(frozen=True)
class ExcursionPolicy:
    """ONE checkpoint's MFE/MAE scan contract (Layer C -- fully separate from Layer B).

    ``mfe_price_resolution``/``mae_price_resolution`` are ORDERED chains,
    not a single `ExcursionPriceField` -- Q10 Semiconductor/Q12's shared
    engine falls back from `BAR_HIGH`/`BAR_LOW` to `REFERENCE_PRICE`
    per-row within the scan (`quant_shadow_forward_outcomes.py:338-339`),
    and Q9 Horizon/Exit falls back from `SOURCE_FIELD_HIGH_PRICE`/
    `SOURCE_FIELD_LOW_PRICE` to `PRIMARY_PRICE_FALLBACK`
    (`strategy_horizon_feedback.py:917-918`). `None` means that excursion is
    not computed at all (Q11's EOD checkpoint computes neither; Opening
    Shadow's `delayed_path` computes MFE only, `mae_price_resolution=None`).
    """

    window_end: MfeMaeWindowEnd
    start_inclusive: bool
    end_inclusive: bool
    mfe_price_resolution: PriceResolutionPolicy | None = None
    mae_price_resolution: PriceResolutionPolicy | None = None
    start_offset_seconds: float = 0.0
    end_offset_seconds: float | None = None
    direction_aware: bool = False
    mfe_floor_zero: bool = False
    mae_cap_zero: bool = False
    completeness: DataCompletenessPolicy | None = None

    def __post_init__(self) -> None:
        _require_enum_member(self.window_end, MfeMaeWindowEnd, "ExcursionPolicy.window_end")
        _require(self.mfe_price_resolution is not None or self.mae_price_resolution is not None, "ExcursionPolicy must compute at least one of MFE/MAE")
        if self.mfe_price_resolution is None:
            _require(not self.mfe_floor_zero, "mfe_floor_zero has no meaning when MFE is not computed")
        if self.mae_price_resolution is None:
            _require(not self.mae_cap_zero, "mae_cap_zero has no meaning when MAE is not computed")
        if self.end_offset_seconds is not None:
            _require(self.end_offset_seconds >= self.start_offset_seconds, "ExcursionPolicy.end_offset_seconds must not be before start_offset_seconds")
        if self.window_end is MfeMaeWindowEnd.UNBOUNDED_FORWARD:
            _require(self.end_offset_seconds is None, "MfeMaeWindowEnd.UNBOUNDED_FORWARD has no end_offset_seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_end": self.window_end.value,
            "start_inclusive": self.start_inclusive,
            "end_inclusive": self.end_inclusive,
            "mfe_price_resolution": self.mfe_price_resolution.to_dict() if self.mfe_price_resolution is not None else None,
            "mae_price_resolution": self.mae_price_resolution.to_dict() if self.mae_price_resolution is not None else None,
            "start_offset_seconds": self.start_offset_seconds,
            "end_offset_seconds": self.end_offset_seconds,
            "direction_aware": self.direction_aware,
            "mfe_floor_zero": self.mfe_floor_zero,
            "mae_cap_zero": self.mae_cap_zero,
            "completeness": self.completeness.to_dict() if self.completeness is not None else None,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "ExcursionPolicy":
        raw = dict(row)
        mfe_row = raw.get("mfe_price_resolution")
        mae_row = raw.get("mae_price_resolution")
        completeness_row = raw.get("completeness")
        return ExcursionPolicy(
            window_end=MfeMaeWindowEnd(raw["window_end"]),
            start_inclusive=raw["start_inclusive"],
            end_inclusive=raw["end_inclusive"],
            mfe_price_resolution=PriceResolutionPolicy.from_dict(mfe_row) if mfe_row else None,
            mae_price_resolution=PriceResolutionPolicy.from_dict(mae_row) if mae_row else None,
            start_offset_seconds=raw.get("start_offset_seconds", 0.0),
            end_offset_seconds=raw.get("end_offset_seconds"),
            direction_aware=bool(raw.get("direction_aware", False)),
            mfe_floor_zero=bool(raw.get("mfe_floor_zero", False)),
            mae_cap_zero=bool(raw.get("mae_cap_zero", False)),
            completeness=DataCompletenessPolicy.from_dict(completeness_row) if completeness_row else None,
        )


@dataclass(frozen=True)
class ReferenceResolutionPolicy:
    """HOW a `ForwardPolicy`'s own t=0 timestamp+price (Layer A) were established.

    ``kind=PRE_RESOLVED_REFERENCE`` is the one case where an UPSTREAM
    process (never this generic engine) already resolved the reference --
    see `ReferenceResolutionKind` for the full ownership determination
    (Q10 Index's `FIRST_PULLBACK_ENTRY`: **UPSTREAM_REFERENCE_RESOLUTION**
    ownership, per Codex's Boundary Closure ruling). Because the engine
    never computes this reference itself, `price_resolution` must be
    exactly `single(PriceCandidate.FIXED_OBSERVED_PRICE)` (the same
    "already resolved, no lookup" semantic `FIXED_OBSERVED_PRICE` already
    carries elsewhere), and `provenance` must name the upstream algorithm
    (e.g. `"FIRST_PULLBACK_ENTRY"`) -- the generic contract never carries
    that algorithm's own parameters (threshold fractions, lookback
    windows); those belong only to the upstream program's own semantic
    profile, never to this engine-facing policy.
    """

    kind: ReferenceResolutionKind
    price_resolution: PriceResolutionPolicy
    origin: EventOrigin | None = None
    provenance: str = ""

    def __post_init__(self) -> None:
        _require_enum_member(self.kind, ReferenceResolutionKind, "ReferenceResolutionPolicy.kind")
        if self.origin is not None:
            _require_enum_member(self.origin, EventOrigin, "ReferenceResolutionPolicy.origin")
        if self.kind is ReferenceResolutionKind.PRE_RESOLVED_REFERENCE:
            _require(self.price_resolution.authorities == (PriceCandidate.FIXED_OBSERVED_PRICE,), "PRE_RESOLVED_REFERENCE must resolve via FIXED_OBSERVED_PRICE alone -- the reference is already resolved upstream, never looked up by this engine")
            _require(bool(self.provenance), "PRE_RESOLVED_REFERENCE requires a non-empty provenance naming the upstream algorithm")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "price_resolution": self.price_resolution.to_dict(),
            "origin": self.origin.value if self.origin is not None else None,
            "provenance": self.provenance,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "ReferenceResolutionPolicy":
        raw = dict(row)
        origin = raw.get("origin")
        return ReferenceResolutionPolicy(
            kind=ReferenceResolutionKind(raw["kind"]),
            price_resolution=PriceResolutionPolicy.from_dict(raw["price_resolution"]),
            origin=EventOrigin(origin) if origin else None,
            provenance=raw.get("provenance", ""),
        )


# Reset item 25/26: the strict per-HorizonKind field-exclusivity matrix.
_KIND_ONLY_FIELDS: dict[HorizonKind, tuple[str, ...]] = {
    HorizonKind.RELATIVE_SECONDS: ("relative_seconds",),
    HorizonKind.FIXED_CLOCK_TARGET: ("fixed_clock",),
    HorizonKind.SESSION_CLOSE: ("fixed_clock",),
    HorizonKind.FORWARD_SESSION: ("forward_session",),
}
_ALL_KIND_SPECIFIC_FIELDS = ("relative_seconds", "fixed_clock", "forward_session")


@dataclass(frozen=True)
class HorizonSpec:
    """ONE checkpoint within a ForwardPolicy -- self-contained enough that UEF-2B never re-reads the legacy source."""

    label: str
    kind: HorizonKind
    origin: EventOrigin
    observation: ObservationPolicy
    excursion: ExcursionPolicy | None = None
    relative_seconds: int | None = None
    forward_session: ForwardSessionSpec | None = None
    fixed_clock: FixedClockSpec | None = None
    horizon_set_id: str = ""

    def __post_init__(self) -> None:
        _require_enum_member(self.kind, HorizonKind, "HorizonSpec.kind")
        _require_enum_member(self.origin, EventOrigin, "HorizonSpec.origin")
        _require(bool(self.label), "HorizonSpec.label is required")
        own_fields = set(_KIND_ONLY_FIELDS.get(self.kind, ()))
        forbidden_fields = [name for name in _ALL_KIND_SPECIFIC_FIELDS if name not in own_fields and getattr(self, name) is not None]
        _require(not forbidden_fields, f"HorizonSpec {self.label!r}: {self.kind.value} must not carry {forbidden_fields}")
        if self.kind is HorizonKind.RELATIVE_SECONDS:
            _require(self.relative_seconds is not None, f"HorizonSpec {self.label!r}: RELATIVE_SECONDS requires relative_seconds")
            _require(self.relative_seconds >= 0, f"HorizonSpec {self.label!r}: relative_seconds must not be negative (0 is the origin instant itself)")
        elif self.kind in (HorizonKind.SESSION_CLOSE, HorizonKind.FIXED_CLOCK_TARGET):
            _require(self.fixed_clock is not None, f"HorizonSpec {self.label!r}: {self.kind.value} requires a FixedClockSpec")
            if self.kind is HorizonKind.FIXED_CLOCK_TARGET:
                _require(self.origin is EventOrigin.FIXED_CLOCK, f"HorizonSpec {self.label!r}: FIXED_CLOCK_TARGET must declare origin=EventOrigin.FIXED_CLOCK")
        elif self.kind is HorizonKind.FORWARD_SESSION:
            _require(self.forward_session is not None, f"HorizonSpec {self.label!r}: FORWARD_SESSION requires a ForwardSessionSpec")
            _require(
                self.observation.missing_resolution is MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY,
                f"HorizonSpec {self.label!r}: FORWARD_SESSION must use MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY -- "
                "evidence: delayed_outcomes.py's own d{n}_status='INSUFFICIENT_FUTURE_DAYS' fires immediately from the "
                "artifact-derived calendar, it never waits/expires -- this is the link (Boundary Closure item 19/20) that "
                "canonically produces MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS for this horizon kind",
            )
        if self.excursion is not None and self.excursion.window_end is MfeMaeWindowEnd.FORWARD_SESSION_BOUND:
            _require(self.kind is HorizonKind.FORWARD_SESSION, f"HorizonSpec {self.label!r}: MfeMaeWindowEnd.FORWARD_SESSION_BOUND requires kind=FORWARD_SESSION -- the excursion window always reuses this horizon's own forward_session bound, never a separate one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind.value,
            "origin": self.origin.value,
            "observation": self.observation.to_dict(),
            "excursion": self.excursion.to_dict() if self.excursion is not None else None,
            "relative_seconds": self.relative_seconds,
            "forward_session": self.forward_session.to_dict() if self.forward_session is not None else None,
            "fixed_clock": self.fixed_clock.to_dict() if self.fixed_clock is not None else None,
            "horizon_set_id": self.horizon_set_id,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "HorizonSpec":
        raw = dict(row)
        fixed_clock_row = raw.get("fixed_clock")
        excursion_row = raw.get("excursion")
        forward_session_row = raw.get("forward_session")
        return HorizonSpec(
            label=raw["label"],
            kind=HorizonKind(raw["kind"]),
            origin=EventOrigin(raw["origin"]),
            observation=ObservationPolicy.from_dict(raw["observation"]),
            excursion=ExcursionPolicy.from_dict(excursion_row) if excursion_row else None,
            relative_seconds=raw.get("relative_seconds"),
            forward_session=ForwardSessionSpec.from_dict(forward_session_row) if forward_session_row else None,
            fixed_clock=FixedClockSpec.from_dict(fixed_clock_row) if fixed_clock_row else None,
            horizon_set_id=raw.get("horizon_set_id", ""),
        )


@dataclass(frozen=True)
class GrossReturnPolicy:
    """The forward gross-return arithmetic, direction, and unit convention -- episode/program-wide."""

    return_unit: ReturnUnit
    direction: TradeDirection = TradeDirection.LONG
    formula: str = "(observed_price / reference_price - 1)"

    def __post_init__(self) -> None:
        _require_enum_member(self.return_unit, ReturnUnit, "GrossReturnPolicy.return_unit")
        _require_enum_member(self.direction, TradeDirection, "GrossReturnPolicy.direction")


def _stable_policy_id(*, horizons: tuple[HorizonSpec, ...], gross_return: GrossReturnPolicy, reference_resolution: ReferenceResolutionPolicy, source_result_cost_semantics: SourceResultCostSemantics) -> str:
    payload = {
        "horizons": [horizon.to_dict() for horizon in horizons],
        "gross_return": {"return_unit": gross_return.return_unit.value, "direction": gross_return.direction.value, "formula": gross_return.formula},
        "reference_resolution": reference_resolution.to_dict(),
        "source_result_cost_semantics": source_result_cost_semantics.value,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return f"FWDPOL_{digest[:20]}"


@dataclass(frozen=True)
class ForwardPolicy:
    """An explicit, immutable, serializable description of one forward/checkpoint calculator's semantics.

    ``reference_resolution`` (Layer A, required): HOW this calculator's own
    origin timestamp+price were established -- kept separate from every
    checkpoint's OWN observation price chain (Layer B).

    ``source_result_cost_semantics``: pure provenance about whether the
    LEGACY calculator's own result already carries a cost adjustment --
    never triggers any cost computation here (UEF-3 remains the sole cost
    authority; UEF-2B computes gross movement only).
    """

    legacy_program: str
    horizons: tuple[HorizonSpec, ...]
    gross_return: GrossReturnPolicy
    reference_resolution: ReferenceResolutionPolicy
    source_result_cost_semantics: SourceResultCostSemantics = SourceResultCostSemantics.UNKNOWN
    cost_note: str = ""
    policy_version: str = "v5"
    schema_version: str = FORWARD_POLICY_SCHEMA_VERSION
    policy_id: str = field(default="")

    def __post_init__(self) -> None:
        _require(bool(self.legacy_program), "ForwardPolicy.legacy_program is required")
        _require_enum_member(self.source_result_cost_semantics, SourceResultCostSemantics, "ForwardPolicy.source_result_cost_semantics")
        _require(len(self.horizons) > 0, "ForwardPolicy.horizons must not be empty")
        seen: dict[tuple[str, str], HorizonSpec] = {}
        for horizon in self.horizons:
            key = (horizon.label, horizon.horizon_set_id)
            _require(key not in seen, f"ForwardPolicy {self.legacy_program!r}: duplicate horizon label {horizon.label!r} within horizon_set_id {horizon.horizon_set_id!r}")
            seen[key] = horizon
        computed_id = _stable_policy_id(horizons=self.horizons, gross_return=self.gross_return, reference_resolution=self.reference_resolution, source_result_cost_semantics=self.source_result_cost_semantics)
        if self.policy_id:
            _require(self.policy_id == computed_id, f"ForwardPolicy.policy_id={self.policy_id!r} does not match its own content-derived id {computed_id!r}")
        else:
            object.__setattr__(self, "policy_id", computed_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "legacy_program": self.legacy_program,
            "horizons": [horizon.to_dict() for horizon in self.horizons],
            "gross_return": {"return_unit": self.gross_return.return_unit.value, "direction": self.gross_return.direction.value, "formula": self.gross_return.formula},
            "reference_resolution": self.reference_resolution.to_dict(),
            "source_result_cost_semantics": self.source_result_cost_semantics.value,
            "cost_note": self.cost_note,
        }

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "ForwardPolicy":
        raw = dict(payload)
        gross_row = dict(raw["gross_return"])
        return ForwardPolicy(
            legacy_program=raw["legacy_program"],
            horizons=tuple(HorizonSpec.from_dict(row) for row in raw["horizons"]),
            gross_return=GrossReturnPolicy(
                return_unit=ReturnUnit(gross_row["return_unit"]),
                direction=TradeDirection(gross_row.get("direction", TradeDirection.LONG.value)),
                formula=gross_row.get("formula", "(observed_price / reference_price - 1)"),
            ),
            reference_resolution=ReferenceResolutionPolicy.from_dict(raw["reference_resolution"]),
            source_result_cost_semantics=SourceResultCostSemantics(raw.get("source_result_cost_semantics", SourceResultCostSemantics.UNKNOWN.value)),
            cost_note=raw.get("cost_note", ""),
            policy_version=raw.get("policy_version", "v5"),
            schema_version=raw.get("schema_version", FORWARD_POLICY_SCHEMA_VERSION),
            policy_id=raw.get("policy_id", ""),
        )


def serialize_forward_policy(policy: ForwardPolicy) -> str:
    return json.dumps(policy.to_dict(), sort_keys=True, ensure_ascii=False)


def deserialize_forward_policy(payload: str) -> ForwardPolicy:
    return ForwardPolicy.from_dict(json.loads(payload))


__all__ = [
    "ForwardPolicyValidationError",
    "FixedClockSpec",
    "PriceResolutionPolicy",
    "SessionCloseSpec",
    "ForwardSessionSpec",
    "DataCompletenessPolicy",
    "ObservationPolicy",
    "ExcursionPolicy",
    "ReferenceResolutionPolicy",
    "HorizonSpec",
    "GrossReturnPolicy",
    "ForwardPolicy",
    "serialize_forward_policy",
    "deserialize_forward_policy",
]
