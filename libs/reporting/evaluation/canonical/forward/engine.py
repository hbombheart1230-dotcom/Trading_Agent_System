"""UEF-2B -- Canonical Forward Engine (generic resolver, no program names).

This module is the ONLY place in `canonical/forward` that computes anything.
It consumes a frozen UEF-2A `ForwardPolicy` (from `profiles.py`, or any other
future source) purely as DATA -- it never imports `profiles.py` and never
branches on `legacy_program`, a horizon `label`, or any other calculator
identity. Every decision this module makes is driven exclusively by the
generic vocabulary already frozen in `contracts.py`/`policy.py`.

Ten generic primitives (the acceptance-gate list, restated):
`resolve_target`, `resolve_observation`, `resolve_ordered_price`,
`validate_evidence`, `validate_completeness`, `resolve_missing`,
`resolve_session_close`, `resolve_forward_session`, `resolve_excursion`,
`calculate_gross_return`. `evaluate_forward` is the one public entry point
that orchestrates them per `HorizonSpec`.

Boundary discipline (restated from the request):

- Layer A (reference resolution) is NOT this engine's job -- the caller
  supplies an already-resolved `ResolvedReference` (timestamp+price per
  `EventOrigin`). This engine only executes Layers B (observation) and C
  (excursion). `resolve_ordered_price` is still exposed as a public,
  reusable primitive -- whoever DOES resolve Layer A upstream may reuse it,
  but this module's own entry point never calls it against
  `ForwardPolicy.reference_resolution`.
- No hidden current time (`datetime.now()`/`date.today()`), no hidden file
  I/O (filesystem/SQLite/network/broker), no legacy artifact parsing.
  Every timestamp, price, and session boundary is either an explicit input
  or derived deterministically from one.
- Gross return only -- no commission/fee/tax/slippage/net/PF/WR/MDD
  (UEF-3's domain). `ForwardPolicy.source_result_cost_semantics` is echoed
  as lineage, never consumed arithmetically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from ..contracts import EventOrigin, ReturnUnit
from ..identity import EventRef, epoch_seconds_to_kst_date
from .contracts import (
    DataCompletenessKind,
    EvidenceVerificationState,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingObservationStatus,
    MissingResolutionPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    SourceResultCostSemantics,
    TradeDirection,
)
from .policy import (
    DataCompletenessPolicy,
    ExcursionPolicy,
    FixedClockSpec,
    ForwardPolicy,
    ForwardSessionSpec,
    GrossReturnPolicy,
    HorizonSpec,
    ObservationPolicy,
    PriceResolutionPolicy,
    SessionCloseSpec,
)


class EngineInputError(ValueError):
    """Raised when the caller's own inputs (not a profile defect) are incomplete/inconsistent."""


class AmbiguousObservationError(EngineInputError):
    """Raised when two supplied observations share a timestamp with conflicting field values.

    UEF-2B FIX1 / H2: neither UEF-1 nor UEF-2A's frozen contract defines any
    precedence/tie-break authority for this case (`ObservationSelectionMode`
    describes search direction relative to a TARGET, never disambiguation
    among multiple candidates already sitting at the identical timestamp).
    Per the explicit instruction, this engine therefore NEVER invents a
    first/last/min/max tie-break, and NEVER lets input order decide --
    this is a deterministic, order-independent failure: the same conflicting
    pair raises the identical error regardless of which one appears first
    in the caller's own list.
    """


class UEF2AFreezeBlocker(RuntimeError):
    """Raised if a frozen UEF-2A profile turns out to be structurally unexecutable by this engine.

    Per the request's absolute freeze: this engine must never silently
    "fix" a UEF-2A structural defect by adding a program-specific branch.
    Raising this and stopping is the only allowed response.
    """


# =========================================================================
# Canonical engine-facing input/output shapes
# =========================================================================


@dataclass(frozen=True)
class CanonicalObservation:
    """One canonical, already-normalized market observation (a bar, tick, or collector snapshot).

    ``fields`` is a flat bag keyed by `PriceCandidate` -- e.g. `{BAR_CLOSE:
    71200.0, BAR_HIGH: 71500.0, SOURCE_FIELD_PRICE: 71200.0}`. This engine
    never parses a legacy raw field name (`"close"`, `"cur_price"`, ...)
    itself -- normalizing legacy field names into `PriceCandidate` keys
    (including the row-own-price alias `PRIMARY_PRICE_FALLBACK`) is the
    canonical-input-building step's job, upstream of this engine (item 7/31:
    no market-specific normalization added here). `REFERENCE_PRICE` is the
    ONE candidate this engine resolves itself (from `ResolvedReference`,
    episode-wide) -- it is never expected in this per-observation bag.
    """

    timestamp: int
    fields: Mapping[PriceCandidate, float | None] = field(default_factory=dict)
    volume: float | None = None
    evidence: EvidenceVerificationState | None = None


