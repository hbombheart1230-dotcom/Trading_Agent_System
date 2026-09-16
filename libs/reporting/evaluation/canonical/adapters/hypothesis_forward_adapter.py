"""UEF-4B-2 -- Q12 Calc2 canonical adapter: `hypothesis_forward_adapter`.

Source authority (verified directly against real source, not only
`docs/research/uef4_legacy_family_inventory.md`):
`libs/reporting/baseline_btc_woori_tech/hypothesis_forward.py::
entry_forward_outcomes` -- for one (trading_date, entry_method) local
entry point (`entry_epoch`/`entry_price`, one of the fixed
`HYPOTHESIS_ENTRY_METHODS`: `"09:00"`/`"09:03"`/`"09:05"`/`"09:10"`/
`"PULLBACK"`, computed by `hypothesis_features.py::build_hypothesis_features`),
this function checkpoints +5/15/30/60m + EOD forward returns and returns
BOTH `gross_return_pct` AND `net_return_pct = gross - drag_pct` in the
SAME result dict (`hypothesis_forward.py:73-78`) -- confirmed
`NET_OR_COST_INCLUDED` by the frozen UEF-2A profile
(`build_q12_calc2_hypothesis_forward_profile`, `cost_note` cites the same
two lines).

TWO PROVENANCE LAYERS (Section 8 of this task): the BTC-side hypothesis
trigger (`btc_0855` -- a FIXED-CLOCK 08:55 KST snapshot,
`hypothesis_features.py::_btc_0855`, recomputed deterministically from
`(signal_payload, trading_date)`, never an independently-stored event
with its own id) and the local equity's own entry point
(`entry_epoch`/`entry_price`, symbol `041190`). Neither is collapsed into
a single generic "market event" -- both are preserved as explicit
metadata alongside the canonical identity built from the local entry
point (`q12_baseline_btc_woori.build_entry_method_event_ref`).

NET_OR_COST_INCLUDED HANDLING: gross_return/observed_timestamp/target_timestamp/
mfe/mae/missing_status are delegated to the frozen, generic UEF-2B
`evaluate_forward()` (fed real minute candles + the resolved local entry
reference) -- exactly the "no Q12-specific continuity/forward algorithm"
requirement. `net_return_pct` is the ONE figure UEF-2B structurally
cannot produce (it is outside UEF-2B's scope: "no commission/fee/tax/
slippage/net" -- `forward/engine.py`'s own module docstring) --  it is
read verbatim from the legacy source's own already-computed value and
carried through as `SOURCE_PROVIDED`, never recomputed, never paired
with an explicit `CostPolicy` (`gross_return` is excluded from the
`CanonicalAggregationMember` for this reason -- the frozen
`aggregation.py` contract itself forbids carrying both).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import (
    CheckpointCompleteness,
    EventOrigin,
    ExecutionMode,
    ObservationType,
    ReturnUnit,
)
from libs.reporting.evaluation.canonical.identity import (
    evaluation_record_id as _build_evaluation_record_id,
    evaluation_subject_id as _build_evaluation_subject_id,
)
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, Provenance, build_episode_record
from libs.reporting.evaluation.canonical.forward import MissingObservationStatus, SourceResultCostSemantics
from libs.reporting.evaluation.canonical.forward.engine import ResolvedReference, evaluate_forward
from libs.reporting.evaluation.canonical.forward.profiles import build_q12_calc2_hypothesis_forward_profile
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState

from .q12_baseline_btc_woori import (
    Q12AdapterError,
    SOURCE_NAMESPACE,
    TARGET_SYMBOL,
    build_entry_method_event_ref,
    candles_to_observations,
)


HYPOTHESIS_ID = "q12_btc_woori_five_variable_validation.v1"  # real contracts.py::HYPOTHESIS_CONTRACT_ID
HYPOTHESIS_HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")  # real contracts.py::HYPOTHESIS_HORIZONS
ENTRY_METHODS = ("09:00", "09:03", "09:05", "09:10", "PULLBACK")  # real contracts.py::HYPOTHESIS_ENTRY_METHODS


def _legacy_number(value: Any) -> float | None:
    """Byte-for-byte copy of `hypothesis_forward.py::_number` -- the exact
    conversion the legacy fallback (below) itself uses, including its
    `(None, "")` short-circuit (NOT the same as a generic float() cast)."""

    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply_legacy_high_low_fallback(rows: Sequence[Mapping[str, Any]], *, entry_price: float) -> list[dict[str, Any]]:
    """FIX1 (Fix A): reproduce `entry_forward_outcomes`'s own excursion
    high/low fallback EXACTLY (`hypothesis_forward.py:70-71`):

        high = max(_number(row.get("high") or row.get("close")) or entry_price for row in window)
        low  = min(_number(row.get("low")  or row.get("close"))  or entry_price for row in window)

    -- i.e. per row: `high` if truthy, else `close` if truthy, else
    `entry_price` (Python `or`-chain semantics: `None`/`0`/`0.0` are the
    ONLY values that trigger the fallback -- this is deliberately NOT a
    finite/positive check, it is the PROVEN legacy sentinel rule, applied
    once, before the shared parser's own separate finite/positive
    validation runs on whatever this function produces). `close` and
    `open` are left completely untouched -- the legacy source never
    applies this fallback to the checkpoint price itself, only to the
    excursion (MFE/MAE) scan's own high/low reads.

    This is Calc2-specific legacy normalization living entirely in Calc2's
    own adapter module (Section 17 of this task) -- the shared
    `candles_to_observations` parser gains no `if calc2 ...` branch.
    """

    out: list[dict[str, Any]] = []
    for row in rows:
        raw_high = row.get("high") or row.get("close")
        high_number = _legacy_number(raw_high)
        effective_high = high_number if high_number else entry_price

        raw_low = row.get("low") or row.get("close")
        low_number = _legacy_number(raw_low)
        effective_low = low_number if low_number else entry_price

        out.append({**row, "high": effective_high, "low": effective_low})
    return out


def _missing_completeness(status: MissingObservationStatus | None) -> CheckpointCompleteness:
    """Local copy of the same generic mapping `forward_measurement_adapter.py`
    declares -- that function is private (`_missing_status_to_completeness`)
    and not part of the frozen module's public API, so this is a
    Q12-specific re-declaration (option B), not a reach into frozen
    UEF-4B-1 internals."""

    if status is None:
        raise Q12AdapterError("_missing_completeness: called with status=None")
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
        raise Q12AdapterError(f"_missing_completeness: no mapping declared for {status!r}")
    return mapped


@dataclass(frozen=True)
class Q12Calc2EntryMethod:
    """One (trading_date, entry_method) hypothesis-forward sample, parsed
    from the real `entry_forward_outcomes()` output shape (one entry of
    the `outcomes` dict) plus its `btc_0855` day-level signal snapshot."""

    trading_date: str
    entry_method: str
    status: str  # "OBSERVED" / "MISSING" (entry itself, not a horizon)
    reason: str
    entry_epoch: int | None
    entry_price: float | None
    returns_by_horizon: Mapping[str, Mapping[str, Any]]
    btc_0855: Mapping[str, Any]


def parse_calc2_entry_method(
    *,
    trading_date: str,
    entry_method: str,
    outcome: Mapping[str, Any],
    btc_0855: Mapping[str, Any],
) -> Q12Calc2EntryMethod:
    """Parse one real `outcomes[method]` entry (`entry_forward_outcomes()`'s
    own output shape). Fail-fast on missing/invalid load-bearing fields."""

    if entry_method not in ENTRY_METHODS:
        raise Q12AdapterError(f"parse_calc2_entry_method: unknown entry_method={entry_method!r}")
    status = str(outcome.get("status") or "").strip()
    if status not in ("OBSERVED", "MISSING"):
        raise Q12AdapterError(f"parse_calc2_entry_method: outcome.status={status!r} is not OBSERVED/MISSING")
    entry_epoch = outcome.get("entry_epoch") if status == "OBSERVED" else None
    entry_price = outcome.get("entry_price") if status == "OBSERVED" else None
    if status == "OBSERVED" and (entry_epoch is None or int(entry_epoch) <= 0 or entry_price is None or float(entry_price) <= 0):
        raise Q12AdapterError(
            f"parse_calc2_entry_method: entry_method={entry_method!r} declares status=OBSERVED but "
            "entry_epoch/entry_price is missing/invalid -- contradictory source fields"
        )
    returns = outcome.get("returns") if status == "OBSERVED" else {}
    returns = returns if isinstance(returns, Mapping) else {}
    return Q12Calc2EntryMethod(
        trading_date=trading_date,
        entry_method=entry_method,
        status=status,
        reason=str(outcome.get("reason") or ""),
        entry_epoch=int(entry_epoch) if entry_epoch is not None else None,
        entry_price=float(entry_price) if entry_price is not None else None,
        returns_by_horizon=dict(returns),
        btc_0855=dict(btc_0855 or {}),
    )


def build_calc2_episode(sample: Q12Calc2EntryMethod, minute_rows: Sequence[Mapping[str, Any]]) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Calc2 (trading_date,
    entry_method) sample.

    `entry_condition_failed`/`entry_observation_missing` (Section 12/13 of
    this task): when the ENTRY ITSELF never resolved (`sample.status ==
    "MISSING"`), no reference exists at all and this function rejects the
    call outright -- the caller must represent the whole sample as a
    MISSING population member, never build a zero-return episode for it
    (mirrors Q10 Semiconductor's `available=False` handling exactly).
    """

    if sample.status != "OBSERVED" or sample.entry_epoch is None or sample.entry_price is None:
        raise Q12AdapterError(
            f"build_calc2_episode: entry_method={sample.entry_method!r} on {sample.trading_date!r} has no "
            f"resolved entry (status={sample.status!r}, reason={sample.reason!r}) -- caller must treat this "
            "as a MISSING population member instead of building an episode for it"
        )
    fallback_rows = _apply_legacy_high_low_fallback(minute_rows, entry_price=sample.entry_price)
    observations = candles_to_observations(fallback_rows)
    resolved_reference = ResolvedReference.single(
        origin=EventOrigin.CANDIDATE, timestamp=sample.entry_epoch, price=sample.entry_price,
    )
    event_ref = build_entry_method_event_ref(trading_date=sample.trading_date, entry_method=sample.entry_method)
    policy = build_q12_calc2_hypothesis_forward_profile()
    result = evaluate_forward(event_ref=event_ref, policy=policy, resolved_reference=resolved_reference, observations=observations)

    checkpoints: list[Checkpoint] = []
    for horizon in result.horizons:
        source_row = sample.returns_by_horizon.get(horizon.label)
        source_row = source_row if isinstance(source_row, Mapping) else {}
        source_status = str(source_row.get("status") or "")
        if horizon.missing_status is None:
            completeness = CheckpointCompleteness.OBSERVED
            source_net_return = source_row.get("net_return_pct")
            if source_status != "OBSERVED" or source_net_return is None:
                raise Q12AdapterError(
                    f"build_calc2_episode: horizon {horizon.label!r} resolved via the frozen forward engine "
                    f"(OBSERVED) but the legacy source's own returns[{horizon.label!r}] is status="
                    f"{source_status!r}/net_return_pct={source_net_return!r} -- contradictory source fields, "
                    "never silently reconciled"
                )
            net_return = float(source_net_return)
        else:
            completeness = _missing_completeness(horizon.missing_status)
            net_return = None
        checkpoints.append(
            Checkpoint(
                horizon_label=horizon.label,
                horizon_origin=EventOrigin.CANDIDATE,
                target_timestamp=horizon.target_timestamp,
                observed_timestamp=horizon.observed_timestamp,
                observed_price=horizon.observed_price,
                gross_return=horizon.gross_return,
                net_return=net_return,
                mfe=horizon.mfe.move if horizon.mfe is not None else None,
                mae=horizon.mae.move if horizon.mae is not None else None,
                completeness=completeness,
                source="baseline_btc_woori_tech_hypothesis_forward",
                return_unit=ReturnUnit.PERCENTAGE_POINTS,
                horizon_set_id="baseline_btc_woori_tech_hypothesis_forward",
            )
        )

    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=HYPOTHESIS_ID,
        observation_type=ObservationType.CANDIDATE,
        execution_mode=ExecutionMode.SHADOW,
        trading_date=sample.trading_date,
        symbol=TARGET_SYMBOL,
        event_ref=event_ref,
        checkpoints=tuple(checkpoints),
        provenance=Provenance(
            legacy_program="baseline_btc_woori_tech_hypothesis_forward",
            legacy_schema="q12_btc_woori_hypothesis_daily.v1",
            source_artifact="reports/evaluation/baseline_btc_woori_tech/<day>/q12_btc_woori_hypothesis_validation.json",
            source_function="entry_forward_outcomes",
        ),
        metadata={
            "entry_method": sample.entry_method,
            "entry_epoch": sample.entry_epoch,
            "entry_price": sample.entry_price,
            "btc_0855": sample.btc_0855,
        },
    )


