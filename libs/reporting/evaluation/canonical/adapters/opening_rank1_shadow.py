"""UEF-4B-3 -- Opening Shadow 1A canonical adapter + shared Opening-family
candle parser.

Opening Shadow is the UEF-4A-approved PRIMARY EVIDENCE family covering
THREE genuinely distinct legacy calculators:

- **1A** (this module) -- `libs/reporting/opening_rank1_shadow/
  latent_forward.py::_observe` -- "Latent Reactivation": forward-measures
  a SYMBOL's own LATER re-detection ("fresh trigger") after an earlier
  appearance. NOT a new adapter family -- reuses the frozen
  `forward_measurement_adapter` generic layer verbatim (GROSS_ONLY, same
  shape as Q9/Q10 Semiconductor/Q12 Calc1).
- **1B/1C** -- `already_net_shadow_adapter.py` (this package, sibling
  module) -- `libs/research/opening_rank1_longitudinal/delayed_outcomes.py::
  forward_30m_net`/`delayed_path`.

1A IS A DIFFERENT PHYSICAL EVENT POPULATION FROM 1B/1C (verified directly
against source, not inferred from naming): 1A's own sample unit is a
"fresh trigger" row (`watch_id`/`trigger_day`/`trigger_epoch`/`symbol`,
built by `_fresh_triggers()` from `redetections[].first_signal_evidence`
in a watch payload) -- a genuinely SEPARATE, LATER real-world event from
whatever "initial" rank-1 appearance 1B/1C measure (1A's own row even
carries an `initial_episode_id`/`initial_day` PROVENANCE link back to
that initial appearance, but 1A's OWN forward measurement is anchored to
the fresh RE-detection's own `trigger_epoch`, never the initial one).
1A and 1B/1C therefore get INDEPENDENT canonical identities -- this is
NOT evidence duplication, it is two real, separately-occurring events.

NOT part of this adapter's scope, verified structurally (this module
imports nothing from either): `opening_rank1_controlled_probe.py`
(Opening Rank-1 Controlled Probe) and `controlled_mock_lanes/` (Controlled
Mock Lane) -- both are execution-outcome evidence (real/mock order
submission results), explicitly excluded from UEF-4B's read-only
evaluation-adapter scope by UEF-4A's own inventory (Table D).

"Opening Alpha" is a REPORTING ATTRIBUTION LABEL spanning (at least) four
different components (Shadow 1A/1B/1C, the Controlled Probe, the Short
Alpha Discriminator, the Alpha Research Board -- UEF-4A Section 8), never
one canonical evaluator. Nothing in this adapter is named or provenanced
as though "Opening Alpha" were a single evaluator; every canonical
record's `Provenance.legacy_program` names the ACTUAL underlying
calculator (`opening_rank1_shadow_latent_forward` for 1A).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import EventOrigin, ExecutionMode
from libs.reporting.evaluation.canonical.identity import DerivedFieldKind, DerivedIdentityPart
from libs.reporting.evaluation.canonical.record import EpisodeRecord, Provenance
from libs.reporting.evaluation.canonical.forward import PriceCandidate
from libs.reporting.evaluation.canonical.forward.engine import CanonicalObservation, ResolvedReference
from libs.reporting.evaluation.canonical.forward.profiles import build_opening_shadow_1a_profile
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState

from .forward_measurement_adapter import (
    ForwardMeasurementAdapterError,
    build_forward_measurement_episode,
    build_forward_measurement_event_ref,
    checkpoint_to_aggregation_member,
)


class OpeningShadowAdapterError(ForwardMeasurementAdapterError):
    """Raised for an Opening Shadow legacy-input problem (any variant) -- fail fast, never repair."""


SOURCE_NAMESPACE = "opening_rank1_shadow"
HYPOTHESIS_ID_1A = "opening_rank1_shadow_latent_reactivation"  # real contracts.py::COHORT_ID-adjacent program label

LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION = "latent_reactivation_forward.v1"
# The real, repo-relative artifact family path layout `build_latent_
# reactivation_watch`/`build_latent_reactivation_forward` actually write
# to (verified directly against source -- see `_verify_1a_artifact_origin`).
_LATENT_REACTIVATION_FORWARD_PATH_SUFFIX = ("opening_rank1_shadow", "latent_watch", "latent_reactivation_forward.json")


def _finite_float(value: Any, *, field: str) -> float:
    """FIX1-lesson hardening (same rule as Q10/Q12): reject NaN/+inf/-inf outright."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OpeningShadowAdapterError(f"candles_to_observations: {field}={value!r} is not a real number") from exc
    if not math.isfinite(number):
        raise OpeningShadowAdapterError(f"candles_to_observations: {field}={value!r} is not finite (NaN/inf are never valid)")
    return number