@dataclass(frozen=True)
class ResolvedOrigin:
    """One already-resolved (timestamp, price) anchor point for a given `EventOrigin`."""

    timestamp: int
    price: float | None = None


@dataclass(frozen=True)
class ResolvedReference:
    """Layer A's own output, supplied to this engine as an input (this engine never computes it).

    Most `ForwardPolicy`s anchor every `HorizonSpec` to the SAME origin
    event (the common case: one entry in ``origins``). A minority (e.g. an
    ``ACTUAL_EXIT``-anchored checkpoint alongside ``SIGNAL``-anchored
    forward checkpoints in the same policy) declare a horizon whose own
    ``origin`` differs from the policy's primary reference -- ``origins``
    is a small mapping so this engine can look up whichever `EventOrigin`
    a given `HorizonSpec` actually declares, generically, without knowing
    which calculator this is.
    """

    primary_origin: EventOrigin
    origins: Mapping[EventOrigin, ResolvedOrigin]
    provenance: str = ""

    def __post_init__(self) -> None:
        if self.primary_origin not in self.origins:
            raise EngineInputError(f"ResolvedReference.origins is missing its own primary_origin={self.primary_origin!r}")

    @property
    def reference_timestamp(self) -> int:
        return self.origins[self.primary_origin].timestamp

    @property
    def reference_price(self) -> float | None:
        return self.origins[self.primary_origin].price

    def origin_for(self, origin: EventOrigin) -> ResolvedOrigin:
        resolved = self.origins.get(origin)
        if resolved is None:
            raise EngineInputError(f"ResolvedReference has no resolved origin for {origin!r} -- the caller must supply one for every EventOrigin any HorizonSpec in this policy declares")
        return resolved

    @staticmethod
    def single(*, origin: EventOrigin, timestamp: int, price: float | None) -> "ResolvedReference":
        return ResolvedReference(primary_origin=origin, origins={origin: ResolvedOrigin(timestamp=timestamp, price=price)})


@dataclass(frozen=True)
class SessionContext:
    """Calendar/session input for `FORWARD_SESSION` horizons only (unused by every other kind).

    ``future_session_dates``: the ARTIFACT_AVAILABLE_SESSIONS-authority
    calendar (`ForwardSessionResolverAuthority`'s only member) -- calendar
    dates strictly after the origin's own date, in order, that this
    engine's caller already knows exist. ``sessions_with_observations``:
    the subset of those dates that actually have at least one
    `CanonicalObservation`. Both are plain caller-supplied facts -- this
    engine never scans a filesystem/database to discover them (item 30).
    """

    future_session_dates: tuple[str, ...] = ()
    sessions_with_observations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PriceResolution:
    """The result of `resolve_ordered_price` -- which candidate (if any) actually resolved, and to what."""

    price: float | None
    candidate_used: PriceCandidate | None


@dataclass(frozen=True)
class TargetResolution:
    """The result of `resolve_target` -- a resolved epoch, OR a definitive missing status (never a fallback guess)."""

    origin_timestamp: int
    target_timestamp: int | None = None
    target_session_date: str | None = None
    missing_status: MissingObservationStatus | None = None

    @property
    def resolved(self) -> bool:
        return self.missing_status is None


@dataclass(frozen=True)
class ExcursionResult:
    """One resolved MFE or MAE extremum."""

    price: float | None
    candidate_used: PriceCandidate | None
    move: float | None
    observed_timestamp: int | None = None


@dataclass(frozen=True)
class HorizonResult:
    """Canonical per-checkpoint result -- target/observed timestamps are always kept separate (item 14/42).

    ``target_session_date`` (UEF-2B FIX1 / H5): for a `FORWARD_SESSION`
    horizon, `resolve_target` resolves a SESSION (a calendar date), not a
    point-in-time epoch -- `target_timestamp` is correctly `None` for this
    `HorizonKind` (there is no frozen nominal epoch to put there; the
    resolved session date is a genuinely different kind of value, never
    collapsed into the same field). This field is `HorizonResult`'s own --
    UEF-2B's own result type, not a UEF-2A frozen contract -- so adding it
    here is a UEF-2B execution fix, not a UEF-2A amendment.
    """

    label: str
    horizon_set_id: str
    origin_timestamp: int
    target_timestamp: int | None
    target_session_date: str | None
    observed_timestamp: int | None
    observed_price: float | None
    price_candidate_used: PriceCandidate | None
    missing_status: MissingObservationStatus | None
    gross_return: float | None
    completeness_complete: bool | None
    mfe: ExcursionResult | None
    mae: ExcursionResult | None


