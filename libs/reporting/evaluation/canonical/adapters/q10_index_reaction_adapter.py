"""UEF-4B-4 -- Q10 Index Calc F/G canonical adapter: `q10_index_reaction_adapter`.

Source authority (verified directly against real source, not only
`docs/research/uef4_legacy_family_inventory.md`):
`libs/reporting/baseline_samsung_hynix/forward_validation/reaction_reader.py`
(`_stock_reaction` = Calc F for stock targets; `_index_reaction` = Calc G
for index targets -- both delegate to the SAME shared `_stock_reaction`
function; `_index_reaction` only adds a `collector_override` for the 3
governed checkpoints) and
`libs/reporting/baseline_samsung_hynix/forward_validation/pipeline.py`
(`build_q10_forward_validation` -- the real writer of the trusted
artifact this module ingests). `SCHEMA_VERSION`/`PROGRAM_ID`/`TARGETS`/
`CHECKPOINTS` are imported directly from
`forward_validation/contracts.py`, never retyped.

F/G AMBIGUITY RESOLUTION (UEF-4A Table D, this task's Section 6): F and
G are NOT two views over the same physical observation (option B) and
NOT two independent adapter FAMILIES needing separate Q-numbered
programs (option A) -- verified directly against source:
`build_actual_reactions()` (the real pipeline orchestrator) iterates the
SAME 4-entry `TARGETS` tuple and calls the SAME underlying
`_stock_reaction` algorithm for every target, branching only on
`target["kind"]` (`"stock"` -> Calc F's own path; `"index"` -> Calc G's
own path via `_index_reaction`, itself a thin wrapper around
`_stock_reaction`). This is option E: ONE source family / ONE
computational algorithm (`reaction_reader.py`), reused across TWO
DISJOINT PHYSICAL POPULATIONS by target kind -- stock symbols (005930,
000660) for F, index symbols (KOSPI, KOSDAQ) for G. Each (day, symbol)
is its OWN distinct physical event (different symbol => different
`canonical_event_id`, per UEF-1's own identity rule) -- 4 targets/day
produce 4 distinct canonical episodes, never merged, never multiplied.
G's ONLY genuine difference is a richer, collector-governed 3-state
missing taxonomy (ABSENT/INVALID/VERIFIED,
`EvidenceVerificationState`) for its 3 checkpoints (09:30/10:00/CLOSE)
-- an adapter-local MISSING-semantics decision, not a physical-identity
difference.

PHYSICAL EVENT COUNT (representative day, 4 targets): 4 (samsung,
sk_hynix, kospi, kosdaq). EPISODE COUNT: 4 (one `EpisodeRecord` per
target -- Calc F for the 2 stock targets, Calc G for the 2 index
targets). EVALUATION/VIEW COUNT: 1 per episode (no Q10-Semiconductor-
style multi-view aggregation exists in this source). CHECKPOINT COUNT:
Calc F episodes carry 5 checkpoints (09:00/09:03/09:05/09:10/09:15);
Calc G episodes carry 3 checkpoints (09:30/10:00/CLOSE). No evidence
multiplication anywhere in this module.

CALC G ENGINE-INTEGRATION NOTE: the frozen `build_q10_index_calc_g_
profile()` declares 3 `HorizonSpec`s PER governed label (one per
`EvidenceVerificationState` variant -- `profiles.py::_governed`),
meaning its OWN `result.horizons` would carry the SAME label 3 times if
run wholesale through `evaluate_forward()` -- the frozen, must-not-
modify `build_forward_measurement_episode()` explicitly REJECTS a
duplicate horizon label as an adapter/profile-set misconfiguration. This
module therefore does NOT run Calc G's checkpoints through
`evaluate_forward()` at all: the real, persisted
`q10_actual_market_reactions.json` artifact already carries the FINAL,
fully-resolved tri-state outcome per governed checkpoint (baked in by
`_stock_reaction`'s own `collector_override` handling at write time) --
this module reads that resolved `points[label]` value verbatim
(SOURCE-PROVIDED) and calls the frozen, exported
`forward.engine.calculate_gross_return()` directly for the one
percentage-return calculation needed, never reimplementing that
formula. This is the SAME "some legacy-verified protocol stays outside
the frozen engine's own observation-matching machinery, only its
already-resolved value is consumed" precedent UEF-2A itself already
established for Calc H's `PRE_RESOLVED_REFERENCE` -- applied here to
observation-resolution instead of reference-resolution. Calc F has no
such duplicate-label issue and is delegated to `evaluate_forward()` in
full via the frozen, reused-verbatim `forward_measurement_adapter`.

TRUSTED INGESTION: the real writer, `build_q10_forward_validation`
(`pipeline.py:131-181`), persists `q10_actual_market_reactions.json`
under `reports/evaluation/baseline_samsung_hynix/<day>/
q10_forward_validation/`, carrying BOTH a real `schema_version`
(`SCHEMA_VERSION`, imported from `contracts.py`, never retyped) AND a
real `evaluation_program_id` (`PROGRAM_ID`, likewise) -- this module's
loader verifies the artifact's real repo-relative directory family
layout (the `<day>` segment is validated by ISO-date SHAPE, never a
hardcoded date) AND both persisted literals before parsing anything --
one step stronger than Opening Shadow FIX2's own pattern (two
independent persisted discriminators here, not one).

EXECUTION BOUNDARY: this module imports nothing from
`opening_rank1_controlled_probe.py`, `controlled_mock_lanes/`, or any
broker/executor/order module. Q10 Index's REAL controlled-lane
execution symbols (069500/114800/229200/251340, KODEX ETFs --
`controlled_mock_lanes/contracts.py::Q10_INDEX_SYMBOLS`) are NEVER the
same symbols this module ever reads (005930/000660/KOSPI/KOSDAQ, the
underlying stock/index OBSERVATION symbols `contracts.py::TARGETS`
declares) -- evaluation evidence and execution evidence are governed by
completely disjoint symbol universes in the real source, never merely
asserted disjoint by this adapter.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from libs.reporting.baseline_samsung_hynix.forward_validation.contracts import PROGRAM_ID, SCHEMA_VERSION
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import _checkpoint_epoch

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, EventOrigin, ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, Provenance, build_episode_record
from libs.reporting.evaluation.canonical.forward import PriceCandidate
from libs.reporting.evaluation.canonical.forward.engine import CanonicalObservation, ResolvedReference, calculate_gross_return
from libs.reporting.evaluation.canonical.forward.profiles import build_q10_index_calc_f_profile, build_q10_index_calc_g_profile
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState

from .forward_measurement_adapter import (
    ForwardMeasurementAdapterError,
    build_forward_measurement_episode,
    build_forward_measurement_event_ref,
    checkpoint_to_aggregation_member,
)


class Q10IndexAdapterError(ForwardMeasurementAdapterError):
    """Raised for a Q10 Index legacy-input problem (Calc F/G/H, any variant) -- fail fast, never repair."""


SOURCE_NAMESPACE = "q10_index_forward_validation"
HYPOTHESIS_ID_F = "baseline_samsung_hynix_calc_f"
HYPOTHESIS_ID_G = "baseline_samsung_hynix_calc_g"

# Real, repo-relative artifact family path layout `build_q10_forward_
# validation` actually writes to (`pipeline.py:139-141`): a day-variable
# directory, never a hardcoded date.
_BASELINE_SAMSUNG_HYNIX_DIR = "baseline_samsung_hynix"
_Q10_FORWARD_VALIDATION_DIR = "q10_forward_validation"
_REACTIONS_ARTIFACT_FILENAME = "q10_actual_market_reactions.json"
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

F_HORIZON_LABELS = ("09:00", "09:03", "09:05", "09:10", "09:15")
G_HORIZON_LABELS = ("09:30", "10:00", "CLOSE")
_G_HORIZON_SET_BY_STATE = {
    "VERIFIED": "collector_verified",
    "INVALID": "collector_invalid",
    "ABSENT": "collector_absent_legacy_fallback",
}


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _finite_positive(value: Any, *, field: str) -> float:
    number = _number(value)
    if number is None or not math.isfinite(number):
        raise Q10IndexAdapterError(f"{field}={value!r} is not a finite real number")
    if number <= 0:
        raise Q10IndexAdapterError(f"{field}={number!r} must be strictly positive")
    return number


def _verify_q10_forward_validation_day_dir(path: Path) -> Path:
    """Verify the real, repo-relative directory family layout
    (`.../baseline_samsung_hynix/<day>/q10_forward_validation`) -- the
    `<day>` segment is validated by ISO-date SHAPE, never compared
    against a hardcoded literal date."""

    resolved = Path(path)
    parts = resolved.as_posix().rstrip("/").split("/")
    if (
        len(parts) < 3
        or parts[-1] != _Q10_FORWARD_VALIDATION_DIR
        or parts[-3] != _BASELINE_SAMSUNG_HYNIX_DIR
        or not _DAY_PATTERN.match(parts[-2])
    ):
        raise Q10IndexAdapterError(
            f"_verify_q10_forward_validation_day_dir: path={str(resolved)!r} is not located under the real "
            f"q10_forward_validation artifact family layout "
            f"(.../{_BASELINE_SAMSUNG_HYNIX_DIR}/<YYYY-MM-DD>/{_Q10_FORWARD_VALIDATION_DIR}) -- refusing to treat "
            "an arbitrarily-located directory as this source family's artifact"
        )
    return resolved


def _read_verified_json(day_dir: Path, filename: str) -> Mapping[str, Any]:
    """Read one file under a verified `q10_forward_validation` day
    directory and require BOTH real persisted discriminators
    (`schema_version` AND `evaluation_program_id`, both imported
    verbatim from `forward_validation/contracts.py` -- never a
    caller-supplied or retyped literal) before returning its payload."""

    _verify_q10_forward_validation_day_dir(day_dir)
    path = Path(day_dir) / filename
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Q10IndexAdapterError(f"_read_verified_json: could not read {str(path)!r}: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise Q10IndexAdapterError(f"_read_verified_json: {str(path)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise Q10IndexAdapterError(f"_read_verified_json: {str(path)!r} does not contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    program_id = str(payload.get("evaluation_program_id") or "")
    if schema_version != SCHEMA_VERSION or program_id != PROGRAM_ID:
        raise Q10IndexAdapterError(
            f"_read_verified_json: {str(path)!r} has schema_version={schema_version!r} "
            f"evaluation_program_id={program_id!r} -- does not match the real Q10 Index forward-validation "
            f"artifact's own persisted discriminators ({SCHEMA_VERSION!r}, {PROGRAM_ID!r})"
        )
    return payload


@dataclass(frozen=True)
class Q10IndexReactionTarget:
    """One real `_stock_reaction`/`_index_reaction` result row, parsed
    from the trusted `q10_actual_market_reactions.json` artifact."""

    day: str
    key: str
    symbol: str
    kind: str
    points: Mapping[str, Any]
    path: tuple[Mapping[str, Any], ...]


def _parse_reaction_target(*, day: str, key: str, row: Mapping[str, Any]) -> Q10IndexReactionTarget:
    target = row.get("target")
    if not isinstance(target, Mapping):
        raise Q10IndexAdapterError(f"_parse_reaction_target: key={key!r} has no target descriptor")
    symbol = str(target.get("symbol") or "").strip()
    if not symbol:
        raise Q10IndexAdapterError(f"_parse_reaction_target: key={key!r} has no target.symbol")
    kind = str(target.get("kind") or "").strip()
    if kind not in ("stock", "index"):
        raise Q10IndexAdapterError(f"_parse_reaction_target: key={key!r} has unknown target.kind={kind!r} -- Calc F/G only recognize 'stock'/'index'")
    points = row.get("points")
    if not isinstance(points, Mapping):
        raise Q10IndexAdapterError(f"_parse_reaction_target: key={key!r} has no points")
    path = row.get("path")
    if not isinstance(path, list):
        raise Q10IndexAdapterError(f"_parse_reaction_target: key={key!r} has no path (candle series)")
    return Q10IndexReactionTarget(day=day, key=key, symbol=symbol, kind=kind, points=points, path=tuple(p for p in path if isinstance(p, Mapping)))


def _candles_to_observations(rows: Sequence[Mapping[str, Any]]) -> list[CanonicalObservation]:
    """Q10 Index's own local OHLCV-dict -> `CanonicalObservation`
    translation -- a deliberate local copy of the same generic pattern
    every other family in this package declares independently (each
    family owns its own translation; no cross-family import). Same
    fail-fast rules established across this whole project: `ts<=0`
    rejected outright; NaN/inf/negative price rejected; `close` must be
    finite-positive if present."""

    observations: list[CanonicalObservation] = []
    for row in rows:
        ts = int(row.get("ts") or 0)
        if ts <= 0:
            raise Q10IndexAdapterError(f"_candles_to_observations: candle has invalid timestamp ts={ts!r} -- never silently dropped")
        fields: dict[PriceCandidate, float] = {}
        for key, candidate in (("open", PriceCandidate.BAR_OPEN), ("high", PriceCandidate.BAR_HIGH), ("low", PriceCandidate.BAR_LOW), ("close", PriceCandidate.BAR_CLOSE)):
            value = row.get(key)
            if value is None:
                continue
            number = _number(value)
            if number is None or not math.isfinite(number):
                raise Q10IndexAdapterError(f"_candles_to_observations: {key}={value!r} is not a finite real number")
            if number < 0 or (key == "close" and number == 0):
                raise Q10IndexAdapterError(f"_candles_to_observations: {key}={number!r} is not a legitimate price")
            fields[candidate] = number
        volume_value = row.get("volume")
        volume = None
        if volume_value is not None:
            volume = _number(volume_value)
            if volume is None or not math.isfinite(volume) or volume < 0:
                raise Q10IndexAdapterError(f"_candles_to_observations: volume={volume_value!r} is not a legitimate value")
        observations.append(CanonicalObservation(timestamp=ts, fields=fields, volume=volume))
    return observations


def _resolve_open_reference(target: Q10IndexReactionTarget) -> tuple[int, float] | None:
    """Preserve the real, ALREADY-RESOLVED 09:00 reference verbatim
    (`points["09:00"]`) -- this module never re-derives the opening-
    detection algorithm (`_opening_point`'s own first-positive-volume-
    candle scan) itself, per this task's Section 17: if source already
    resolved the reference, preserve it, never recompute a different one
    from raw candles."""

    opening = target.points.get("09:00")
    if not isinstance(opening, Mapping) or opening.get("status") != "OBSERVED":
        return None
    price = _number(opening.get("price"))
    ts = int(opening.get("ts") or 0)
    if price is None or price <= 0 or ts <= 0:
        return None
    return ts, price


def _build_calc_f_episode(target: Q10IndexReactionTarget) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Calc F stock-reaction
    sample. Delegates 100% to the frozen, generic `forward_measurement_
    adapter` layer with the frozen UEF-2A `build_q10_index_calc_f_
    profile()` -- no new adapter family, no duplicated identity/
    checkpoint/aggregation logic."""

    if target.kind != "stock":
        raise Q10IndexAdapterError(f"_build_calc_f_episode: key={target.key!r} kind={target.kind!r} is not 'stock' -- Calc F only covers stock targets")
    resolved = _resolve_open_reference(target)
    if resolved is None:
        raise Q10IndexAdapterError(
            f"_build_calc_f_episode: symbol={target.symbol!r} day={target.day!r} has no OBSERVED 09:00 reference -- "
            "caller must treat this target as a MISSING population member instead of building an episode for it"
        )
    reference_ts, reference_price = resolved
    resolved_reference = ResolvedReference.single(origin=EventOrigin.FIXED_CLOCK, timestamp=reference_ts, price=reference_price)
    observations = _candles_to_observations(target.path)
    event_ref = build_forward_measurement_event_ref(source_namespace=SOURCE_NAMESPACE, trading_date=target.day, symbol=target.symbol)
    return build_forward_measurement_episode(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID_F,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date=target.day,
        symbol=target.symbol,
        horizon_origin=EventOrigin.FIXED_CLOCK,
        event_ref=event_ref,
        resolved_reference=resolved_reference,
        observations=observations,
        profiles=((HYPOTHESIS_ID_F, build_q10_index_calc_f_profile()),),
        provenance=Provenance(
            legacy_program=HYPOTHESIS_ID_F,
            legacy_schema=SCHEMA_VERSION,
            source_artifact=f"{_BASELINE_SAMSUNG_HYNIX_DIR}/{target.day}/{_Q10_FORWARD_VALIDATION_DIR}/{_REACTIONS_ARTIFACT_FILENAME}",
            source_function="_stock_reaction",
        ),
        metadata={"key": target.key, "kind": target.kind},
    )


