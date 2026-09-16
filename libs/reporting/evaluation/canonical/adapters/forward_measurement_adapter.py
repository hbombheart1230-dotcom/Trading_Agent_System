"""UEF-4 -- `forward_measurement_adapter` semantic family (generic layer).

Reusable glue for the "one candidate/decision, forward-measured against
one or more frozen `ForwardPolicy` profiles, GROSS_ONLY cost semantics"
adapter family (UEF-4A inventory, Table B: Q9, Q10 Semiconductor, Q10
Index Calc F/G, Opening Shadow 1A -- and, per UEF-4A Table A row 6, Q12
Calc1 once implemented, since it reuses the exact same engine as Q10
Semiconductor).

This module knows NOTHING about any specific Q program's legacy artifact
schema (no "q10"/"q9"/decision json shape anywhere below) -- it only
knows the frozen UEF-1 identity contract, the frozen UEF-2A/2B forward
contract, and the frozen UEF-3A/3C metric/aggregation contract, and wires
already-resolved inputs through them. Legacy-schema-specific parsing
(reading a real `decisions.json`/`forward_returns.json` row, deciding
which legacy field means what) belongs in a program-specific module such
as `q10_semiconductor.py`, which calls into this one.

No function here computes gross/net return, cost, profit factor, or
drawdown -- every one of those is delegated to the frozen
`forward.engine.evaluate_forward` (UEF-2B) or to
`metrics.aggregation.aggregate_canonical_samples` (UEF-3B/3C). This
module only translates and assembles already-canonical inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import (
    CheckpointCompleteness,
    CheckpointMetricKind,
    EventOrigin,
    ExecutionMode,
    ObservationType,
    ReturnUnit,
)
from libs.reporting.evaluation.canonical.identity import (
    DerivedIdentityPart,
    EventRef,
    build_derived_event_ref,
    build_event_ref,
)
from libs.reporting.evaluation.canonical.record import (
    Checkpoint,
    EpisodeRecord,
    Provenance,
    build_episode_record,
)
from libs.reporting.evaluation.canonical.forward import (
    ForwardPolicy,
    MissingObservationStatus,
    PriceCandidate,
)
from libs.reporting.evaluation.canonical.forward.engine import (
    CanonicalObservation,
    ResolvedReference,
    evaluate_forward,
)
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    SampleMemberState,
)
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics


class ForwardMeasurementAdapterError(ValueError):
    """Raised for adapter-input problems (never a frozen-core defect) -- fail fast, never repair."""


# One deterministic, documented mapping from UEF-2B's own
# `MissingObservationStatus` (the RESULT of applying a `MissingResolutionPolicy`)
# to UEF-1's own `CheckpointCompleteness` vocabulary. Neither frozen module
# defines this mapping itself (episode-building from a forward-engine result
# is explicitly UEF-4's job -- see `record.py`'s module docstring), so it is
# declared once, here, generically -- never per-Q, never inline at a call site.
_MISSING_STATUS_TO_COMPLETENESS: Mapping[MissingObservationStatus, CheckpointCompleteness] = {
    MissingObservationStatus.TARGET_NOT_REACHED: CheckpointCompleteness.PENDING,
    MissingObservationStatus.NO_DATA: CheckpointCompleteness.MISSING,
    MissingObservationStatus.NO_OBSERVATION_WITHIN_TOLERANCE: CheckpointCompleteness.STALE,
    MissingObservationStatus.SESSION_ENDED: CheckpointCompleteness.MISSING,
    MissingObservationStatus.EVIDENCE_INVALID: CheckpointCompleteness.MISSING,
    MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS: CheckpointCompleteness.MISSING,
}


def build_forward_measurement_event_ref(
    *,
    source_namespace: str,
    trading_date: str,
    symbol: str,
    native_id: Any = None,
    extra_fields: Mapping[str, DerivedIdentityPart] | None = None,
) -> EventRef:
    """One candidate/episode's identity: prefer a source-native id, else a
    derived (trading_date, symbol, ...) composite (UEF-1 `identity.py`).

    ``native_id`` -- pass it when the source has ONE stable id for this
    exact episode (e.g. Q9's own `decision_id` IS the episode). Leave it
    ``None`` and supply ``extra_fields`` when identity requires a
    composite of the decision's own id plus this specific candidate's own
    dimension (e.g. Q10 Semiconductor: one decision produces N ranked
    candidates, so `(trading_date, symbol, decision_id)` is the composite
    identity -- `decision_id` alone is not enough because it names the
    decision, not the candidate).
    """

    if native_id is not None and str(native_id).strip():
        return build_event_ref(source_namespace=source_namespace, native_id=native_id)
    return build_derived_event_ref(
        source_namespace=source_namespace,
        trading_date=trading_date,
        symbol=symbol,
        extra_fields=dict(extra_fields or {}),
    )


def _missing_status_to_completeness(status: MissingObservationStatus | None) -> CheckpointCompleteness:
    if status is None:
        raise ForwardMeasurementAdapterError(
            "_missing_status_to_completeness: called with status=None -- caller must branch on "
            "HorizonResult.missing_status is None (OBSERVED) before calling this mapper"
        )
    mapped = _MISSING_STATUS_TO_COMPLETENESS.get(status)
    if mapped is None:
        raise ForwardMeasurementAdapterError(
            f"_missing_status_to_completeness: no mapping declared for MissingObservationStatus={status!r} -- "
            "add an explicit mapping rather than silently defaulting one in"
        )
    return mapped


def build_forward_measurement_episode(
    *,
    source_namespace: str,
    hypothesis_id: str,
    execution_mode: ExecutionMode,
    trading_date: str,
    symbol: str,
    horizon_origin: EventOrigin,
    event_ref: EventRef,
    resolved_reference: ResolvedReference,
    observations: Sequence[CanonicalObservation],
    profiles: Sequence[tuple[str, ForwardPolicy]],
    provenance: Provenance | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EpisodeRecord:
    """Run one or more frozen `ForwardPolicy` profiles against ONE shared
    (reference, observations) pair, and merge their `HorizonResult`s into
    ONE canonical `EpisodeRecord`.

    ``profiles`` -- e.g. ``[("baseline_samsung_hynix_calc_a", calc_a_policy),
    ("baseline_samsung_hynix_calc_b", calc_b_policy), (..., calc_c_policy)]``.
    Every profile is executed via the frozen, generic
    `forward.engine.evaluate_forward` (UEF-2B) -- this function adds no
    calculation of its own, only merges the results. A horizon LABEL
    appearing in more than one profile is rejected outright (fail-fast,
    per this task's "ambiguous primary sample mapping" rule) rather than
    silently letting the last-executed profile win.
    """

    checkpoints: list[Checkpoint] = []
    seen_labels: dict[str, str] = {}
    for horizon_set_id, policy in profiles:
        result = evaluate_forward(
            event_ref=event_ref,
            policy=policy,
            resolved_reference=resolved_reference,
            observations=observations,
        )
        for horizon in result.horizons:
            if horizon.label in seen_labels:
                raise ForwardMeasurementAdapterError(
                    f"build_forward_measurement_episode: horizon label {horizon.label!r} is declared by both "
                    f"{seen_labels[horizon.label]!r} and {horizon_set_id!r} -- one candidate cannot receive two "
                    "independently-computed values for the same horizon label; this is an adapter/profile-set "
                    "misconfiguration, never silently resolved by picking one"
                )
            seen_labels[horizon.label] = horizon_set_id
            if horizon.missing_status is None:
                completeness = CheckpointCompleteness.OBSERVED
            else:
                completeness = _missing_status_to_completeness(horizon.missing_status)
            checkpoints.append(
                Checkpoint(
                    horizon_label=horizon.label,
                    horizon_origin=horizon_origin,
                    target_timestamp=horizon.target_timestamp,
                    observed_timestamp=horizon.observed_timestamp,
                    observed_price=horizon.observed_price,
                    gross_return=horizon.gross_return,
                    net_return=None,
                    mfe=horizon.mfe.move if horizon.mfe is not None else None,
                    mae=horizon.mae.move if horizon.mae is not None else None,
                    completeness=completeness,
                    source=horizon_set_id,
                    return_unit=ReturnUnit.PERCENTAGE_POINTS,
                    horizon_set_id=horizon_set_id,
                    metric_kind=CheckpointMetricKind.PRICE_BASED,
                )
            )

    return build_episode_record(
        source_namespace=source_namespace,
        hypothesis_id=hypothesis_id,
        observation_type=ObservationType.CANDIDATE,
        execution_mode=execution_mode,
        trading_date=trading_date,
        symbol=symbol,
        event_ref=event_ref,
        checkpoints=tuple(checkpoints),
        provenance=provenance or Provenance(),
        metadata=dict(metadata or {}),
    )


def checkpoint_to_aggregation_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
    cost_policy: CostPolicy,
    state_override: SampleMemberState | None = None,
) -> CanonicalAggregationMember:
    """Translate one already-canonical `Checkpoint` (GROSS_ONLY family) into
    one `CanonicalAggregationMember`, ready for UEF-3C's frozen
    `aggregate_canonical_samples`.

    Never computes a net return itself -- `gross_return`/`cost_policy` are
    passed straight through; `aggregate_canonical_samples` is the sole
    caller of `calculate_net_return` (UEF-3B, frozen). ``state_override``
    lets a caller mark this member `EXCLUDED` by its own view-selection
    policy (e.g. Q10 Semiconductor's `eligible` flag) regardless of
    whether the checkpoint itself observed a value -- an EXCLUDED member
    is a policy decision, not a data-availability fact, and always wins
    over the checkpoint's own completeness.
    """

    if state_override is SampleMemberState.EXCLUDED:
        return CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)
    if checkpoint is None or checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    if checkpoint.gross_return is None or checkpoint.observed_timestamp is None:
        raise ForwardMeasurementAdapterError(
            f"checkpoint_to_aggregation_member: checkpoint {checkpoint.horizon_label!r} is OBSERVED but missing "
            "gross_return/observed_timestamp -- this is a canonical-record consistency defect, never silently "
            "treated as MISSING"
        )
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED,
        evaluation_record_id=evaluation_record_id,
        gross_return=checkpoint.gross_return,
        return_unit=checkpoint.return_unit,
        source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_policy=cost_policy,
        observed_timestamp=checkpoint.observed_timestamp,
        target_timestamp=checkpoint.target_timestamp,
    )


__all__ = [
    "ForwardMeasurementAdapterError",
    "build_forward_measurement_event_ref",
    "build_forward_measurement_episode",
    "checkpoint_to_aggregation_member",
]
