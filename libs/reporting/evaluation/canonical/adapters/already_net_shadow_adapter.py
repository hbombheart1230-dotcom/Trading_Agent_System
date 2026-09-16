"""UEF-4B-3 -- Opening Shadow 1B/1C canonical adapter: `already_net_shadow_adapter`.

Source authority (verified directly against real source, not only
`docs/research/uef4_legacy_family_inventory.md`):
`libs/research/opening_rank1_longitudinal/delayed_outcomes.py::
forward_30m_net` (1B) / `::delayed_path` (1C).

1B AND 1C ARE THE SAME PHYSICAL EPISODE (verified directly against
source, not inferred from naming): both operate on the SAME "virtual
buy" MONITOR_DECISION event -- `delayed_path`'s own `baseline`/
`baseline_epoch` come from `case["virtual_buy_price"]`/
`case["virtual_buy_time_kst"]`, which (per the real orchestration in
`opening_rank1_deep_dive/read_model.py::build_case` and
`opening_rank1_longitudinal/pipeline.py`) are the SAME reference point
`forward_30m_net`'s own `entry`/`baseline` resolves. `delayed_path` even
DIRECTLY CONSUMES 1B's own result (`case.get("net_return_30m_pct")`) to
derive its own `delayed_high_opportunity`/`selection_horizon_label`
fields (`delayed_outcomes.py:172-194`) -- a genuine DATA dependency, not
merely a shared label. 1B and 1C are therefore merged into ONE canonical
`EpisodeRecord` per (trading_date, symbol, decision_epoch), with
checkpoints `+30m` (1B) and `d1`/`d3`/`d5` (1C) -- exactly the same
"one physical episode, multiple named horizon-set checkpoints" pattern
UEF-4B-1 already established for Q10 Semiconductor's Calc A/B/C, never
three independent physical samples for one physical episode.

NET_OR_COST_INCLUDED HANDLING: neither `forward_30m_net` nor
`delayed_path` produces a separable gross figure AT ALL (both bake
`ROUND_TRIP_COST_PCT=0.28` into the ONE return figure each field
carries, via the shared `_net()` helper) -- so, exactly like Q12
Calc2/Calc3, this adapter calls the REAL legacy functions DIRECTLY for
the net figures (irreducibly SOURCE_PROVIDED, never recomputed, never
paired with an explicit `CostPolicy`) while delegating
observed/target-timestamp and missing-status bookkeeping to the frozen,
generic `evaluate_forward()` (informational gross only, excluded from
`CanonicalAggregationMember` for NET_OR_COST_INCLUDED members exactly as
the frozen `aggregation.py` contract requires).

`d{n}_max_high_net_pct` (1C's own MFE-shaped field) is ALREADY
cost-adjusted (net-of-cost), unlike a typical raw-price-move MFE --
translated verbatim into `Checkpoint.mfe`, never renormalized or
reinterpreted as a gross excursion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import (
    CheckpointCompleteness,
    EventOrigin,
    ExecutionMode,
    ObservationType,
    ReturnUnit,
)
from libs.reporting.evaluation.canonical.identity import DerivedFieldKind, DerivedIdentityPart
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, Provenance, build_episode_record
from libs.reporting.evaluation.canonical.forward import MissingObservationStatus, SourceResultCostSemantics
from libs.reporting.evaluation.canonical.forward.engine import ResolvedOrigin, ResolvedReference, SessionContext, evaluate_forward
from libs.reporting.evaluation.canonical.forward.profiles import (
    build_opening_shadow_1b_profile,
    build_opening_shadow_1c_profile,
)
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState
from libs.research.opening_rank1_longitudinal.delayed_outcomes import delayed_path, forward_30m_net

from .forward_measurement_adapter import build_forward_measurement_event_ref
from .opening_rank1_shadow import OpeningShadowAdapterError, candles_to_observations


SOURCE_NAMESPACE = "opening_rank1_longitudinal"
HYPOTHESIS_ID = "opening_rank1_longitudinal_delayed_outcomes"  # real source module's own provenance identity
KST = timezone(timedelta(hours=9))

OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION = "opening_rank1_longitudinal.v1"
# The real, repo-relative artifact family path layout `run_opening_rank1_
# longitudinal`'s own default `output_root` writes to (verified directly
# against source -- `pipeline.py:131-133,252` -- see
# `_verify_1bc_artifact_origin`).
_OPENING_RANK1_LONGITUDINAL_PATH_SUFFIX = ("offline_alpha", "opening_rank1_longitudinal", "opening_rank1_longitudinal.json")


def _day(row: Mapping[str, Any]) -> str:
    """Byte-for-byte copy of `delayed_outcomes.py::_day` -- the exact day
    extraction the real legacy functions themselves use (`raw_ts`-prefix
    based, NOT a `ts`+timezone conversion) -- required to reproduce their
    own day-grouping faithfully when this adapter calls them directly."""

    raw = str(row.get("raw_ts") or "")
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def _missing_completeness(status: MissingObservationStatus | None) -> CheckpointCompleteness:
    if status is None:
        raise OpeningShadowAdapterError("_missing_completeness: called with status=None")
    mapping = {
        MissingObservationStatus.TARGET_NOT_REACHED: CheckpointCompleteness.PENDING,
        MissingObservationStatus.NO_DATA: CheckpointCompleteness.MISSING,
        MissingObservationStatus.NO_OBSERVATION_WITHIN_TOLERANCE: CheckpointCompleteness.STALE,
        MissingObservationStatus.SESSION_ENDED: CheckpointCompleteness.MISSING,
        MissingObservationStatus.EVIDENCE_INVALID: CheckpointCompleteness.MISSING,
        MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS: CheckpointCompleteness.MISSING,
    }
    mapped = mapping.get(status)
    if mapped is None:
        raise OpeningShadowAdapterError(f"_missing_completeness: no mapping declared for {status!r}")
    return mapped


@dataclass(frozen=True)
class OpeningShadow1BC(object):
    """One (trading_date, symbol, decision_epoch) "virtual buy" episode --
    the SAME physical event 1B and 1C both evaluate."""

    trading_date: str
    symbol: str
    decision_id: str
    decision_epoch: int


def _parse_1bc_case(
    *,
    trading_date: str,
    symbol: str,
    decision_id: str,
    decision_epoch: int,
) -> OpeningShadow1BC:
    """Fail-fast on missing/invalid load-bearing identity fields. Rank is
    deliberately NOT part of this identity -- 1B/1C's own source
    (`forward_30m_net`/`delayed_path`) never reads a rank field at all;
    it belongs (if anywhere) to the upstream candidate-selection layer,
    never to this episode's own physical identity.

    FIX2: internal-only -- never a public ingestion entrypoint on its own
    (see `canonicalize_opening_shadow_1bc_artifact`, the module's only
    supported/public entrypoint)."""

    trading_date = str(trading_date or "").strip()
    if not trading_date:
        raise OpeningShadowAdapterError("_parse_1bc_case: trading_date is required")
    symbol = str(symbol or "").strip()
    if not symbol:
        raise OpeningShadowAdapterError("_parse_1bc_case: symbol is required")
    if decision_epoch is None or int(decision_epoch) <= 0:
        raise OpeningShadowAdapterError(f"_parse_1bc_case: invalid decision_epoch={decision_epoch!r}")
    return OpeningShadow1BC(
        trading_date=trading_date, symbol=symbol,
        decision_id=str(decision_id or ""), decision_epoch=int(decision_epoch),
    )


@dataclass(frozen=True)
class _VerifiedOpeningShadow1BCRecord:
    """FIX2 HIGH#2 -- the ONLY input type `_build_1bc_episode` accepts.
    Wrapping (rather than a bare `OpeningShadow1BC`) keeps the internal
    episode-building helper from being mistaken for a supported public
    entrypoint -- the one supported public entrypoint,
    `canonicalize_opening_shadow_1bc_artifact`, is also the only function
    that constructs this wrapper, and only after `_verify_1bc_artifact_
    origin` has confirmed both the real artifact family/path layout and
    the real persisted `schema_version`."""

    case: OpeningShadow1BC


def _resolve_1b_entry(case: OpeningShadow1BC, rows: Sequence[Mapping[str, Any]]) -> tuple[int, float] | None:
    """Reproduces `forward_30m_net`'s own entry resolution EXACTLY
    (`delayed_outcomes.py:48-56`): the first row, on `day`, strictly after
    `decision_epoch`, ordered by `ts`; price = `open` else `close`. Layer
    A reference resolution -- the frozen engine never does this itself."""

    day_rows = sorted(
        (row for row in rows if _day(row) == case.trading_date and int(row.get("ts") or 0) > case.decision_epoch),
        key=lambda row: int(row.get("ts") or 0),
    )
    if not day_rows:
        return None
    entry = day_rows[0]
    entry_epoch = int(entry.get("ts") or 0)
    open_price = entry.get("open")
    close_price = entry.get("close")
    baseline = float(open_price) if open_price else (float(close_price) if close_price else None)
    if baseline is None or baseline <= 0:
        return None
    return entry_epoch, baseline


def _build_session_context(case: OpeningShadow1BC, rows: Sequence[Mapping[str, Any]], *, trading_calendar: Sequence[str]) -> SessionContext:
    future_session_dates = tuple(day for day in trading_calendar if day > case.trading_date)
    sessions_with_observations = frozenset(_day(row) for row in rows if _day(row))
    return SessionContext(future_session_dates=future_session_dates, sessions_with_observations=sessions_with_observations)


def _build_1bc_episode(
    record: _VerifiedOpeningShadow1BCRecord,
    rows: Sequence[Mapping[str, Any]],
    *,
    trading_calendar: Sequence[str],
) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` merging Opening Shadow 1B
    (+30m) and 1C (d1/d3/d5) checkpoints for one physical "virtual buy"
    episode. Delegates observed/target-timestamp and missing-status
    bookkeeping to the frozen `evaluate_forward()`; `net_return`/`mfe`
    values come verbatim from the REAL legacy `forward_30m_net`/
    `delayed_path` functions, called directly (irreducibly
    SOURCE_PROVIDED, see module docstring).

    FIX2 HIGH#2: only accepts a `_VerifiedOpeningShadow1BCRecord` (never a
    bare case/dict) -- see `canonicalize_opening_shadow_1bc_artifact`.
    """

    case = record.case
    resolved = _resolve_1b_entry(case, rows)
    if resolved is None:
        raise OpeningShadowAdapterError(
            f"_build_1bc_episode: symbol={case.symbol!r} decision_epoch={case.decision_epoch!r} has no resolvable "
            "forward reference (no same-day candle after decision_epoch) -- caller must treat this case as a "
            "MISSING population member instead of building an episode for it"
        )
    entry_epoch, entry_price = resolved

    # Real legacy functions, called directly -- the actual net figures
    # (irreducibly SOURCE_PROVIDED, never recomputed by this adapter):
    net_30m = forward_30m_net(rows=list(rows), day=case.trading_date, decision_epoch=case.decision_epoch)
    legacy_case = {
        "virtual_buy_price": entry_price,
        "virtual_buy_time_kst": datetime.fromtimestamp(entry_epoch, tz=KST).isoformat(),
        "day": case.trading_date,
        # passed through AS-IS, including None -- `delayed_path` already
        # has its own documented `float(case.get(...) or 0.0)` fallback
        # internally (delayed_outcomes.py:172); this adapter must not add
        # a SECOND, redundant 0.0 substitution of its own on top of it.
        "net_return_30m_pct": net_30m,
    }
    delayed_result = delayed_path(legacy_case, list(rows), trading_calendar=list(trading_calendar))

    observations = candles_to_observations(rows)
    # 1B's own horizon origin is MONITOR_DECISION; 1C's is CUSTOM (per the
    # frozen `build_opening_shadow_1c_profile`) -- but both anchor to the
    # SAME (entry_epoch, entry_price) "virtual buy" reference (see module
    # docstring: 1B/1C are the same physical episode), so both origins are
    # supplied here sharing the identical resolved origin.
    origin = ResolvedOrigin(timestamp=entry_epoch, price=entry_price)
    resolved_reference = ResolvedReference(
        primary_origin=EventOrigin.MONITOR_DECISION,
        origins={EventOrigin.MONITOR_DECISION: origin, EventOrigin.CUSTOM: origin},
    )
    event_ref = build_forward_measurement_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        trading_date=case.trading_date,
        symbol=case.symbol,
        native_id=case.decision_id if case.decision_id else None,
        extra_fields=None if case.decision_id else {"decision_epoch": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=case.decision_epoch)},
    )

    session_context = _build_session_context(case, rows, trading_calendar=trading_calendar)
    profiles = (
        ("opening_rank1_longitudinal_forward_30m_net", build_opening_shadow_1b_profile()),
        ("opening_rank1_longitudinal_delayed_path", build_opening_shadow_1c_profile()),
    )

    checkpoints: list[Checkpoint] = []
    seen_labels: dict[str, str] = {}
    for horizon_set_id, policy in profiles:
        result = evaluate_forward(
            event_ref=event_ref, policy=policy, resolved_reference=resolved_reference,
            observations=observations, session_context=session_context,
        )
        for horizon in result.horizons:
            if horizon.label in seen_labels:
                raise OpeningShadowAdapterError(
                    f"_build_1bc_episode: horizon label {horizon.label!r} declared by both "
                    f"{seen_labels[horizon.label]!r} and {horizon_set_id!r}"
                )
            seen_labels[horizon.label] = horizon_set_id

            if horizon.label == "+30m":
                source_net = net_30m
                source_mfe = None
            else:
                prefix = horizon.label  # "d1"/"d3"/"d5"
                status = delayed_result.get(f"{prefix}_status")
                source_net = delayed_result.get(f"{prefix}_close_net_pct") if status == "OBSERVED" else None
                source_mfe = delayed_result.get(f"{prefix}_max_high_net_pct") if status == "OBSERVED" else None

            if horizon.missing_status is None:
                completeness = CheckpointCompleteness.OBSERVED
                if source_net is None:
                    raise OpeningShadowAdapterError(
                        f"_build_1bc_episode: horizon {horizon.label!r} resolved via the frozen forward engine "
                        "(OBSERVED) but the legacy source's own net figure is None -- contradictory source "
                        "fields, never silently reconciled"
                    )
                net_return = float(source_net)
                mfe = float(source_mfe) if source_mfe is not None else None
            else:
                completeness = _missing_completeness(horizon.missing_status)
                net_return = None
                mfe = None

            checkpoints.append(
                Checkpoint(
                    horizon_label=horizon.label,
                    horizon_origin=EventOrigin.MONITOR_DECISION if horizon.label == "+30m" else EventOrigin.CUSTOM,
                    target_timestamp=horizon.target_timestamp,
                    observed_timestamp=horizon.observed_timestamp,
                    observed_price=horizon.observed_price,
                    gross_return=horizon.gross_return,
                    net_return=net_return,
                    mfe=mfe,
                    mae=None,  # 1B has no excursion at all; 1C is MFE-only -- MAE never populated for this family
                    completeness=completeness,
                    source=horizon_set_id,
                    return_unit=ReturnUnit.PERCENTAGE_POINTS,
                    horizon_set_id=horizon_set_id,
                )
            )

    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID,
        observation_type=ObservationType.SHADOW_ENTRY,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date=case.trading_date,
        symbol=case.symbol,
        event_ref=event_ref,
        checkpoints=tuple(checkpoints),
        provenance=Provenance(
            legacy_program="opening_rank1_longitudinal_delayed_outcomes",
            legacy_schema=OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION,
            source_artifact="/".join(_OPENING_RANK1_LONGITUDINAL_PATH_SUFFIX),
            source_function="forward_30m_net + delayed_path",
        ),
        metadata={
            "decision_id": case.decision_id,
            "decision_epoch": case.decision_epoch,
            "delayed_selection_horizon_label": delayed_result.get("selection_horizon_label"),
        },
    )