def _g_checkpoint_state(point: Mapping[str, Any]) -> str:
    """Classify one real, already-resolved `points[label]` entry into the
    real tri-state `_collector_raw_row` already produced
    (`reaction_reader.py:340-417`) -- verbatim classification, never a
    re-derivation of the collector-governance algorithm itself."""

    if point.get("status") == "OBSERVED":
        return "VERIFIED" if "source" in point else "ABSENT"
    if point.get("integrity_failure"):
        return "INVALID"
    return "ABSENT"


def _build_calc_g_episode(target: Q10IndexReactionTarget) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Calc G index-reaction
    sample -- see module docstring for why this bypasses `evaluate_
    forward()` for its own 3 governed checkpoints (SOURCE-PROVIDED,
    verbatim from the trusted artifact's own already-resolved `points`)."""

    if target.kind != "index":
        raise Q10IndexAdapterError(f"_build_calc_g_episode: key={target.key!r} kind={target.kind!r} is not 'index' -- Calc G only covers index targets")
    resolved = _resolve_open_reference(target)
    if resolved is None:
        raise Q10IndexAdapterError(
            f"_build_calc_g_episode: symbol={target.symbol!r} day={target.day!r} has no OBSERVED 09:00 reference -- "
            "caller must treat this target as a MISSING population member instead of building an episode for it"
        )
    _reference_ts, reference_price = resolved
    g_policy = build_q10_index_calc_g_profile()
    checkpoints: list[Checkpoint] = []
    for label in G_HORIZON_LABELS:
        point = target.points.get(label)
        if not isinstance(point, Mapping):
            raise Q10IndexAdapterError(f"_build_calc_g_episode: symbol={target.symbol!r} has no points[{label!r}] -- unknown horizon")
        state = _g_checkpoint_state(point)
        horizon_set_id = _G_HORIZON_SET_BY_STATE[state]
        target_timestamp = _checkpoint_epoch(target.day, label)
        if point.get("status") == "OBSERVED":
            observed_price = _finite_positive(point.get("price"), field=f"points[{label!r}].price")
            observed_ts = int(point.get("ts") or 0)
            if observed_ts <= 0:
                raise Q10IndexAdapterError(f"_build_calc_g_episode: points[{label!r}] is OBSERVED but ts={point.get('ts')!r} is invalid")
            checkpoints.append(Checkpoint(
                horizon_label=label, horizon_origin=EventOrigin.FIXED_CLOCK, target_timestamp=target_timestamp,
                observed_timestamp=observed_ts, observed_price=observed_price,
                gross_return=calculate_gross_return(reference_price=reference_price, observed_price=observed_price, policy=g_policy.gross_return),
                net_return=None, mfe=None, mae=None, completeness=CheckpointCompleteness.OBSERVED,
                source=horizon_set_id, return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=horizon_set_id,
            ))
        else:
            completeness = CheckpointCompleteness.PARTIAL if state == "INVALID" else CheckpointCompleteness.MISSING
            checkpoints.append(Checkpoint(
                horizon_label=label, horizon_origin=EventOrigin.FIXED_CLOCK, target_timestamp=target_timestamp,
                observed_timestamp=None, observed_price=None, gross_return=None, net_return=None, mfe=None, mae=None,
                completeness=completeness, source=horizon_set_id, return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=horizon_set_id,
            ))
    event_ref = build_forward_measurement_event_ref(source_namespace=SOURCE_NAMESPACE, trading_date=target.day, symbol=target.symbol)
    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID_G,
        observation_type=ObservationType.DAY_SYMBOL,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        trading_date=target.day,
        symbol=target.symbol,
        event_ref=event_ref,
        checkpoints=tuple(checkpoints),
        provenance=Provenance(
            legacy_program=HYPOTHESIS_ID_G,
            legacy_schema=SCHEMA_VERSION,
            source_artifact=f"{_BASELINE_SAMSUNG_HYNIX_DIR}/{target.day}/{_Q10_FORWARD_VALIDATION_DIR}/{_REACTIONS_ARTIFACT_FILENAME}",
            source_function="_index_reaction",
        ),
        metadata={"key": target.key, "kind": target.kind},
    )