def candles_to_observations(rows: Sequence[Mapping[str, Any]]) -> list[CanonicalObservation]:
    """Shared OHLCV-dict -> `CanonicalObservation` translation for the whole
    Opening Shadow family (1A here, 1B/1C in the sibling module). A
    deliberate Opening-local copy of the same generic pattern
    `q10_semiconductor.py`/`q12_baseline_btc_woori.py` each declare
    independently -- NOT a cross-family import from either (each family
    owns its own translation; none of Q10/Q12's frozen/approved files are
    touched or depended on here). Timestamp: `ts<=0` rejected outright
    (never silently dropped). Price fields: NaN/inf/negative rejected;
    exactly `0.0` passes through unresolved for `high`/`low` (Opening
    Shadow 1A's own frozen profile chain,
    `_chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)`,
    correctly falls through on an invalid 0 candidate -- matches
    `latent_forward.py::_observe`'s own `high = ... or entry_price`
    fallback exactly, per the frozen profile's own docstring). `close`
    must be finite-positive if present (matches this system's own real
    upstream candle-loading contract, `_normalize_rows`'s `close<=0:
    continue` filter). `volume`: not load-bearing for Opening Shadow's own
    checkpoint/excursion logic (confirmed by direct source read -- neither
    `_observe` nor `forward_30m_net`/`delayed_path` reference `volume` at
    all) -- zero allowed, NaN/inf/negative rejected.
    """

    observations: list[CanonicalObservation] = []
    for row in rows:
        ts = int(row.get("ts") or 0)
        if ts <= 0:
            raise OpeningShadowAdapterError(
                f"candles_to_observations: candle has invalid timestamp ts={ts!r} (raw={row.get('ts')!r}) -- "
                "a non-positive candle timestamp is rejected outright, never silently dropped"
            )
        fields: dict[PriceCandidate, float] = {}
        for key, candidate in (
            ("open", PriceCandidate.BAR_OPEN),
            ("high", PriceCandidate.BAR_HIGH),
            ("low", PriceCandidate.BAR_LOW),
        ):
            value = row.get(key)
            if value is None:
                continue
            number = _finite_float(value, field=key)
            if number < 0:
                raise OpeningShadowAdapterError(f"candles_to_observations: {key}={number!r} is negative -- never a legitimate sentinel or valid price")
            fields[candidate] = number
        close_value = row.get("close")
        if close_value is not None:
            close_number = _finite_float(close_value, field="close")
            if close_number <= 0:
                raise OpeningShadowAdapterError(f"candles_to_observations: close={close_number!r} must be strictly positive")
            fields[PriceCandidate.BAR_CLOSE] = close_number
        volume_value = row.get("volume")
        volume: float | None = None
        if volume_value is not None:
            volume = _finite_float(volume_value, field="volume")
            if volume < 0:
                raise OpeningShadowAdapterError(f"candles_to_observations: volume={volume!r} is negative -- never valid")
        observations.append(CanonicalObservation(timestamp=ts, fields=fields, volume=volume))
    return observations