def checkpoint_to_net_or_cost_included_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
    state_override: SampleMemberState | None = None,
) -> CanonicalAggregationMember:
    """Opening Shadow's own copy of the same `NET_OR_COST_INCLUDED`
    translation Q12's `hypothesis_forward_adapter.py`/
    `vnext_completeness_adapter.py` each declare independently -- every
    adapter family owns its own translation (UEF-4A Table B is 1:1
    family-per-source); the shape is identical only because these
    families happen to share the same cost semantics, never because one
    imports/reuses another's implementation."""

    if state_override is SampleMemberState.EXCLUDED:
        return CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)
    if checkpoint is None or checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    if checkpoint.net_return is None or checkpoint.observed_timestamp is None:
        raise OpeningShadowAdapterError(
            f"checkpoint_to_net_or_cost_included_member: checkpoint {checkpoint.horizon_label!r} is OBSERVED "
            "but missing net_return/observed_timestamp -- canonical-record consistency defect, never silently "
            "treated as MISSING"
        )
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED,
        evaluation_record_id=evaluation_record_id,
        gross_return=None,
        return_unit=checkpoint.return_unit,
        source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_policy=None,
        source_net_return=checkpoint.net_return,
        observed_timestamp=checkpoint.observed_timestamp,
        target_timestamp=checkpoint.target_timestamp,
    )