@dataclass(frozen=True)
class CanonicalForwardResult:
    """The engine's one output shape -- lineage aligned to UEF-1/UEF-2A, no duplicate identity authority (item 27).

    ``policy_declared_reference_provenance``/``resolved_reference_provenance``
    (UEF-2B FIX1 / H6): these are two DIFFERENT pieces of information that
    the prior revision collapsed into one field with an invented precedence
    (``policy provenance > resolved_reference provenance``) that no frozen
    UEF-1/UEF-2A contract actually declares. `ReferenceResolutionPolicy.
    provenance` (frozen, static, policy-level -- "which upstream algorithm
    this CALCULATOR always uses") and `ResolvedReference.provenance`
    (UEF-2B's own engine-input field -- whatever a specific CALLER chose to
    attach for one specific invocation) are kept fully separate here; no
    precedence between them is invented. Both are `CanonicalForwardResult`'s
    OWN fields (UEF-2B's own result type, not a UEF-2A contract), so
    splitting them is a UEF-2B execution fix, not a UEF-2A amendment.
    """

    event_ref: EventRef | None
    policy_id: str
    policy_version: str
    legacy_program: str
    source_result_cost_semantics: SourceResultCostSemantics
    cost_note: str
    reference_timestamp: int
    reference_price: float | None
    policy_declared_reference_provenance: str
    resolved_reference_provenance: str
    horizons: tuple[HorizonResult, ...]


# =========================================================================
# Generic helpers (no program names, no hidden clock, no hidden I/O)
# =========================================================================


def _is_valid_price(value: object) -> bool:
    """The one canonical price-validity rule, generalized from EVERY real calculator's own
    ``or 0.0``/``if price <= 0: return None`` guard (item 7) -- None, non-finite, and
    non-positive values are never a resolved candidate. No market-specific (e.g. Kiwoom
    signed-price) normalization is added here -- that is an execution-domain concern."""

    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0.0


def resolve_ordered_price(chain: PriceResolutionPolicy, *, observation: CanonicalObservation | None, resolved_reference: ResolvedReference, current_origin: ResolvedOrigin | None = None) -> PriceResolution:
    """Execute a `PriceResolutionPolicy` exactly as declared -- first valid candidate wins, no invented fallback (item 6).

    Two candidates are resolved from episode/horizon-level state rather than
    the per-observation ``fields`` bag, because the FROZEN `PriceCandidate`
    vocabulary itself defines them that way, never because of which
    calculator is involved: `REFERENCE_PRICE` is always the policy's own
    PRIMARY resolved reference price (episode-wide); `FIXED_OBSERVED_PRICE`
    means "already resolved upstream, no lookup at all" -- it is THIS
    horizon's own resolved origin price (``current_origin``, e.g. Q11's
    zero-offset `ACTUAL_EXIT` checkpoint), never looked up in an
    observation. Every other candidate is read from the observation's own
    canonical field bag.
    """

    for candidate in chain.authorities:
        if candidate is PriceCandidate.REFERENCE_PRICE:
            value = resolved_reference.reference_price
        elif candidate is PriceCandidate.FIXED_OBSERVED_PRICE:
            value = current_origin.price if current_origin is not None else None
        else:
            value = observation.fields.get(candidate) if observation is not None else None
        if _is_valid_price(value):
            return PriceResolution(price=float(value), candidate_used=candidate)
    return PriceResolution(price=None, candidate_used=None)


def validate_evidence(observation_policy: ObservationPolicy, observation: CanonicalObservation | None) -> bool:
    """Does the found observation's own evidence-quality state match what this checkpoint declares it requires?"""

    if observation_policy.evidence_requirement is None:
        return True
    if observation is None:
        return False
    return observation.evidence is observation_policy.evidence_requirement