@dataclass(frozen=True)
class Q10IndexReactionCanonicalResult:
    """Adapter-local (NOT canonical) per-target result of the approved
    Calc F/G ingestion path. `episode` is `None` only when the 09:00
    reference never resolved (a MISSING population member -- `member.
    state` reflects this)."""

    target: Q10IndexReactionTarget
    member: CanonicalAggregationMember
    episode: EpisodeRecord | None


def _resolve_member_and_episode(
    target: Q10IndexReactionTarget, *, build_episode, horizon_label: str, cost_policy: CostPolicy,
) -> tuple[CanonicalAggregationMember, EpisodeRecord | None]:
    if _resolve_open_reference(target) is None:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING), None
    episode = build_episode(target)
    checkpoint = next((cp for cp in episode.checkpoints if cp.horizon_label == horizon_label), None)
    if checkpoint is None:
        raise Q10IndexAdapterError(f"_resolve_member_and_episode: no checkpoint for horizon_label={horizon_label!r}")
    member = checkpoint_to_aggregation_member(checkpoint, evaluation_record_id=episode.identity.evaluation_record_id, cost_policy=cost_policy)
    return member, episode


def canonicalize_q10_index_calc_f_artifact(
    day_dir: str | Path, *, horizon_label: str, cost_policy: CostPolicy,
) -> list[Q10IndexReactionCanonicalResult]:
    """The ONE approved, public Calc F ingestion entrypoint: reads the
    trusted `q10_actual_market_reactions.json` artifact (real family path
    + BOTH real persisted discriminators verified first), then
    canonicalizes every STOCK-kind target -- index-kind targets are
    simply outside Calc F's own population definition (not excluded,
    not missing -- a different calc's own population, per this task's
    Section 23)."""

    payload = _read_verified_json(Path(day_dir), _REACTIONS_ARTIFACT_FILENAME)
    day = str(payload.get("day") or "")
    targets = payload.get("targets")
    if not isinstance(targets, Mapping):
        raise Q10IndexAdapterError("canonicalize_q10_index_calc_f_artifact: artifact.targets must be an object")
    results: list[Q10IndexReactionCanonicalResult] = []
    for key, row in targets.items():
        if not isinstance(row, Mapping):
            continue
        target = _parse_reaction_target(day=day, key=str(key), row=row)
        if target.kind != "stock":
            continue
        member, episode = _resolve_member_and_episode(target, build_episode=_build_calc_f_episode, horizon_label=horizon_label, cost_policy=cost_policy)
        results.append(Q10IndexReactionCanonicalResult(target=target, member=member, episode=episode))
    return results


