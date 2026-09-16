"""UEF-3B -- Canonical Cost & Metric Engine (implements UEF-3A, never reinterprets it).

UEF-3A (`contracts.py`/`policy.py`, FROZEN as of 2026-09-15 -- see
`docs/research/uef_freeze_manifest.md`) defined the canonical vocabulary
and the construction-time invariants every cost/return/metric VALUE must
satisfy, but deliberately computed nothing: no function there ever
iterates over a caller-supplied sequence of business values to reduce it
to an aggregate. That is precisely the boundary this module crosses --
UEF-3B is where the actual arithmetic lives.

Every function here:
- takes already-canonical scalar/sequence inputs (a resolved gross return,
  an already-built `CostPolicy`/`MetricPolicy`/`SamplePopulation`, a list
  of already-resolved per-observation net returns or curve points) --
  never a legacy Q/Opening-shaped dict. Legacy-shape parsing is UEF-4's
  job, not this one (item 19).
- performs its calculation, then hands the result to the matching frozen
  UEF-3A dataclass constructor (`NetReturnRecord`, `ProfitFactorRecord`,
  `DrawdownRecord`) so that dataclass's OWN `__post_init__` re-validates
  the outcome. If this engine's arithmetic ever disagreed with a UEF-3A
  invariant, construction raises immediately -- the frozen contract is
  the final arbiter, this engine can never silently produce a
  contract-violating value.
- contains zero Q-specific/Opening-specific branches (verified by AST
  scan, per the same "no program-specific semantics" rule UEF-2A/2B/3A
  already enforce) and zero legacy-adapter logic.
- is deterministic: same canonical inputs + frozen policies -> same
  output, always. No `datetime.now()`, no randomness, no filesystem, no
  environment config, no unordered-collection dependency (`calculate_max_drawdown`
  explicitly sorts its input via the UEF-3A `compare_drawdown_curve_order`
  comparator before walking it).

Reused, never duplicated or reinterpreted: `CostPolicy.total_cost` (UEF-3A,
the addition itself already lives there), `derive_population_status`/
`require_status_consistent_with_population` (UEF-3A H4), `compare_drawdown_curve_order`
(UEF-3A H3), `require_consistent_population` (UEF-3A H2), and every
dataclass's own `__post_init__` validation. This module adds ONE new,
UEF-3B-owned, deliberately minimal input shape (`DrawdownCurvePoint`) --
not a new UEF-3A contract, just the generic per-point shape the MDD
engine needs to walk a curve; it carries no Q-specific field.

Not part of the frozen UEF-3A manifest (a NEW sibling file -- adding it
does not alter the bytes of `contracts.py`/`policy.py`/`__init__.py`,
so the 9/9 freeze is untouched) and not re-exported through the frozen
`metrics/__init__.py`; import it directly:
    from libs.reporting.evaluation.canonical.metrics.engine import ...
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Sequence

from ..forward.contracts import SourceResultCostSemantics
from .contracts import (
    DrawdownArithmetic,
    DrawdownOrderingAuthority,
    DrawdownTieBreakAuthority,
    MetricComputationStatus,
    NetReturnComputationStatus,
    WinLossFlat,
)
from .policy import (
    CostPolicy,
    DrawdownRecord,
    MetricContractValidationError,
    MetricPolicy,
    MetricValue,
    NetReturnRecord,
    ProfitFactorRecord,
    SamplePopulation,
    WinLossFlatPopulation,
    compare_drawdown_curve_order,
    derive_population_status,
    require_consistent_population,
)
from ..contracts import ReturnUnit


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MetricContractValidationError(message)


# =========================================================================
# Cost Engine (item 5)
# =========================================================================


def calculate_total_cost(cost_policy: CostPolicy) -> float:
    """The canonical total explicit cost for one `CostPolicy` -- one addition, done once.

    `CostPolicy.total_cost` (UEF-3A) already performs the addition
    (`commission + tax + slippage + other_cost`); this function is the
    named UEF-3B engine ENTRY POINT for that same, single, already-correct
    computation -- it does not re-derive or duplicate it, and it never
    multiplies by anything derived from `CostTiming` (per-component
    `CostTiming`/`CostAmountBasis` are provenance/applicability metadata
    only, never a multiplier -- UEF-3A H1).
    """

    if not isinstance(cost_policy, CostPolicy):
        raise MetricContractValidationError("calculate_total_cost: cost_policy must be a CostPolicy")
    return cost_policy.total_cost


def _require_compatible_units(return_unit: ReturnUnit, cost_unit: ReturnUnit, *, context: str) -> None:
    """Reject an implicit PERCENTAGE_POINTS<->FRACTION conversion (item 6).

    The frozen UEF-1 `ReturnUnit` contract declares no conversion factor
    between its two members -- this engine never guesses one. A caller
    supplying a gross return and a `CostPolicy` in different units gets an
    explicit, immediate failure, never a silently-wrong number.
    """

    if return_unit is not cost_unit:
        raise MetricContractValidationError(
            f"{context}: return_unit={return_unit.value} does not match CostPolicy.unit={cost_unit.value} -- "
            "no implicit PERCENTAGE_POINTS<->FRACTION conversion exists in the frozen UEF-1 ReturnUnit contract; "
            "the caller must supply both values in the same unit"
        )


# =========================================================================
# Return Classification (item 9)
# =========================================================================


def classify_net_return(net_return: float) -> WinLossFlat:
    """The exact frozen WIN/LOSS/FLAT rule -- no epsilon, no rounding.

    Operates on the canonical numeric value directly (before any display
    formatting a caller might apply downstream).
    """

    if net_return > 0:
        return WinLossFlat.WIN
    if net_return < 0:
        return WinLossFlat.LOSS
    return WinLossFlat.FLAT


# =========================================================================
# Net Return Engine (item 7-8)
# =========================================================================


def calculate_net_return(
    *,
    gross_return: float | None,
    return_unit: ReturnUnit,
    source_cost_semantics: SourceResultCostSemantics,
    cost_policy: CostPolicy | None = None,
    source_net_return: float | None = None,
    classify: bool = True,
) -> NetReturnRecord:
    """Deterministically construct a canonical `NetReturnRecord` from raw ingredients.

    - `GROSS_ONLY`: applies `cost_policy` to `gross_return` exactly once
      (`net = gross - cost_policy.total_cost`) -> `COMPUTED`.
    - `NET_OR_COST_INCLUDED`: the source's own `source_net_return` is
      authoritative as-is -> `SOURCE_PROVIDED`; an explicit `cost_policy`
      here is rejected outright (double-charging is structurally
      impossible, not merely discouraged).
    - `UNKNOWN`: `UNAVAILABLE`, `net_return=None` -- no guessed value, no
      new status invented (UEF-3A's existing three-member taxonomy only).

    `win_loss_flat` is filled via `classify_net_return` (`classify=True`,
    the default) unless the caller passes `classify=False` to leave it
    unset -- either way, `NetReturnRecord.__post_init__` re-validates the
    classification against the sign it actually received.
    """

    if source_cost_semantics is SourceResultCostSemantics.GROSS_ONLY:
        _require(cost_policy is not None, "calculate_net_return: GROSS_ONLY requires an explicit cost_policy to compute a COMPUTED net return")
        _require(gross_return is not None, "calculate_net_return: GROSS_ONLY requires a known gross_return")
        _require_compatible_units(return_unit, cost_policy.unit, context="calculate_net_return")
        net_return = gross_return - calculate_total_cost(cost_policy)
        win_loss_flat = classify_net_return(net_return) if classify else None
        return NetReturnRecord(
            gross_return=gross_return, return_unit=return_unit, source_cost_semantics=source_cost_semantics,
            computation_status=NetReturnComputationStatus.COMPUTED, cost_policy=cost_policy,
            net_return=net_return, win_loss_flat=win_loss_flat,
        )
    if source_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED:
        _require(source_net_return is not None, "calculate_net_return: NET_OR_COST_INCLUDED requires the source's own net_return value (source_net_return)")
        _require(cost_policy is None, "calculate_net_return: NET_OR_COST_INCLUDED must not receive an explicit cost_policy -- reapplying a cost to an already-net/cost-included source would double-count it")
        win_loss_flat = classify_net_return(source_net_return) if classify else None
        return NetReturnRecord(
            gross_return=gross_return, return_unit=return_unit, source_cost_semantics=source_cost_semantics,
            computation_status=NetReturnComputationStatus.SOURCE_PROVIDED,
            net_return=source_net_return, win_loss_flat=win_loss_flat,
        )
    if source_cost_semantics is SourceResultCostSemantics.UNKNOWN:
        return NetReturnRecord(
            gross_return=gross_return, return_unit=return_unit, source_cost_semantics=source_cost_semantics,
            computation_status=NetReturnComputationStatus.UNAVAILABLE, net_return=None, win_loss_flat=None,
        )
    raise MetricContractValidationError(f"calculate_net_return: unhandled source_cost_semantics={source_cost_semantics!r}")


# =========================================================================
# Profit Factor Engine (item 10)
# =========================================================================


def calculate_profit_factor(
    *,
    net_returns: Sequence[float],
    sample: SamplePopulation,
    metric_policy: MetricPolicy,
) -> ProfitFactorRecord:
    """Canonical profit factor: `sum(positive net returns) / abs(sum(negative net returns))`.

    `net_returns` holds exactly the EVALUATED population's canonical net
    returns (`len(net_returns) == sample.evaluated_count`, checked). The
    win/loss/flat breakdown is derived from `net_returns` via
    `classify_net_return` (never re-typed by the caller), then
    cross-checked against `sample` with UEF-3A's own `require_consistent_population`.

    Precedence (UEF-3A H4, applied here rather than re-decided):
    1. `derive_population_status(sample, metric_policy)` -- if not `VALID`,
       that population-evidence status is used AS-IS (`EMPTY_POPULATION`/
       `MISSING_EVIDENCE`/`INSUFFICIENT_EVIDENCE`), and no profit-factor
       arithmetic runs at all.
    2. Only once population evidence says `VALID` does the profit-factor-
       specific rule apply: zero losses (whether or not there are gains)
       is mathematically undefined -> `UNDEFINED_METRIC` (never `inf`,
       never a `999`/`0` sentinel, never a string). Otherwise `VALID` with
       the exact ratio.

    `MetricValue.unit` is left `None` for a computed profit factor -- it
    is a dimensionless ratio of two same-unit sums, never itself a return
    figure in `ReturnUnit`; the frozen `MetricValue` contract permits
    (does not require) a unit, so this is a UEF-3B engine choice, not a
    reinterpretation of UEF-3A.
    """

    _require(isinstance(sample, SamplePopulation), "calculate_profit_factor: sample must be a SamplePopulation")
    _require(isinstance(metric_policy, MetricPolicy), "calculate_profit_factor: metric_policy must be a MetricPolicy")
    _require(
        len(net_returns) == sample.evaluated_count,
        f"calculate_profit_factor: len(net_returns)={len(net_returns)} does not match sample.evaluated_count={sample.evaluated_count} -- net_returns must hold exactly the evaluated population's canonical net returns, no more, no fewer",
    )

    win_count = sum(1 for value in net_returns if classify_net_return(value) is WinLossFlat.WIN)
    loss_count = sum(1 for value in net_returns if classify_net_return(value) is WinLossFlat.LOSS)
    flat_count = sum(1 for value in net_returns if classify_net_return(value) is WinLossFlat.FLAT)
    breakdown = WinLossFlatPopulation(win_count=win_count, loss_count=loss_count, flat_count=flat_count)
    require_consistent_population(sample, breakdown)

    population_status = derive_population_status(sample, metric_policy)
    if population_status is not MetricComputationStatus.VALID:
        metric = MetricValue(status=population_status)
        return ProfitFactorRecord(metric=metric, population=breakdown, sample=sample, metric_policy=metric_policy)

    gross_profit = sum(value for value in net_returns if value > 0)
    gross_loss_abs = abs(sum(value for value in net_returns if value < 0))

    if gross_loss_abs == 0:
        metric = MetricValue(status=MetricComputationStatus.UNDEFINED_METRIC)
        return ProfitFactorRecord(metric=metric, population=breakdown, sample=sample, metric_policy=metric_policy)

    value = gross_profit / gross_loss_abs
    metric = MetricValue(status=MetricComputationStatus.VALID, value=value, unit=None)
    return ProfitFactorRecord(
        metric=metric, population=breakdown, sample=sample, metric_policy=metric_policy,
        gross_profit=gross_profit, gross_loss_abs=gross_loss_abs,
    )


# =========================================================================
# Maximum Drawdown Engine (item 11-13)
# =========================================================================


@dataclass(frozen=True)
class DrawdownCurvePoint:
    """One generic, UEF-3B-owned per-observation input to the MDD engine.

    NOT a UEF-3A contract type (UEF-3A's own `DrawdownRecord` only fixes
    the RESULT shape, never a per-point input shape -- that boundary is
    exactly what this engine crosses). Deliberately minimal and carries no
    Q-specific/Opening-specific field: a canonical return already in the
    engine call's `input_return_unit`, the two UEF-2B-named ordering
    timestamps referenced by field name only (`observed_timestamp` always
    required; `target_timestamp` required only if the policy's
    `drawdown_ordering_authority` is `TARGET_TIMESTAMP`), and the UEF-1
    `evaluation_record_id` tie-break identity.

    UEF-3B FIX1: `evaluation_record_id` must be non-empty (same `bool(x)`
    truthiness convention the FROZEN `compare_drawdown_curve_order`
    already uses for this exact field -- `bool(tie_break_id_a) and
    bool(tie_break_id_b)`, `policy.py`). An empty id means the frozen
    secondary tie-break authority is unavailable for this point; it must
    never be synthesized, defaulted from list index, or derived from
    object identity -- this is a single-point-local check (a lone point
    with an empty id is invalid on its own, regardless of any other
    point), distinct from the population-level duplicate-key check
    `calculate_max_drawdown` performs below.
    """

    canonical_return: float
    observed_timestamp: int
    evaluation_record_id: str
    target_timestamp: int | None = None

    def __post_init__(self) -> None:
        _require(
            bool(self.evaluation_record_id),
            "DrawdownCurvePoint.evaluation_record_id must be non-empty -- the frozen secondary tie-break "
            "authority is unavailable for an empty/blank id; it must never be synthesized, defaulted from "
            "list index, or derived from object identity",
        )


def _primary_timestamp(point: DrawdownCurvePoint, ordering_authority: DrawdownOrderingAuthority) -> int:
    if ordering_authority is DrawdownOrderingAuthority.OBSERVED_TIMESTAMP:
        return point.observed_timestamp
    if ordering_authority is DrawdownOrderingAuthority.TARGET_TIMESTAMP:
        _require(point.target_timestamp is not None, "calculate_max_drawdown: drawdown_ordering_authority=TARGET_TIMESTAMP requires every DrawdownCurvePoint.target_timestamp to be set")
        return point.target_timestamp
    raise MetricContractValidationError(f"calculate_max_drawdown: unhandled drawdown_ordering_authority={ordering_authority!r}")


def calculate_max_drawdown(
    *,
    points: Sequence[DrawdownCurvePoint],
    metric_policy: MetricPolicy,
    input_return_unit: ReturnUnit,
) -> DrawdownRecord:
    """Exactly UEF-3A H3's frozen additive, return-point, peak-to-trough MDD.

    `curve_0 = 0.0`; `curve_i = curve_(i-1) + canonical_return_i` for
    points walked in `metric_policy.drawdown_ordering_authority` order
    (ties broken by `evaluation_record_id`, ascending -- via UEF-3A's own
    `compare_drawdown_curve_order`, reused rather than re-derived);
    `running_peak_i = max(curve_0..curve_i)`; `drawdown_i = curve_i -
    running_peak_i`; `MDD = min(drawdown_i)`. This is a POINT figure in
    `input_return_unit`, never a percentage-of-equity ratio, never
    compounded, and the starting state is always `0.0` -- all exactly as
    `contracts.DrawdownArithmetic.ADDITIVE` and `policy.DrawdownRecord`
    already specify. Sorting `points` first makes the result independent
    of caller input order by construction.

    Only `DrawdownArithmetic.ADDITIVE` has ANY formula specified anywhere
    in the frozen UEF-3A contract (`COMPOUNDING` is "kept representable"
    but no compounding formula was ever written down) -- if
    `metric_policy.drawdown_arithmetic` is not `ADDITIVE`, this engine
    cannot compute a value without inventing new metric semantics, which
    is forbidden scope; it raises rather than guessing.

    The resulting `sample_count_in_curve`/`metric.status` pairing follows
    the SAME evaluated-count-vs-`minimum_evaluated_for_insufficient_evidence`
    rule `DrawdownRecord.__post_init__` itself already enforces (H3,
    unchanged) -- this function does not decide anything the frozen
    constructor will not independently re-verify.

    UEF-3B FIX1 (MDD determinism closure): before any sort/reduce, every
    point's canonical ordering key -- `(primary_timestamp, evaluation_record_id)`
    under the ACTIVE `ordering_authority`, exactly the same pair
    `compare_drawdown_curve_order` already treats as authoritative -- is
    validated for uniqueness. This is population-level by nature (only
    checkable once every point's key is known, never per-point in
    isolation) and independent of caller input order (a plain scan, no
    sort happens first). A duplicate key is REJECTED outright, never
    resolved by input order, dedup, first-wins/last-wins, or merge -- an
    ambiguous/invalid canonical input is UEF-3B's problem to detect, not
    UEF-6's future deduplication policy to apply here. Without this check,
    two points sharing one canonical key compare as tied under
    `compare_drawdown_curve_order` (returns 0), and Python's stable sort
    then silently preserves whatever relative order the CALLER happened
    to pass them in -- exactly the caller-input-order-as-semantic-authority
    defect this closes (reproduced independently: `[A,B]` vs `[B,A]` with
    a shared canonical key previously produced different MDD values).
    """

    _require(isinstance(metric_policy, MetricPolicy), "calculate_max_drawdown: metric_policy must be a MetricPolicy")
    if metric_policy.drawdown_arithmetic is not DrawdownArithmetic.ADDITIVE:
        raise MetricContractValidationError(
            f"calculate_max_drawdown: drawdown_arithmetic={metric_policy.drawdown_arithmetic.value} has no formula specified anywhere in the frozen UEF-3A contract "
            "(only ADDITIVE does) -- implementing COMPOUNDING would require inventing new metric semantics (UEF3B_SCOPE_ESCALATION_REQUIRED), which this engine does not do"
        )

    ordering_authority = metric_policy.drawdown_ordering_authority
    tie_break_authority = DrawdownTieBreakAuthority.EVALUATION_RECORD_ID

    # Validate every point's required timestamp field, its tie-break id,
    # and the POPULATION-level uniqueness of its canonical ordering key --
    # all up front, before any sort. `sorted()` never invokes the
    # comparator at all for a 0- or 1-element input, so a missing
    # target_timestamp or an empty evaluation_record_id on a lone point
    # would otherwise pass through silently unchecked (this was the exact
    # FIX1 defect: EMPTY_ID_SINGLE_POINT was ACCEPTED). Order of iteration
    # here does not affect the outcome: a duplicate is a duplicate
    # regardless of which of the two colliding points is seen first.
    seen_keys: dict[tuple[int, str], int] = {}
    for index, point in enumerate(points):
        _require(
            bool(point.evaluation_record_id),
            f"calculate_max_drawdown: point at input index {index} has an empty/blank evaluation_record_id -- "
            "the frozen secondary tie-break authority is unavailable for this point; it must never be "
            "synthesized, defaulted from list index, or derived from object identity",
        )
        primary_timestamp = _primary_timestamp(point, ordering_authority)
        key = (primary_timestamp, point.evaluation_record_id)
        if key in seen_keys:
            raise MetricContractValidationError(
                f"calculate_max_drawdown: duplicate canonical ordering key (primary_timestamp={primary_timestamp!r}, "
                f"evaluation_record_id={point.evaluation_record_id!r}) at input indices {seen_keys[key]} and {index} -- "
                "two points must never share one canonical ordering key; this is invalid/ambiguous input that must be "
                "rejected outright, never resolved here by input order, deduplication, or merging (that is UEF-6's "
                "future evidence-lineage/deduplication responsibility, not UEF-3B's)"
            )
        seen_keys[key] = index

    def _cmp(a: DrawdownCurvePoint, b: DrawdownCurvePoint) -> int:
        return compare_drawdown_curve_order(
            ordering_authority=ordering_authority, tie_break_authority=tie_break_authority,
            primary_timestamp_a=_primary_timestamp(a, ordering_authority), tie_break_id_a=a.evaluation_record_id,
            primary_timestamp_b=_primary_timestamp(b, ordering_authority), tie_break_id_b=b.evaluation_record_id,
        )

    ordered = sorted(points, key=functools.cmp_to_key(_cmp))

    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for point in ordered:
        equity += point.canonical_return
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)

    n = len(ordered)
    if n == 0:
        metric = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    elif metric_policy.minimum_evaluated_for_insufficient_evidence > 0 and n < metric_policy.minimum_evaluated_for_insufficient_evidence:
        metric = MetricValue(status=MetricComputationStatus.INSUFFICIENT_EVIDENCE)
    else:
        metric = MetricValue(status=MetricComputationStatus.VALID, value=mdd, unit=input_return_unit)

    return DrawdownRecord(
        metric=metric, arithmetic=metric_policy.drawdown_arithmetic, ordering_authority=ordering_authority,
        tie_break_authority=tie_break_authority, input_return_unit=input_return_unit,
        metric_policy=metric_policy, starting_equity=0.0, sample_count_in_curve=n,
    )


__all__ = [
    "DrawdownCurvePoint",
    "calculate_total_cost",
    "classify_net_return",
    "calculate_net_return",
    "calculate_profit_factor",
    "calculate_max_drawdown",
]