def validate_completeness(policy: DataCompletenessPolicy | None, *, window_start: int, window_end: int, end_inclusive: bool, observations_in_window: Sequence[CanonicalObservation]) -> bool:
    """Gap-check an excursion window's own intermediate observations (item 18/35). ``None`` policy always passes.

    UEF-2B FIX1 / H1: `CONTIGUOUS_INTERVAL` means every expected grid slot
    (``window_start``, ``window_start+interval``, ...) is present EXACTLY
    once -- not merely that the observation COUNT matches the expected
    count. A count-only check (the Fix1-audit-flagged bug) passes on a
    pathological input that drops one expected minute and duplicates
    another, or that has one timestamp off-grid, even though `len(...)`
    happens to match. This checks the actual timestamp SET against the
    expected grid SET, and separately rejects any duplicate timestamp
    within the window outright (a duplicate can never be "contiguous").
    """

    if policy is None:
        return True
    if policy.kind is not DataCompletenessKind.CONTIGUOUS_INTERVAL:
        raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: DataCompletenessKind {policy.kind!r} has no generic engine implementation")
    interval = policy.interval_seconds
    expected_count = int((window_end - window_start) // interval) + (1 if end_inclusive else 0)
    expected_slots = {int(window_start + i * interval) for i in range(expected_count)}
    actual_timestamps = [obs.timestamp for obs in observations_in_window]
    if len(actual_timestamps) != len(set(actual_timestamps)):
        return False  # a duplicate timestamp inside the window is never "contiguous"
    actual_slots = set(actual_timestamps)
    if policy.require_all_expected_observations:
        return actual_slots == expected_slots
    return expected_slots.issubset(actual_slots)


def resolve_missing(*, observation_policy: ObservationPolicy, evidence_ok: bool) -> MissingObservationStatus:
    """Map a failed observation search to a `MissingObservationStatus`, purely from policy authority (item 17)."""

    if not evidence_ok:
        return MissingObservationStatus.EVIDENCE_INVALID
    mapping = {
        MissingResolutionPolicy.KEEP_PENDING: MissingObservationStatus.TARGET_NOT_REACHED,
        MissingResolutionPolicy.EXPIRE_AFTER_TOLERANCE: MissingObservationStatus.NO_OBSERVATION_WITHIN_TOLERANCE,
        MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY: MissingObservationStatus.NO_DATA,
        MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK: MissingObservationStatus.SESSION_ENDED,
    }
    status = mapping.get(observation_policy.missing_resolution)
    if status is None:
        raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: MissingResolutionPolicy {observation_policy.missing_resolution!r} has no generic engine mapping")
    return status


def _fixed_clock_epoch(*, calendar_date: str, clock: FixedClockSpec) -> int:
    hour, minute = (int(part) for part in clock.clock_label.split(":"))
    dt = datetime.fromisoformat(calendar_date).replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=ZoneInfo(clock.timezone))
    return int(dt.timestamp())


def resolve_forward_session(spec: ForwardSessionSpec, *, origin_timestamp: int, session_context: SessionContext) -> tuple[str | None, MissingObservationStatus | None]:
    """`FORWARD_SESSION` traversal (item 12/13/36): the Nth future available session, or a definitive missing status.

    ``required_available_sessions`` intermediate sessions must ALL already
    have observations -- if not, this returns `INSUFFICIENT_FUTURE_SESSIONS`
    immediately; it never substitutes a shorter horizon's target (item 13).
    """

    selected = session_context.future_session_dates[: spec.session_offset]
    if len(selected) < spec.session_offset:
        return None, MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS
    required = selected[: spec.required_available_sessions]
    if any(day not in session_context.sessions_with_observations for day in required):
        return None, MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS
    return selected[-1], None


def resolve_session_close(spec: SessionCloseSpec, *, calendar_date: str) -> int:
    """The concrete epoch a `USE_SESSION_CLOSE_FALLBACK` rule substitutes (item 11)."""

    return _fixed_clock_epoch(calendar_date=calendar_date, clock=spec.close_clock)


def resolve_target(horizon: HorizonSpec, *, resolved_reference: ResolvedReference, session_context: SessionContext | None) -> TargetResolution:
    """Compute this horizon's own nominal target -- exactly the `HorizonKind` semantics UEF-2A declares, nothing invented (item 8-13)."""

    origin = resolved_reference.origin_for(horizon.origin)
    if horizon.kind is HorizonKind.RELATIVE_SECONDS:
        return TargetResolution(origin_timestamp=origin.timestamp, target_timestamp=origin.timestamp + int(horizon.relative_seconds))
    if horizon.kind in (HorizonKind.FIXED_CLOCK_TARGET, HorizonKind.SESSION_CLOSE):
        calendar_date = epoch_seconds_to_kst_date(origin.timestamp)
        return TargetResolution(origin_timestamp=origin.timestamp, target_timestamp=_fixed_clock_epoch(calendar_date=calendar_date, clock=horizon.fixed_clock))
    if horizon.kind is HorizonKind.FORWARD_SESSION:
        if session_context is None:
            raise EngineInputError(f"HorizonSpec {horizon.label!r} is FORWARD_SESSION but no SessionContext was supplied")
        target_date, missing = resolve_forward_session(horizon.forward_session, origin_timestamp=origin.timestamp, session_context=session_context)
        return TargetResolution(origin_timestamp=origin.timestamp, target_session_date=target_date, missing_status=missing)
    raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: HorizonKind {horizon.kind!r} has no generic engine implementation")