def canonicalize_q10_index_calc_g_artifact(
    day_dir: str | Path, *, horizon_label: str, cost_policy: CostPolicy,
) -> list[Q10IndexReactionCanonicalResult]:
    """The ONE approved, public Calc G ingestion entrypoint -- same
    trusted artifact as Calc F, canonicalizes every INDEX-kind target
    only."""

    payload = _read_verified_json(Path(day_dir), _REACTIONS_ARTIFACT_FILENAME)
    day = str(payload.get("day") or "")
    targets = payload.get("targets")
    if not isinstance(targets, Mapping):
        raise Q10IndexAdapterError("canonicalize_q10_index_calc_g_artifact: artifact.targets must be an object")
    results: list[Q10IndexReactionCanonicalResult] = []
    for key, row in targets.items():
        if not isinstance(row, Mapping):
            continue
        target = _parse_reaction_target(day=day, key=str(key), row=row)
        if target.kind != "index":
            continue
        member, episode = _resolve_member_and_episode(target, build_episode=_build_calc_g_episode, horizon_label=horizon_label, cost_policy=cost_policy)
        results.append(Q10IndexReactionCanonicalResult(target=target, member=member, episode=episode))
    return results


__all__ = [
    "Q10IndexAdapterError",
    "SOURCE_NAMESPACE",
    "HYPOTHESIS_ID_F",
    "HYPOTHESIS_ID_G",
    "F_HORIZON_LABELS",
    "G_HORIZON_LABELS",
    "Q10IndexReactionTarget",
    "Q10IndexReactionCanonicalResult",
    "canonicalize_q10_index_calc_f_artifact",
    "canonicalize_q10_index_calc_g_artifact",
]
