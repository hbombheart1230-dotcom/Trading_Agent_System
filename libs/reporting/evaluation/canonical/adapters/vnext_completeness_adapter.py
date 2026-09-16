"""UEF-4B-2 FIX2 -- Q12 Calc3 candidate adapter: `vnext_completeness_adapter`.

======================================================================
STATUS: BLOCKED -- NOT AN APPROVED UEF-4B ADAPTER.
LOSSLESS MAPPING = UNKNOWN.
======================================================================

This module is retained ONLY as a research/reproducer artifact. It is
NOT part of UEF-4B-2's approved canonicalization scope (Calc1/Calc2
only -- see `q12_baseline_btc_woori.py`/`hypothesis_forward_adapter.py`)
and MUST NOT be used, imported, or wired into any approved UEF-4B
orchestration path. `__all__` below deliberately exports nothing from
this module for that reason -- every name here is reachable only by an
explicit, direct import (as the reproducer tests in
`tests/test_uef4b2_q12_adapter.py` do), never via `from
vnext_completeness_adapter import *`, and never treated as public API.

WHY BLOCKED (UEF-4B-2 FIX2, narrowly reopening UEF-4A's Calc3
classification per the project's freeze-reopen policy's case #3, "proven
downstream contract contradiction" -- see
`docs/research/uef4_legacy_family_inventory.md` Section 5's Calc3 entry
for the authoritative record): the real legacy `vnext/outcomes.py::forward`
gates MFE/MAE completeness on `complete = len(window) == expected` --
ROW-COUNT only. The frozen UEF-2A/2B `CONTIGUOUS_INTERVAL` completeness
policy (`build_q12_calc3_vnext_profile`, `forward/engine.py::
validate_completeness`) requires the actual observed TIMESTAMP SET to
equal the expected grid SET exactly -- a strictly stronger rule. A prior
pass (FIX1) argued the two are equivalent over the "valid" legacy input
domain (claiming the shared candle loader,
`baseline_samsung_hynix.data_provider._normalize_rows`, structurally
guarantees exact-grid alignment). An independent audit correctly rejected
that argument: absence of an observed off-grid case in this repo's own
tests/artifacts is NOT proof that the upstream feed can never produce
one -- `_normalize_rows` filters and sorts, but nothing in its own code,
tests, or any other real artifact read for this task **positively
asserts** an exact-minute-grid contract; the "OUTCOME A" conclusion was
an absence-of-counter-evidence inference, not a proven guarantee. See
`test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`
(`tests/test_uef4b2_q12_adapter.py`) for a synthetic, row-count-complete,
off-grid candle series where the real legacy `forward()` function
computes `path_status="COMPLETE"` with real MFE/MAE values, while the
frozen `evaluate_forward()` (fed the identical data, independent of any
adapter-side gatekeeping) computes a DIFFERENT, incomplete result for the
same horizon -- a genuine, reproduced contradiction, not merely a
theoretical one.

Per the project's own "no evidence -> no active semantic" / "known +
classified + blocked is acceptable, unknown + silently forced is not"
principles: Q12 Calc3 remains real PRIMARY EVIDENCE (never demoted to
consumer/derived-view/deprecated), `ADAPTER REQUIRED CONCEPTUALLY = YES`,
but `LOSSLESS MAPPING = UNKNOWN` and `UEF-4B IMPLEMENTATION = BLOCKED`
until a future architecture decision resolves the contract question (does
UEF-2A gain an explicit row-count-completeness variant for this one
family, or is Calc3 excluded from the canonical core entirely, or is
something else decided) -- none of which this task decides.

The `_require_exact_minute_grid` defensive check below is kept as
EXPERIMENTAL adapter-local code (it still mechanically rejects an
off-grid timestamp if this module is ever called directly) but its
presence does NOT constitute proof of losslessness and must never be
cited as such again.

----------------------------------------------------------------------

Source authority (verified directly against real source):
`libs/reporting/baseline_btc_woori_tech/vnext/outcomes.py::forward` --
for the SAME (trading_date, entry_method) local entry point Calc2 reads
(`record['features']['entry_methods'][method]`,
`vnext/pipeline.py:81`), this function checkpoints 09:30/10:00 (fixed
clock, BAR_OPEN, end-EXCLUSIVE window) + EOD (15:30 fixed clock,
BAR_CLOSE, end-INCLUSIVE) and returns BOTH `gross_return_pct` AND
`net_return_pct = gross - drag_pct` (`outcomes.py:27`) --
`NET_OR_COST_INCLUDED`, confirmed by the frozen UEF-2A profile
(`build_q12_calc3_vnext_profile`).

CONTIGUOUS-MINUTE COMPLETENESS (Section 9 of this task -- the load-bearing
concern for this adapter): the real source gates MFE/MAE on
`complete = len(window) == expected` (a genuine 60-second contiguous-bar
completeness check, `outcomes.py:23-24`) -- `mfe_pct`/`mae_pct` are
`None` unless `complete`. The frozen UEF-2A profile already declares this
EXACT rule generically (`DataCompletenessPolicy(kind=CONTIGUOUS_INTERVAL,
interval_seconds=60.0, require_all_expected_observations=True)` attached
to each horizon's `ExcursionPolicy`). This adapter NEVER recomputes
`complete`/`expected`/`len(window)` itself -- it feeds real minute
candles into the frozen, generic `evaluate_forward()` (UEF-2B) and lets
`resolve_excursion()`/`validate_completeness()` decide MFE/MAE
completeness. `Q12 CONTINUITY BRANCH IN CORE = 0`;
`Q12 CONTINUITY CALCULATION IN ADAPTER = 0` (this file computes none of
its own -- only source parsing/validation, per this task's own
requirement).

DUAL-ORIGIN REFERENCE: each horizon's own `HorizonSpec.origin` is
`EventOrigin.FIXED_CLOCK` (the checkpoint TARGET is anchored to a fixed
clock time, 09:30/10:00/15:30 -- `resolve_target()` derives the
CALENDAR DATE from this origin's own timestamp, never its price), while
the policy's own `reference_resolution.origin` is `EventOrigin.CANDIDATE`
(gross/net return is always computed against the SAME entry_price for
every horizon -- matches the real source's own `gross = pct(exit_price,
price)` where `price` is always `entry_price`, never re-resolved per
horizon). Both origins are supplied on the `ResolvedReference`, sharing
the same (entry_epoch, entry_price) values -- FIXED_CLOCK's own
timestamp only needs to fall on the correct trading day.
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
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, Provenance, build_episode_record
from libs.reporting.evaluation.canonical.forward import MissingObservationStatus, SourceResultCostSemantics
from libs.reporting.evaluation.canonical.forward.engine import ResolvedOrigin, ResolvedReference, evaluate_forward
from libs.reporting.evaluation.canonical.forward.profiles import build_q12_calc3_vnext_profile
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState

from .q12_baseline_btc_woori import (
    Q12AdapterError,
    SOURCE_NAMESPACE,
    TARGET_SYMBOL,
    build_entry_method_event_ref,
    candles_to_observations,
)


HYPOTHESIS_ID = "Q12_CRYPTO_EQUITY_CONFIRM_V2_ALIGNED_SHADOW"  # real vnext/contract.py::VERSION
VNEXT_HORIZONS = ("09:30", "10:00", "EOD")  # real vnext/outcomes.py::forward's own horizon loop
ENTRY_METHODS = ("09:00", "09:03", "09:05", "09:10", "PULLBACK")

_MINUTE_GRID_SECONDS = 60


def _require_exact_minute_grid(observations: Sequence[Any]) -> None:
    """EXPERIMENTAL, NOT PROOF OF LOSSLESSNESS (UEF-4B-2 FIX2).

    A prior pass (FIX1) argued this check alone made the frozen exact-grid
    completeness rule "lossless" over Calc3's real input domain
    (`load_woori_candles` -> `_normalize_rows`, shared with Calc1/Calc2).
    An independent audit correctly rejected that reasoning: the absence of
    an observed off-grid case in this repo's own tests/artifacts is NOT a
    proof that the upstream feed can never produce one -- no code, test,
    or contract anywhere in `baseline_btc_woori_tech/**` POSITIVELY
    asserts an exact-minute-grid guarantee; FIX1's conclusion inferred a
    guarantee from absence of counter-evidence, which is not sufficient
    (see the module's own top-of-file BLOCKED banner and
    `test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`
    for the actual reproduced contradiction).

    This function is kept only as a DEFENSIVE, EXPERIMENTAL guard -- if
    this (non-approved) module is ever invoked directly, it still rejects
    an off-grid timestamp outright rather than silently feeding one into
    `evaluate_forward()`. It decides nothing about whether Calc3's
    mapping is lossless; that question remains UNKNOWN and BLOCKED.
    """

    for observation in observations:
        if observation.timestamp % _MINUTE_GRID_SECONDS != 0:
            raise Q12AdapterError(
                f"_require_exact_minute_grid: observation timestamp={observation.timestamp!r} is not aligned "
                f"to the {_MINUTE_GRID_SECONDS}-second minute grid -- an off-grid timestamp is an invalid "
                "source-contract violation for Calc3 (see OUTCOME A investigation in this module), rejected "
                "before canonical evaluation, never silently accepted or snapped to the grid"
            )


def _missing_completeness(status: MissingObservationStatus | None) -> CheckpointCompleteness:
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
class Q12Calc3EntryMethod:
    """One (trading_date, entry_method) vnext-completeness sample, parsed
    from the real `vnext/outcomes.py::forward()` output shape."""

    trading_date: str
    entry_method: str
    status: str  # "OBSERVED" / "MISSING" (entry itself)
    entry_epoch: int | None
    entry_price: float | None
    returns_by_horizon: Mapping[str, Mapping[str, Any]]


def parse_calc3_entry_method(
    *,
    trading_date: str,
    entry_method: str,
    entry: Mapping[str, Any],
    outcome_by_horizon: Mapping[str, Mapping[str, Any]],
) -> Q12Calc3EntryMethod:
    """Parse one real `entry_methods[method]` entry (the same local-entry
    shape Calc2 reads) plus its `forward()` output
    (`outcome_by_horizon`). Fail-fast on missing/invalid load-bearing
    fields."""

    if entry_method not in ENTRY_METHODS:
        raise Q12AdapterError(f"parse_calc3_entry_method: unknown entry_method={entry_method!r}")
    status = str(entry.get("status") or "").strip()
    if status not in ("OBSERVED", "MISSING"):
        raise Q12AdapterError(f"parse_calc3_entry_method: entry.status={status!r} is not OBSERVED/MISSING")
    entry_epoch = entry.get("entry_epoch") if status == "OBSERVED" else None
    entry_price = entry.get("entry_price") if status == "OBSERVED" else None
    if status == "OBSERVED" and (entry_epoch is None or int(entry_epoch) <= 0 or entry_price is None or float(entry_price) <= 0):
        raise Q12AdapterError(
            f"parse_calc3_entry_method: entry_method={entry_method!r} declares status=OBSERVED but "
            "entry_epoch/entry_price is missing/invalid -- contradictory source fields"
        )
    return Q12Calc3EntryMethod(
        trading_date=trading_date,
        entry_method=entry_method,
        status=status,
        entry_epoch=int(entry_epoch) if entry_epoch is not None else None,
        entry_price=float(entry_price) if entry_price is not None else None,
        returns_by_horizon=dict(outcome_by_horizon or {}) if status == "OBSERVED" else {},
    )


def build_calc3_episode(sample: Q12Calc3EntryMethod, minute_rows: Sequence[Mapping[str, Any]]) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Calc3 (trading_date,
    entry_method) sample. Delegates checkpoint/MFE/MAE/completeness
    entirely to the frozen `evaluate_forward()`; only `net_return` is
    translated verbatim from the legacy source (irreducibly
    SOURCE_PROVIDED, see module docstring)."""

    if sample.status != "OBSERVED" or sample.entry_epoch is None or sample.entry_price is None:
        raise Q12AdapterError(
            f"build_calc3_episode: entry_method={sample.entry_method!r} on {sample.trading_date!r} has no "
            f"resolved entry (status={sample.status!r}) -- caller must treat this as a MISSING population "
            "member instead of building an episode for it"
        )
    observations = candles_to_observations(minute_rows)
    _require_exact_minute_grid(observations)
    origin = ResolvedOrigin(timestamp=sample.entry_epoch, price=sample.entry_price)
    resolved_reference = ResolvedReference(
        primary_origin=EventOrigin.CANDIDATE,
        origins={EventOrigin.CANDIDATE: origin, EventOrigin.FIXED_CLOCK: origin},
    )
    event_ref = build_entry_method_event_ref(trading_date=sample.trading_date, entry_method=sample.entry_method)
    policy = build_q12_calc3_vnext_profile()
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
                    f"build_calc3_episode: horizon {horizon.label!r} resolved via the frozen forward engine "
                    f"(OBSERVED) but the legacy source's own outcome[{horizon.label!r}] is status="
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
                horizon_origin=EventOrigin.FIXED_CLOCK,
                target_timestamp=horizon.target_timestamp,
                observed_timestamp=horizon.observed_timestamp,
                observed_price=horizon.observed_price,
                gross_return=horizon.gross_return,
                net_return=net_return,
                mfe=horizon.mfe.move if horizon.mfe is not None else None,
                mae=horizon.mae.move if horizon.mae is not None else None,
                completeness=completeness,
                source="baseline_btc_woori_tech_vnext",
                return_unit=ReturnUnit.PERCENTAGE_POINTS,
                horizon_set_id="baseline_btc_woori_tech_vnext",
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
            legacy_program="baseline_btc_woori_tech_vnext",
            legacy_schema="",
            source_artifact="reports/evaluation/baseline_btc_woori_tech/vnext/<version>/<day>/validation.json",
            source_function="vnext.outcomes.forward",
        ),
        metadata={
            "entry_method": sample.entry_method,
            "entry_epoch": sample.entry_epoch,
            "entry_price": sample.entry_price,
        },
    )


def checkpoint_to_net_or_cost_included_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
    state_override: SampleMemberState | None = None,
) -> CanonicalAggregationMember:
    """Calc3's own copy of the same `NET_OR_COST_INCLUDED` translation
    `hypothesis_forward_adapter.py` declares for Calc2 -- deliberately
    NOT imported from that sibling module (each adapter family owns its
    own translation, matching UEF-4A Table B's 1:1 family-per-source
    mapping; the two implementations are identical only because both
    calculators happen to share the same cost shape, not because one
    reuses the other)."""

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
        gross_return=None,
        return_unit=checkpoint.return_unit,
        source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_policy=None,
        source_net_return=checkpoint.net_return,
        observed_timestamp=checkpoint.observed_timestamp,
        target_timestamp=checkpoint.target_timestamp,
    )


# UEF-4B-2 FIX2: deliberately empty. This module is BLOCKED, not an
# approved UEF-4B adapter (LOSSLESS MAPPING = UNKNOWN -- see the module
# docstring) -- nothing here is exported as public/approved API. Every
# name remains reachable by an explicit direct import for research/
# reproducer purposes only (e.g. the FIX2 contradiction-reproducer test),
# never via `from vnext_completeness_adapter import *`.
__all__: list[str] = []