def _is_eligible_candidate(observation: CanonicalObservation, observation_policy: ObservationPolicy, *, resolved_reference: "ResolvedReference | None", current_origin: "ResolvedOrigin | None") -> bool:
    """UEF-2B FIX1 / H3: `require_positive_volume`/`require_positive_price` executed as a real search-time
    ELIGIBILITY filter -- an ineligible observation is skipped (the search keeps looking), never silently
    accepted and only discovered invalid afterward. Generic: reads exactly the two frozen `ObservationPolicy`
    fields already declared, no per-calculator branch."""

    if observation_policy.require_positive_volume:
        if observation.volume is None or not (isinstance(observation.volume, (int, float)) and isfinite(observation.volume) and observation.volume > 0.0):
            return False
    if observation_policy.require_positive_price:
        if resolved_reference is None:
            raise EngineInputError("require_positive_price=True requires a ResolvedReference to evaluate eligibility")
        resolution = resolve_ordered_price(observation_policy.price_resolution, observation=observation, resolved_reference=resolved_reference, current_origin=current_origin)
        if resolution.price is None:
            return False
    return True


def resolve_observation(
    observation_policy: ObservationPolicy,
    *,
    target: TargetResolution,
    observations: Sequence[CanonicalObservation],
    resolved_reference: "ResolvedReference | None" = None,
    current_origin: "ResolvedOrigin | None" = None,
) -> CanonicalObservation | None:
    """Search `observations` per the policy's own selection mode/tolerance -- one generic search, no per-calculator branch (item 14/15).

    ``observations`` must already be deduplicated/validated for conflicting
    same-timestamp entries (see `_validate_and_deduplicate`, called once by
    `evaluate_forward`) -- this function assumes at most one observation per
    timestamp and never itself picks among duplicates.
    """

    def eligible(observation: CanonicalObservation) -> bool:
        return _is_eligible_candidate(observation, observation_policy, resolved_reference=resolved_reference, current_origin=current_origin)

    if target.target_session_date is not None:
        candidates = [obs for obs in observations if epoch_seconds_to_kst_date(obs.timestamp) == target.target_session_date]
        if observation_policy.selection_mode is ObservationSelectionMode.LAST_AVAILABLE:
            for obs in reversed(candidates):
                if eligible(obs):
                    return obs
            return None
        raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: ObservationSelectionMode {observation_policy.selection_mode!r} has no generic FORWARD_SESSION implementation")

    target_ts = target.target_timestamp
    if observation_policy.selection_mode is ObservationSelectionMode.EXACT:
        for obs in observations:
            if obs.timestamp == target_ts:
                return obs if eligible(obs) else None
        return None
    if observation_policy.selection_mode is ObservationSelectionMode.FIRST_AT_OR_AFTER:
        # UEF-2B FIX1 / H4 (unaffected here, restated for symmetry): the
        # window is [target_ts, target_ts + lookahead] -- FIRST_AT_OR_AFTER
        # never looks backward, so lookback_seconds plays no role (and is
        # required to be 0 for this mode by the frozen `ObservationPolicy`
        # invariants it does not itself enforce beyond EXACT).
        for obs in observations:
            if obs.timestamp < target_ts:
                continue
            if observation_policy.lookahead_seconds is not None and obs.timestamp > target_ts + observation_policy.lookahead_seconds:
                break
            if eligible(obs):
                return obs
        return None
    if observation_policy.selection_mode is ObservationSelectionMode.LAST_AVAILABLE:
        # UEF-2B FIX1 / H4 fix: the real bug was rejecting every observation
        # BEFORE target_ts outright, making lookback_seconds structurally
        # unreachable. The correct window is [target_ts - lookback,
        # target_ts + lookahead] (lookahead=None => unbounded above);
        # LAST_AVAILABLE picks the temporally LATEST eligible observation
        # inside that window (observations are pre-sorted ascending, so the
        # last qualifying one encountered is the latest).
        lower = target_ts - observation_policy.lookback_seconds
        upper = target_ts + observation_policy.lookahead_seconds if observation_policy.lookahead_seconds is not None else None
        match = None
        for obs in observations:
            if obs.timestamp < lower:
                continue
            if upper is not None and obs.timestamp > upper:
                continue
            if not eligible(obs):
                continue
            match = obs
        return match
    raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: ObservationSelectionMode {observation_policy.selection_mode!r} has no generic engine implementation")