def checkpoint_to_net_or_cost_included_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
    state_override: SampleMemberState | None = None,
) -> CanonicalAggregationMember:
    """The `NET_OR_COST_INCLUDED` counterpart of
    `forward_measurement_adapter.checkpoint_to_aggregation_member`
    (that helper hardcodes GROSS_ONLY -- Q10 Semiconductor's own only
    cost shape -- so it cannot serve Calc2/Calc3 as-is; per this task's
    Calc1-reuse decision tree this is option B, Q12-specific translation,
    not a frozen-4B1 defect). Never computes a net return itself --
    `checkpoint.net_return` was already translated, verbatim, from the
    legacy source at episode-construction time.
    """

    if state_override is SampleMemberState.EXCLUDED:
        return CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)
    if checkpoint is None or checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    if checkpoint.net_return is None or checkpoint.observed_timestamp is None:
        raise Q12AdapterError(
            f"checkpoint_to_net_or_cost_included_member: checkpoint {checkpoint.horizon_label!r} is OBSERVED "
            "but missing net_return/observed_timestamp -- canonical-record consistency defect, never silently "
            "treated as MISSING"
        )
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED,
        evaluation_record_id=evaluation_record_id,
        gross_return=None,  # NET_OR_COST_INCLUDED must not also carry gross_return for recomputation
        return_unit=checkpoint.return_unit,
        source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_policy=None,
        source_net_return=checkpoint.net_return,
        observed_timestamp=checkpoint.observed_timestamp,
        target_timestamp=checkpoint.target_timestamp,
    )


__all__ = [
    "HYPOTHESIS_ID",
    "HYPOTHESIS_HORIZONS",
    "ENTRY_METHODS",
    "Q12Calc2EntryMethod",
    "parse_calc2_entry_method",
    "build_calc2_episode",
    "checkpoint_to_net_or_cost_included_member",
]