@dataclass(frozen=True)
class OpeningShadow1ACandidate:
    """One "fresh trigger" (latent reactivation) row, parsed from the real
    `_fresh_triggers()` output shape. A genuinely DIFFERENT physical event
    from whatever initial rank-1 appearance `initial_episode_id` links
    back to -- see module docstring."""

    watch_id: str
    trading_date: str
    symbol: str
    trigger_epoch: int
    trigger_decision_id: str
    rank: int | None
    day_integrity_status: str  # "VALID" or something else -- policy-level exclusion gate
    initial_episode_id: str
    initial_day: str


def _parse_1a_candidate(row: Mapping[str, Any]) -> OpeningShadow1ACandidate:
    """Parse one real `_fresh_triggers()` row. Fail-fast on missing/invalid
    load-bearing fields. FIX2: internal-only -- never a public ingestion
    entrypoint on its own (see `canonicalize_opening_shadow_1a_artifact`,
    the module's only supported/public entrypoint); a bare row dict must
    never reach a canonical record without first passing this module's
    artifact-origin verification."""

    watch_id = str(row.get("watch_id") or "").strip()
    if not watch_id:
        raise OpeningShadowAdapterError("_parse_1a_candidate: row.watch_id is required")
    trading_date = str(row.get("trigger_day") or "").strip()
    if not trading_date:
        raise OpeningShadowAdapterError(f"_parse_1a_candidate: watch_id={watch_id!r} has no trigger_day")
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        raise OpeningShadowAdapterError(f"_parse_1a_candidate: watch_id={watch_id!r} has no symbol")
    trigger_epoch = row.get("trigger_epoch")
    if trigger_epoch is None or int(trigger_epoch) <= 0:
        raise OpeningShadowAdapterError(f"_parse_1a_candidate: watch_id={watch_id!r} has invalid trigger_epoch={trigger_epoch!r}")
    rank = row.get("rank")
    return OpeningShadow1ACandidate(
        watch_id=watch_id,
        trading_date=trading_date,
        symbol=symbol,
        trigger_epoch=int(trigger_epoch),
        trigger_decision_id=str(row.get("trigger_decision_id") or ""),
        rank=int(rank) if rank is not None else None,
        day_integrity_status=str(row.get("trigger_day_integrity_status") or "VALID"),
        initial_episode_id=str(row.get("initial_episode_id") or ""),
        initial_day=str(row.get("initial_day") or ""),
    )


@dataclass(frozen=True)
class _VerifiedOpeningShadow1ARecord:
    """FIX2 HIGH#1/#2 -- the ONLY input type `_build_1a_episode`/
    `_build_1a_exclusion_record` accept. Wrapping (rather than accepting a
    bare `OpeningShadow1ACandidate`) means the module's internal
    episode-building/exclusion-building helpers are never mistaken for a
    supported public entrypoint -- the ONE supported public entrypoint,
    `canonicalize_opening_shadow_1a_artifact`, is also the only function
    in this module that constructs this wrapper, and it does so only
    after `_verify_1a_artifact_origin` has confirmed both the real
    artifact family/path layout and the real persisted `schema_version`.
    This is not a cryptographic guarantee (nothing in Python prevents a
    caller from constructing this wrapper directly); it is an API-surface
    discipline guarantee -- the normal, documented, `__all__`-exported
    path cannot accidentally canonicalize unverified input."""

    candidate: OpeningShadow1ACandidate