def calculate_gross_return(*, reference_price: float, observed_price: float, policy: GrossReturnPolicy) -> float:
    """The one canonical gross-return formula -- unit/direction taken from `GrossReturnPolicy`, never hardcoded (item 23-25)."""

    direction_multiplier = 1.0 if policy.direction is TradeDirection.LONG else -1.0
    raw = ((observed_price / reference_price) - 1.0) * direction_multiplier
    return raw * 100.0 if policy.return_unit is ReturnUnit.PERCENTAGE_POINTS else raw


def _select_window(observations: Sequence[CanonicalObservation], *, start: int, end: int | None, start_inclusive: bool, end_inclusive: bool) -> list[CanonicalObservation]:
    selected = []
    for obs in observations:
        if start_inclusive:
            if obs.timestamp < start:
                continue
        elif obs.timestamp <= start:
            continue
        if end is not None:
            if end_inclusive:
                if obs.timestamp > end:
                    continue
            elif obs.timestamp >= end:
                continue
        selected.append(obs)
    return selected


def _excursion_bounds(excursion: ExcursionPolicy, *, primary_origin_timestamp: int, horizon_origin_timestamp: int, target_timestamp: int | None, observed_timestamp: int | None) -> tuple[int, int | None]:
    start = (primary_origin_timestamp if excursion.window_end is MfeMaeWindowEnd.ACTUAL_EXIT else horizon_origin_timestamp) + int(excursion.start_offset_seconds)
    end_offset = int(excursion.end_offset_seconds) if excursion.end_offset_seconds is not None else 0
    if excursion.window_end is MfeMaeWindowEnd.TARGET_TIMESTAMP:
        end = target_timestamp + end_offset if target_timestamp is not None else None
    elif excursion.window_end in (MfeMaeWindowEnd.OWN_CHECKPOINT_OBSERVATION, MfeMaeWindowEnd.FORWARD_SESSION_BOUND):
        end = observed_timestamp + end_offset if observed_timestamp is not None else None
    elif excursion.window_end is MfeMaeWindowEnd.ACTUAL_EXIT:
        end = target_timestamp + end_offset if target_timestamp is not None else None
    elif excursion.window_end is MfeMaeWindowEnd.UNBOUNDED_FORWARD:
        end = None
    else:
        raise UEF2AFreezeBlocker(f"UEF2A_FREEZE_BLOCKER: MfeMaeWindowEnd {excursion.window_end!r} has no generic engine implementation")
    return start, end


def _extreme(observations: Sequence[CanonicalObservation], chain: PriceResolutionPolicy | None, *, resolved_reference: ResolvedReference, reference_price: float, return_unit: ReturnUnit, direction_multiplier: float, pick_max: bool, floor_or_cap_zero: bool) -> ExcursionResult | None:
    if chain is None:
        return None
    best: ExcursionResult | None = None
    best_move = None
    for obs in observations:
        resolution = resolve_ordered_price(chain, observation=obs, resolved_reference=resolved_reference)
        if resolution.price is None:
            continue
        raw = ((resolution.price / reference_price) - 1.0) * direction_multiplier
        move = raw * 100.0 if return_unit is ReturnUnit.PERCENTAGE_POINTS else raw
        if best_move is None or (move > best_move if pick_max else move < best_move):
            best_move = move
            best = ExcursionResult(price=resolution.price, candidate_used=resolution.candidate_used, move=move, observed_timestamp=obs.timestamp)
    if best is None:
        return None
    if floor_or_cap_zero:
        bounded_move = max(0.0, best.move) if pick_max else min(0.0, best.move)
        return ExcursionResult(price=best.price, candidate_used=best.candidate_used, move=bounded_move, observed_timestamp=best.observed_timestamp)
    return best