def _verify_1bc_artifact_origin(path: Path) -> Mapping[str, Any]:
    """FIX2 HIGH#2 -- the real 1B/1C artifact-origin gate. Verified
    directly against source, requires BOTH:

    1. the artifact's real, repo-relative FAMILY PATH LAYOUT -- the exact
       default `output_root` / filename `run_opening_rank1_longitudinal`
       actually writes to (`.../offline_alpha/opening_rank1_longitudinal/
       opening_rank1_longitudinal.json`, `pipeline.py:131-133,252`);
    2. the real persisted `schema_version` literal the same writer stamps
       into the payload itself (`pipeline.py:230`).

    Neither alone establishes provenance (the exact FIX2 defect: schema_
    version alone was only a caller-supplied assertion). Neither
    Controlled Probe (`data/logs/opening_rank1_controlled_probe/...`,
    `schema_version=="opening_rank1_controlled_probe.v3"`) nor Controlled
    Mock Lane (`data/logs/controlled_mock_lanes/...`,
    `schema_version=="controlled_mock_lanes.v1"`) ever satisfies either
    check -- both verified directly against their own real writer
    modules. Path layout is checked repo-relative (suffix match), never
    against a one-off absolute machine path.
    """

    resolved = Path(path)
    suffix_len = len(_OPENING_RANK1_LONGITUDINAL_PATH_SUFFIX)
    parts = tuple(resolved.as_posix().split("/")[-suffix_len:])
    if parts != _OPENING_RANK1_LONGITUDINAL_PATH_SUFFIX:
        raise OpeningShadowAdapterError(
            f"_verify_1bc_artifact_origin: path={str(resolved)!r} is not located under the real "
            f"opening_rank1_longitudinal artifact family layout "
            f"(.../{'/'.join(_OPENING_RANK1_LONGITUDINAL_PATH_SUFFIX)}) -- refusing to treat an "
            "arbitrarily-located file as this source family's artifact"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpeningShadowAdapterError(f"_verify_1bc_artifact_origin: could not read {str(resolved)!r}: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise OpeningShadowAdapterError(f"_verify_1bc_artifact_origin: {str(resolved)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise OpeningShadowAdapterError(f"_verify_1bc_artifact_origin: {str(resolved)!r} does not contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION:
        raise OpeningShadowAdapterError(
            f"_verify_1bc_artifact_origin: schema_version={schema_version!r} at {str(resolved)!r} does not match "
            f"the real opening_rank1_longitudinal artifact's own persisted discriminator "
            f"({OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION!r})"
        )
    return payload


def _extract_1bc_fields(row: Mapping[str, Any]) -> tuple[str, str, str, int]:
    """Derive `(trading_date, symbol, decision_id, decision_epoch)` from
    one real `events` row. Verified directly against source: real event
    rows (`opening_rank1_deep_dive/read_model.py::build_case`, whose
    output IS the `opening_rank1_deep_dive.json` artifact's own `cases`
    list that `opening_rank1_longitudinal/pipeline.py:141-144` reads
    verbatim and merges through `stage_fate`/`delayed_path` into this
    artifact's own final `events` rows) carry `day`, `symbol`,
    `decision_id`, and `decision_time_kst` -- NOT a raw `decision_epoch`
    int field (`read_model.py:88-97`). `decision_time_kst` is written as
    `epoch_to_kst(episode.get("decision_epoch")) ==
    datetime.fromtimestamp(int(epoch), tz=utc).astimezone(KST).isoformat()`
    (`opening_rank1_deep_dive/loaders.py::epoch_to_kst`) -- a real,
    deterministic, invertible transform of the real epoch, not a
    fabricated derivation; `decision_epoch` is recovered here by
    reversing it exactly (`datetime.fromisoformat(...).timestamp()`)."""

    trading_date = str(row.get("day") or "")
    symbol = str(row.get("symbol") or "")
    decision_id = str(row.get("decision_id") or "")
    decision_time_kst = str(row.get("decision_time_kst") or "")
    decision_epoch = 0
    if decision_time_kst:
        try:
            decision_epoch = int(datetime.fromisoformat(decision_time_kst).timestamp())
        except ValueError:
            decision_epoch = 0
    return trading_date, symbol, decision_id, decision_epoch


@dataclass(frozen=True)
class OpeningShadow1BCCanonicalResult:
    """Adapter-local (NOT canonical) per-event result of the approved
    1B/1C ingestion path (`canonicalize_opening_shadow_1bc_artifact`).
    `episode` is `None` only when no resolvable forward reference exists
    (a MISSING population member) -- 1B/1C has no eligibility-exclusion
    concept of its own (unlike 1A), so this is the only reason `episode`
    is ever unset."""

    case: OpeningShadow1BC
    episode: EpisodeRecord | None


def canonicalize_opening_shadow_1bc_artifact(
    path: str | Path,
    *,
    minute_rows_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    trading_calendar: Sequence[str],
) -> list[OpeningShadow1BCCanonicalResult]:
    """FIX2 -- the ONE approved, public 1B/1C ingestion entrypoint.

    1. reads the artifact through its own real, verified origin (family
       path layout + persisted schema_version, `_verify_1bc_artifact_origin`)
       -- never a caller-supplied, already-parsed dict;
    2. extracts each real `events` row's identity fields
       (`_extract_1bc_fields`) and parses them into a verified DTO
       (`_VerifiedOpeningShadow1BCRecord`, internal);
    3. canonicalizes: a resolvable case gets a normal merged 1B/1C
       EpisodeRecord, an unresolvable one is reported as a MISSING
       population member (`episode=None`) -- there is no way to reach a
       canonical output through this module without first passing origin
       verification.

    Minute-candle data is supplied by the caller (`minute_rows_by_symbol`)
    rather than read from the artifact itself, because the real
    `opening_rank1_longitudinal.json` artifact's own event rows never
    carry OHLCV bars (candle data comes from a separate real source,
    `daily_provider.py`/`microstructure.py`'s own loaders) -- this is
    candle data, not evidence-family provenance, so it carries no
    separate origin concern.
    """

    payload = _verify_1bc_artifact_origin(Path(path))
    events = payload.get("events")
    if not isinstance(events, list):
        raise OpeningShadowAdapterError("canonicalize_opening_shadow_1bc_artifact: artifact.events must be a list")

    results: list[OpeningShadow1BCCanonicalResult] = []
    for row in events:
        if not isinstance(row, Mapping):
            continue
        trading_date, symbol, decision_id, decision_epoch = _extract_1bc_fields(row)
        case = _parse_1bc_case(trading_date=trading_date, symbol=symbol, decision_id=decision_id, decision_epoch=decision_epoch)
        record = _VerifiedOpeningShadow1BCRecord(case)
        rows = minute_rows_by_symbol.get(symbol) or ()
        if _resolve_1b_entry(case, rows) is None:
            results.append(OpeningShadow1BCCanonicalResult(case=case, episode=None))
            continue
        episode = _build_1bc_episode(record, rows, trading_calendar=trading_calendar)
        results.append(OpeningShadow1BCCanonicalResult(case=case, episode=episode))
    return results


__all__ = [
    "SOURCE_NAMESPACE",
    "HYPOTHESIS_ID",
    "OpeningShadow1BC",
    "OpeningShadow1BCCanonicalResult",
    "checkpoint_to_net_or_cost_included_member",
    "OPENING_RANK1_LONGITUDINAL_SCHEMA_VERSION",
    "canonicalize_opening_shadow_1bc_artifact",
]