def _resolve_1a_entry(candidate: OpeningShadow1ACandidate, candles: Sequence[Mapping[str, Any]]) -> tuple[int, float] | None:
    """Reproduces `_observe`'s own entry resolution EXACTLY
    (`latent_forward.py:96-103`): the first candle strictly AFTER
    `trigger_epoch`, price = `open` if truthy else `close`. This is Layer
    A reference resolution -- the frozen engine never does this itself
    (`ForwardPolicy.reference_resolution` is `_external_ref`, i.e. the
    caller/adapter resolves it) -- so this adapter reproduces the SAME
    search legacy performs, never re-deriving a different rule."""

    ordered = sorted(candles, key=lambda row: int(row.get("ts") or 0))
    entry = next((row for row in ordered if int(row.get("ts") or 0) > candidate.trigger_epoch), None)
    if entry is None:
        return None
    entry_epoch = int(entry.get("ts") or 0)
    open_price = entry.get("open")
    close_price = entry.get("close")
    entry_price = float(open_price) if open_price else (float(close_price) if close_price else None)
    if entry_price is None or entry_price <= 0:
        return None
    return entry_epoch, entry_price


def _build_1a_episode(record: _VerifiedOpeningShadow1ARecord, candles: Sequence[Mapping[str, Any]]) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one 1A fresh-trigger sample.

    Delegates 100% to the frozen, generic `forward_measurement_adapter`
    layer with the frozen UEF-2A `build_opening_shadow_1a_profile()` --
    NO new adapter family, NO duplicated identity/checkpoint/aggregation
    logic. Raises if no reference could be resolved (mirrors `_observe`'s
    own `MISSING_FORWARD_PRICE` case) -- caller must treat this candidate
    as a MISSING population member instead of building an episode for it.

    FIX2 HIGH#1: only accepts a `_VerifiedOpeningShadow1ARecord` (never a
    bare candidate/dict), and defensively rejects a non-VALID candidate
    immediately -- even an accidental internal misuse must fail fast here
    rather than silently producing a normal EpisodeRecord for an excluded
    row (real `build_latent_reactivation_forward` never calls `_observe()`
    for one either; use `_build_1a_exclusion_record` instead).
    """

    candidate = record.candidate
    if candidate.day_integrity_status != "VALID":
        raise OpeningShadowAdapterError(
            f"_build_1a_episode: watch_id={candidate.watch_id!r} has day_integrity_status="
            f"{candidate.day_integrity_status!r} (not VALID) -- a non-VALID candidate must never reach a normal "
            "EpisodeRecord; use _build_1a_exclusion_record instead"
        )
    resolved = _resolve_1a_entry(candidate, candles)
    if resolved is None:
        raise OpeningShadowAdapterError(
            f"_build_1a_episode: watch_id={candidate.watch_id!r} symbol={candidate.symbol!r} has no resolvable "
            "forward reference (no candle after trigger_epoch, or entry price unavailable) -- caller must treat "
            "this candidate as a MISSING population member instead of building an episode for it"
        )
    entry_epoch, entry_price = resolved
    observations = candles_to_observations(candles)
    resolved_reference = ResolvedReference.single(origin=EventOrigin.SIGNAL, timestamp=entry_epoch, price=entry_price)
    event_ref = build_forward_measurement_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        trading_date=candidate.trading_date,
        symbol=candidate.symbol,
        extra_fields={"watch_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=candidate.watch_id)},
    )
    return build_forward_measurement_episode(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID_1A,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date=candidate.trading_date,
        symbol=candidate.symbol,
        horizon_origin=EventOrigin.SIGNAL,
        event_ref=event_ref,
        resolved_reference=resolved_reference,
        observations=observations,
        profiles=(("opening_rank1_shadow_latent_forward", build_opening_shadow_1a_profile()),),
        provenance=Provenance(
            legacy_program="opening_rank1_shadow_latent_forward",
            legacy_schema=LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION,
            source_artifact="/".join(_LATENT_REACTIVATION_FORWARD_PATH_SUFFIX),
            source_function="_observe",
        ),
        metadata={
            "watch_id": candidate.watch_id,
            "trigger_decision_id": candidate.trigger_decision_id,
            "rank": candidate.rank,
            "day_integrity_status": candidate.day_integrity_status,
            "initial_episode_id": candidate.initial_episode_id,
            "initial_day": candidate.initial_day,
        },
    )


@dataclass(frozen=True)
class OpeningShadow1AExclusion:
    """Lineage-preserving record for a 1A fresh-trigger candidate the real
    `build_latent_reactivation_forward` marks
    `EXCLUDED_TRIGGER_DAY_INTEGRITY` (`latent_forward.py:239-246`). The
    real legacy system never calls `_observe()` for these rows at all
    (they are routed straight into its own `excluded` list, bypassing
    forward-price resolution entirely) -- this adapter mirrors that
    exactly and does not attempt resolution for them either.

    Deliberately NOT a new canonical type: the canonical population state
    for an excluded row is `SampleMemberState.EXCLUDED` alone (see
    `_resolve_1a_aggregation_member` below), which the frozen
    `checkpoint_to_aggregation_member` already represents WITHOUT an
    EpisodeRecord (its own `state_override=EXCLUDED` branch discards
    checkpoint and evaluation_record_id entirely -- exclusions are
    already representable without an EpisodeRecord per the frozen UEF-3A
    contract). This dataclass exists purely so the exclusion itself stays
    traceable (watch_id, symbol, trigger_day, trigger_epoch, integrity
    status, exclusion reason, source provenance), never silently dropped.
    """

    watch_id: str
    trading_date: str
    symbol: str
    trigger_epoch: int
    trigger_decision_id: str
    day_integrity_status: str
    exclusion_reason: str
    initial_episode_id: str
    initial_day: str
    legacy_program: str
    legacy_schema: str
    source_artifact: str


def _build_1a_exclusion_record(record: _VerifiedOpeningShadow1ARecord) -> OpeningShadow1AExclusion:
    """Build the lineage-preserving exclusion record for a non-VALID 1A
    candidate. Raises if called on a VALID candidate -- use
    `_build_1a_episode` for those instead; a candidate is either eligible
    (build an episode) or excluded (build this record), never both."""

    candidate = record.candidate
    if candidate.day_integrity_status == "VALID":
        raise OpeningShadowAdapterError(
            f"_build_1a_exclusion_record: watch_id={candidate.watch_id!r} has day_integrity_status='VALID' -- "
            "not an exclusion candidate; use _build_1a_episode instead"
        )
    return OpeningShadow1AExclusion(
        watch_id=candidate.watch_id,
        trading_date=candidate.trading_date,
        symbol=candidate.symbol,
        trigger_epoch=candidate.trigger_epoch,
        trigger_decision_id=candidate.trigger_decision_id,
        day_integrity_status=candidate.day_integrity_status,
        exclusion_reason=f"opening_day_status:{candidate.day_integrity_status}",
        initial_episode_id=candidate.initial_episode_id,
        initial_day=candidate.initial_day,
        legacy_program="opening_rank1_shadow_latent_forward",
        legacy_schema=LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION,
        source_artifact="/".join(_LATENT_REACTIVATION_FORWARD_PATH_SUFFIX),
    )


def _resolve_1a_aggregation_member(
    record: _VerifiedOpeningShadow1ARecord,
    candles: Sequence[Mapping[str, Any]],
    *,
    horizon_label: str,
    cost_policy: CostPolicy,
) -> CanonicalAggregationMember:
    """The 1A population-state gate. Real legacy authority
    (`build_latent_reactivation_forward`) marks a `trigger_day_integrity_
    status != VALID` row `EXCLUDED_TRIGGER_DAY_INTEGRITY` and never runs
    `_observe()` on it -- so a non-VALID candidate here becomes
    `SampleMemberState.EXCLUDED` directly, never MISSING, never a
    0-return, never silently dropped, and never given an attempted
    forward-price resolution the real system itself never performs.

    A VALID candidate follows the ordinary eligible/evaluated-or-missing
    path: `_resolve_1a_entry` decides MISSING (mirrors `_build_1a_episode`'s
    own documented "caller must treat this as MISSING" contract) without
    swallowing any other error class, then the frozen, reused-verbatim
    `checkpoint_to_aggregation_member` (never reimplemented here) performs
    the actual translation -- this function computes no return, cost, or
    completeness value of its own.
    """

    candidate = record.candidate
    if candidate.day_integrity_status != "VALID":
        return checkpoint_to_aggregation_member(
            None, evaluation_record_id="", cost_policy=cost_policy,
            state_override=SampleMemberState.EXCLUDED,
        )
    if _resolve_1a_entry(candidate, candles) is None:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    episode = _build_1a_episode(record, candles)
    checkpoint = next((cp for cp in episode.checkpoints if cp.horizon_label == horizon_label), None)
    if checkpoint is None:
        raise OpeningShadowAdapterError(f"_resolve_1a_aggregation_member: no checkpoint for horizon_label={horizon_label!r}")
    return checkpoint_to_aggregation_member(
        checkpoint, evaluation_record_id=episode.identity.evaluation_record_id, cost_policy=cost_policy,
    )


def _verify_1a_artifact_origin(path: Path) -> Mapping[str, Any]:
    """FIX2 HIGH#2 -- the real 1A artifact-origin gate. Verified directly
    against source (not only the inventory doc), requires BOTH:

    1. the artifact's real, repo-relative FAMILY PATH LAYOUT -- the exact
       `output_root`/filename `build_latent_reactivation_watch`/
       `build_latent_reactivation_forward` actually write to
       (`.../opening_rank1_shadow/latent_watch/latent_reactivation_forward.json`,
       `latent_watch.py:292-303` composing `opening_output_root /
       "latent_watch"` as `output_root`, `latent_forward.py:276` writing
       `Path(output_root) / "latent_reactivation_forward.json"`);
    2. the real persisted `schema_version` literal the same writer stamps
       into the payload itself (`latent_forward.py:268`).

    Neither alone establishes provenance (this is the exact FIX2 defect:
    schema_version alone was only a caller-supplied assertion) -- a
    forged dict that merely carries the right schema_version but was
    never actually located under this artifact family's real path is
    rejected by check 1; a real-looking path whose contents carry the
    wrong (or no) schema_version is rejected by check 2. Neither
    Controlled Probe (`data/logs/opening_rank1_controlled_probe/...`,
    `schema_version=="opening_rank1_controlled_probe.v3"`) nor Controlled
    Mock Lane (`data/logs/controlled_mock_lanes/...`,
    `schema_version=="controlled_mock_lanes.v1"`) ever satisfies either
    check -- both verified directly against their own real writer
    modules (`opening_rank1_controlled_probe.py`,
    `controlled_mock_lanes/contracts.py`+`coordinator.py`+`ledger.py`).
    Path layout is checked repo-relative (suffix match), never against a
    one-off absolute machine path.
    """

    resolved = Path(path)
    suffix_len = len(_LATENT_REACTIVATION_FORWARD_PATH_SUFFIX)
    parts = tuple(resolved.as_posix().split("/")[-suffix_len:])
    if parts != _LATENT_REACTIVATION_FORWARD_PATH_SUFFIX:
        raise OpeningShadowAdapterError(
            f"_verify_1a_artifact_origin: path={str(resolved)!r} is not located under the real "
            f"latent_reactivation_forward artifact family layout "
            f"(.../{'/'.join(_LATENT_REACTIVATION_FORWARD_PATH_SUFFIX)}) -- refusing to treat an "
            "arbitrarily-located file as this source family's artifact"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpeningShadowAdapterError(f"_verify_1a_artifact_origin: could not read {str(resolved)!r}: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise OpeningShadowAdapterError(f"_verify_1a_artifact_origin: {str(resolved)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise OpeningShadowAdapterError(f"_verify_1a_artifact_origin: {str(resolved)!r} does not contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION:
        raise OpeningShadowAdapterError(
            f"_verify_1a_artifact_origin: schema_version={schema_version!r} at {str(resolved)!r} does not match "
            f"the real latent_reactivation_forward artifact's own persisted discriminator "
            f"({LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION!r})"
        )
    return payload


@dataclass(frozen=True)
class OpeningShadow1ACanonicalResult:
    """Adapter-local (NOT canonical) per-candidate result of the approved
    1A ingestion path (`canonicalize_opening_shadow_1a_artifact`).
    Exactly one of `episode`/`exclusion` is ever populated, decided
    entirely by the population gate inside that function -- never left to
    caller discipline: `episode` is set only for a VALID candidate with a
    resolvable forward reference; `exclusion` is set only for a non-VALID
    candidate; both are `None` only for a VALID candidate with no
    resolvable reference (a MISSING population member -- `member.state`
    reflects this)."""

    candidate: OpeningShadow1ACandidate
    member: CanonicalAggregationMember
    episode: EpisodeRecord | None
    exclusion: OpeningShadow1AExclusion | None


def canonicalize_opening_shadow_1a_artifact(
    path: str | Path,
    *,
    candles_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    horizon_label: str,
    cost_policy: CostPolicy,
) -> list[OpeningShadow1ACanonicalResult]:
    """FIX2 -- the ONE approved, public 1A ingestion entrypoint.

    1. reads the artifact through its own real, verified origin (family
       path layout + persisted schema_version, `_verify_1a_artifact_origin`)
       -- never a caller-supplied, already-parsed dict;
    2. parses every row into a verified DTO (`_VerifiedOpeningShadow1ARecord`,
       internal -- never constructible from outside this module's own
       verified path in normal use);
    3. applies the population gate immediately: a VALID row follows the
       normal eligible/evaluated-or-missing path, a non-VALID row becomes
       `SampleMemberState.EXCLUDED` with full lineage preserved
       (`OpeningShadow1AExclusion`) -- there is no way to reach a normal
       EpisodeRecord for a non-VALID row through this function, and no
       way to reach ANY canonical output through this module without
       first passing origin verification.

    Candle data is supplied by the caller (`candles_by_symbol`) rather
    than read from the artifact itself, because the real
    `latent_reactivation_forward.json` artifact's own rows never carry
    OHLCV bars (verified against `latent_forward.py` -- candle data comes
    from a separate real source, `candle_provider.py`'s
    `load_opening_candles`/its own disk cache); this is candle data, not
    evidence-family provenance, so it carries no separate origin concern.
    """

    payload = _verify_1a_artifact_origin(Path(path))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise OpeningShadowAdapterError("canonicalize_opening_shadow_1a_artifact: artifact.rows must be a list")

    results: list[OpeningShadow1ACanonicalResult] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        record = _VerifiedOpeningShadow1ARecord(_parse_1a_candidate(row))
        candidate = record.candidate
        candles = candles_by_symbol.get(candidate.symbol) or ()
        member = _resolve_1a_aggregation_member(record, candles, horizon_label=horizon_label, cost_policy=cost_policy)
        if candidate.day_integrity_status != "VALID":
            results.append(OpeningShadow1ACanonicalResult(
                candidate=candidate, member=member, episode=None, exclusion=_build_1a_exclusion_record(record),
            ))
            continue
        if _resolve_1a_entry(candidate, candles) is None:
            results.append(OpeningShadow1ACanonicalResult(candidate=candidate, member=member, episode=None, exclusion=None))
            continue
        episode = _build_1a_episode(record, candles)
        results.append(OpeningShadow1ACanonicalResult(candidate=candidate, member=member, episode=episode, exclusion=None))
    return results


__all__ = [
    "OpeningShadowAdapterError",
    "SOURCE_NAMESPACE",
    "HYPOTHESIS_ID_1A",
    "LATENT_REACTIVATION_FORWARD_SCHEMA_VERSION",
    "candles_to_observations",
    "OpeningShadow1ACandidate",
    "OpeningShadow1AExclusion",
    "OpeningShadow1ACanonicalResult",
    "canonicalize_opening_shadow_1a_artifact",
]