def resolve_excursion(
    excursion: ExcursionPolicy,
    *,
    window_observations: Sequence[CanonicalObservation],
    resolved_reference: ResolvedReference,
    reference_price: float,
    return_unit: ReturnUnit,
    direction: TradeDirection,
    complete: bool,
) -> tuple[ExcursionResult | None, ExcursionResult | None]:
    """Generic MFE/MAE resolution -- each ordered chain executed independently, direction applied only when declared (item 20-24)."""

    if excursion.completeness is not None and not complete:
        return None, None
    direction_multiplier = (1.0 if direction is TradeDirection.LONG else -1.0) if excursion.direction_aware else 1.0
    mfe = _extreme(window_observations, excursion.mfe_price_resolution, resolved_reference=resolved_reference, reference_price=reference_price, return_unit=return_unit, direction_multiplier=direction_multiplier, pick_max=True, floor_or_cap_zero=excursion.mfe_floor_zero)
    mae = _extreme(window_observations, excursion.mae_price_resolution, resolved_reference=resolved_reference, reference_price=reference_price, return_unit=return_unit, direction_multiplier=direction_multiplier, pick_max=False, floor_or_cap_zero=excursion.mae_cap_zero)
    return mfe, mae


# =========================================================================
# Public entry point
# =========================================================================


def _evaluate_horizon(horizon: HorizonSpec, *, policy: ForwardPolicy, resolved_reference: ResolvedReference, observations: Sequence[CanonicalObservation], session_context: SessionContext | None) -> HorizonResult:
    target = resolve_target(horizon, resolved_reference=resolved_reference, session_context=session_context)
    if not target.resolved:
        return HorizonResult(
            label=horizon.label, horizon_set_id=horizon.horizon_set_id, origin_timestamp=target.origin_timestamp,
            target_timestamp=None, target_session_date=target.target_session_date, observed_timestamp=None, observed_price=None, price_candidate_used=None,
            missing_status=target.missing_status, gross_return=None, completeness_complete=None, mfe=None, mae=None,
        )

    current_origin = resolved_reference.origin_for(horizon.origin)
    observed = resolve_observation(horizon.observation, target=target, observations=observations, resolved_reference=resolved_reference, current_origin=current_origin)
    evidence_ok = validate_evidence(horizon.observation, observed)
    price_resolution = PriceResolution(price=None, candidate_used=None)
    if observed is not None and evidence_ok:
        price_resolution = resolve_ordered_price(horizon.observation.price_resolution, observation=observed, resolved_reference=resolved_reference, current_origin=current_origin)

    if (observed is None or not evidence_ok or price_resolution.price is None) and horizon.observation.missing_resolution is MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK:
        fallback_date = epoch_seconds_to_kst_date(target.origin_timestamp)
        fallback_epoch = resolve_session_close(horizon.observation.session_close_fallback, calendar_date=fallback_date)
        fallback_target = TargetResolution(origin_timestamp=target.origin_timestamp, target_timestamp=fallback_epoch)
        fallback_policy = ObservationPolicy(selection_mode=ObservationSelectionMode.LAST_AVAILABLE, price_resolution=horizon.observation.session_close_fallback.price_resolution, missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY)
        observed = resolve_observation(fallback_policy, target=fallback_target, observations=observations, resolved_reference=resolved_reference, current_origin=current_origin)
        evidence_ok = True
        if observed is not None:
            price_resolution = resolve_ordered_price(fallback_policy.price_resolution, observation=observed, resolved_reference=resolved_reference, current_origin=current_origin)

    if observed is None or not evidence_ok or price_resolution.price is None:
        return HorizonResult(
            label=horizon.label, horizon_set_id=horizon.horizon_set_id, origin_timestamp=target.origin_timestamp,
            target_timestamp=target.target_timestamp, target_session_date=target.target_session_date, observed_timestamp=observed.timestamp if observed is not None else None,
            observed_price=None, price_candidate_used=None,
            missing_status=resolve_missing(observation_policy=horizon.observation, evidence_ok=evidence_ok),
            gross_return=None, completeness_complete=None, mfe=None, mae=None,
        )

    reference_price = resolved_reference.reference_price
    if reference_price is None:
        raise EngineInputError("ResolvedReference.reference_price is required to calculate a gross return")
    gross_return = calculate_gross_return(reference_price=reference_price, observed_price=price_resolution.price, policy=policy.gross_return)

    mfe = mae = None
    completeness_complete = None
    if horizon.excursion is not None:
        start, end = _excursion_bounds(
            horizon.excursion, primary_origin_timestamp=resolved_reference.reference_timestamp, horizon_origin_timestamp=target.origin_timestamp,
            target_timestamp=target.target_timestamp, observed_timestamp=observed.timestamp,
        )
        window = _select_window(observations, start=start, end=end, start_inclusive=horizon.excursion.start_inclusive, end_inclusive=horizon.excursion.end_inclusive)
        if horizon.excursion.completeness is not None and end is not None:
            completeness_complete = validate_completeness(horizon.excursion.completeness, window_start=start, window_end=end, end_inclusive=horizon.excursion.end_inclusive, observations_in_window=window)
        mfe, mae = resolve_excursion(
            horizon.excursion, window_observations=window, resolved_reference=resolved_reference, reference_price=reference_price,
            return_unit=policy.gross_return.return_unit, direction=policy.gross_return.direction, complete=completeness_complete if completeness_complete is not None else True,
        )

    return HorizonResult(
        label=horizon.label, horizon_set_id=horizon.horizon_set_id, origin_timestamp=target.origin_timestamp,
        target_timestamp=target.target_timestamp, target_session_date=target.target_session_date, observed_timestamp=observed.timestamp, observed_price=price_resolution.price,
        price_candidate_used=price_resolution.candidate_used, missing_status=None, gross_return=gross_return,
        completeness_complete=completeness_complete, mfe=mfe, mae=mae,
    )


def _validate_and_deduplicate(observations: Sequence[CanonicalObservation]) -> tuple[CanonicalObservation, ...]:
    """UEF-2B FIX1 / H2: order-independent, deterministic handling of same-timestamp observations.

    No frozen UEF-1/UEF-2A contract defines a precedence for two
    observations sharing a timestamp -- so this never picks a "winner" by
    input order (or by any other invented rule). Two observations at the
    same timestamp with IDENTICAL field/volume/evidence values are a
    harmless duplicate (collapsed to one, order plays no role since they
    are interchangeable by definition of `==`); two with DIFFERING values
    are a genuine, irreducible ambiguity this engine refuses to guess at.
    """

    by_timestamp: dict[int, CanonicalObservation] = {}
    for observation in observations:
        existing = by_timestamp.get(observation.timestamp)
        if existing is None:
            by_timestamp[observation.timestamp] = observation
        elif existing != observation:
            raise AmbiguousObservationError(
                f"two observations at timestamp={observation.timestamp} have conflicting field values "
                f"({existing!r} vs {observation!r}) -- UEF-1/UEF-2A define no tie-break authority for this; "
                "the caller must resolve the ambiguity before calling evaluate_forward"
            )
    return tuple(sorted(by_timestamp.values(), key=lambda observation: observation.timestamp))


def evaluate_forward(
    *,
    event_ref: EventRef | None = None,
    policy: ForwardPolicy,
    resolved_reference: ResolvedReference,
    observations: Sequence[CanonicalObservation],
    session_context: SessionContext | None = None,
) -> CanonicalForwardResult:
    """The one public UEF-2B entry point -- deterministic given identical inputs (item 4/28), never a program name in sight.

    ``policy`` is a frozen `ForwardPolicy` -- any of the 14 semantic
    profiles in `profiles.py`, or any future one, with zero special-casing.
    """

    ordered_observations = _validate_and_deduplicate(observations)
    horizons = tuple(
        _evaluate_horizon(horizon, policy=policy, resolved_reference=resolved_reference, observations=ordered_observations, session_context=session_context)
        for horizon in policy.horizons
    )
    return CanonicalForwardResult(
        event_ref=event_ref,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        legacy_program=policy.legacy_program,
        source_result_cost_semantics=policy.source_result_cost_semantics,
        cost_note=policy.cost_note,
        reference_timestamp=resolved_reference.reference_timestamp,
        reference_price=resolved_reference.reference_price,
        policy_declared_reference_provenance=policy.reference_resolution.provenance,
        resolved_reference_provenance=resolved_reference.provenance,
        horizons=horizons,
    )


__all__ = [
    "EngineInputError",
    "AmbiguousObservationError",
    "UEF2AFreezeBlocker",
    "CanonicalObservation",
    "ResolvedOrigin",
    "ResolvedReference",
    "SessionContext",
    "PriceResolution",
    "TargetResolution",
    "ExcursionResult",
    "HorizonResult",
    "CanonicalForwardResult",
    "resolve_ordered_price",
    "validate_evidence",
    "validate_completeness",
    "resolve_missing",
    "resolve_session_close",
    "resolve_forward_session",
    "resolve_target",
    "resolve_observation",
    "calculate_gross_return",
    "resolve_excursion",
    "evaluate_forward",
]
