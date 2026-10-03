"""UEF-3A -- Canonical Cost & Metric policy/record shapes (contract only, no engine).

Every dataclass here either (a) declares a POLICY -- how a future UEF-3B
engine should compute something, or (b) declares a RESULT SHAPE whose
construction-time invariants a UEF-3B-produced value must satisfy. No
dataclass or function in this module ever iterates over a caller-supplied
SEQUENCE of business values (returns, trades, observations) to reduce it
to an aggregate number -- that is exactly the UEF-3B boundary this file
does not cross. Every numeric field a record carries is supplied directly
by the caller (a human, a test, or eventually UEF-3B); this module only
validates internal consistency, exactly like UEF-2A's `policy.py` never
resolves a forward observation, only validates the shape of a policy that
describes how one WOULD be resolved.

Reused, never duplicated: `ReturnUnit`/`LineageStatus` (UEF-1,
canonical/contracts.py), `AggregateIdentity` (UEF-1, canonical/record.py),
`SourceResultCostSemantics` (UEF-2A, FROZEN, canonical/forward/contracts.py
-- imported read-only, this file never writes to that package).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..contracts import ReturnUnit
from ..forward.contracts import SourceResultCostSemantics
from ..record import AggregateIdentity
from .contracts import (
    METRIC_CONTRACT_SCHEMA_VERSION,
    CostAmountBasis,
    CostTiming,
    DrawdownArithmetic,
    DrawdownOrderingAuthority,
    DrawdownTieBreakAuthority,
    MetricComputationStatus,
    NetReturnComputationStatus,
    WinLossFlat,
)


class MetricContractValidationError(ValueError):
    """Raised when a UEF-3A cost/metric contract object violates its own invariants."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MetricContractValidationError(message)


def _require_enum_member(value: Any, enum_cls: type, field_name: str) -> None:
    """Direct-constructor type safety, matching UEF-2A's own established pattern
    (Boundary Closure item 32/33) -- a raw string must never silently pass."""

    _require(isinstance(value, enum_cls), f"{field_name}={value!r} must be a real {enum_cls.__name__} member, not a raw {type(value).__name__}")


_NUMERIC_EPSILON = 1e-9
"""Floating-point REPRESENTATION tolerance only (comparing two arithmetic
results for equality) -- categorically different from a business-logic
"flat" tolerance (item 8's ban on an arbitrary win/loss epsilon). This
value is never applied to a WinLossFlat classification decision."""


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:20]}"


# =========================================================================
# Cost Contract (item 5)
# =========================================================================


@dataclass(frozen=True)
class CostPolicy:
    """Canonical cost model -- commission/tax/slippage/other, one declared timing, one unit.

    `unit` reuses UEF-1's `ReturnUnit` directly (item 5A: cost and return
    share one internal representation; formatting/display is a separate,
    downstream concern never encoded here). Component magnitudes are
    always non-negative (every real cost constant found in this inventory
    -- `ROUND_TRIP_COST_PCT=0.28`, every `cost_pct`/`slippage_pct` param --
    is a positive magnitude to be SUBTRACTED from gross, never a signed
    delta). `provenance` (item 5D) names where this cost figure came from;
    a policy with a non-zero cost and empty provenance is invalid --
    losing the "where did this number come from" story is exactly the
    failure item 5D forbids.

    UEF-3A FIX1 (H1): `timing` is the DEFAULT timing applied to every
    component unless that component declares its own override below.
    `commission_timing`/`tax_timing`/`slippage_timing`/`other_cost_timing`
    (each `CostTiming | None`, default `None` meaning "use `timing`") let
    a real mixed-timing structure (e.g. commission charged on both the
    entry and exit legs -- `ROUND_TRIP` -- alongside a transaction tax
    that applies only at exit -- `EXIT_ONLY`) be represented losslessly,
    without inventing per-leg numeric sub-fields or any Q-specific shape.
    An override is only meaningful (and only accepted) on a component with
    a genuinely non-zero magnitude of its own -- declaring one on a
    zero-magnitude component carries no information and is exactly the
    kind of unresolvable ambiguity this fix closes, so it is rejected.

    UEF-3A FIX2 (H1): `amount_basis` (`CostAmountBasis`, default and only
    legal value `CANONICAL_TOTAL_CONTRIBUTION`) makes explicit WHAT each
    nonzero component magnitude means: an already-resolved TOTAL
    contribution for the interval it covers, never a per-leg tariff a
    consumer must further multiply by `CostTiming`. `CostTiming` answers
    WHEN a cost applies; `amount_basis` answers WHAT the number itself IS
    -- the two questions were conflated before this fix, leaving
    `commission=0.10, commission_timing=ROUND_TRIP` open to a "per-leg,
    double it" misreading. `total_cost` is plain addition of each
    component's magnitude, counted exactly once, regardless of timing.
    """

    timing: CostTiming
    unit: ReturnUnit
    commission: float = 0.0
    tax: float = 0.0
    slippage: float = 0.0
    other_cost: float = 0.0
    commission_timing: CostTiming | None = None
    tax_timing: CostTiming | None = None
    slippage_timing: CostTiming | None = None
    other_cost_timing: CostTiming | None = None
    amount_basis: CostAmountBasis = CostAmountBasis.CANONICAL_TOTAL_CONTRIBUTION
    provenance: str = ""
    policy_version: str = "v1"
    policy_id: str = field(default="")

    @property
    def total_cost(self) -> float:
        return self.commission + self.tax + self.slippage + self.other_cost

    def timing_for(self, component_name: str) -> CostTiming:
        """The EFFECTIVE `CostTiming` for one component -- its own override if
        declared, otherwise this policy's default `timing` (H1)."""

        if component_name not in ("commission", "tax", "slippage", "other_cost"):
            raise MetricContractValidationError(f"CostPolicy.timing_for: unknown component {component_name!r}")
        override = getattr(self, f"{component_name}_timing")
        return override if override is not None else self.timing

    def __post_init__(self) -> None:
        _require_enum_member(self.timing, CostTiming, "CostPolicy.timing")
        _require_enum_member(self.unit, ReturnUnit, "CostPolicy.unit")
        _require_enum_member(self.amount_basis, CostAmountBasis, "CostPolicy.amount_basis")
        for component_name in ("commission", "tax", "slippage", "other_cost"):
            value = getattr(self, component_name)
            _require(isinstance(value, (int, float)) and value >= 0, f"CostPolicy.{component_name} must be a non-negative number")
            override = getattr(self, f"{component_name}_timing")
            if override is not None:
                _require_enum_member(override, CostTiming, f"CostPolicy.{component_name}_timing")
                _require(value > 0, f"CostPolicy.{component_name}_timing={override.value!r} is declared but {component_name}=0 -- a per-component timing override on a zero-magnitude component carries no information and is exactly the ambiguity H1 forbids")
                _require(self.timing not in (CostTiming.NO_COST, CostTiming.ALREADY_INCLUDED), f"CostPolicy.{component_name}_timing cannot be declared when CostPolicy.timing={self.timing.value} -- that policy-level timing already requires every component to be 0, leaving no magnitude for a per-component override to apply to")
        if self.timing in (CostTiming.NO_COST, CostTiming.ALREADY_INCLUDED):
            _require(self.total_cost == 0, f"CostPolicy.timing={self.timing.value} carries no cost magnitude of its own -- component fields must all be 0 (ALREADY_INCLUDED's magnitude is unknown at this granularity; NO_COST has none by definition)")
        if self.total_cost > 0:
            _require(bool(self.provenance), "CostPolicy with a non-zero cost must declare a non-empty provenance -- a bare number with no source is exactly what item 5D forbids")
        computed_id = _stable_id("COSTPOL", {
            "timing": self.timing.value, "unit": self.unit.value, "commission": self.commission,
            "tax": self.tax, "slippage": self.slippage, "other_cost": self.other_cost,
            "commission_timing": self.commission_timing.value if self.commission_timing is not None else None,
            "tax_timing": self.tax_timing.value if self.tax_timing is not None else None,
            "slippage_timing": self.slippage_timing.value if self.slippage_timing is not None else None,
            "other_cost_timing": self.other_cost_timing.value if self.other_cost_timing is not None else None,
            "amount_basis": self.amount_basis.value,
            "provenance": self.provenance, "policy_version": self.policy_version,
        })
        if self.policy_id:
            _require(self.policy_id == computed_id, f"CostPolicy.policy_id={self.policy_id!r} does not match its own content-derived id {computed_id!r}")
        else:
            object.__setattr__(self, "policy_id", computed_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timing": self.timing.value, "unit": self.unit.value, "commission": self.commission,
            "tax": self.tax, "slippage": self.slippage, "other_cost": self.other_cost,
            "commission_timing": self.commission_timing.value if self.commission_timing is not None else None,
            "tax_timing": self.tax_timing.value if self.tax_timing is not None else None,
            "slippage_timing": self.slippage_timing.value if self.slippage_timing is not None else None,
            "other_cost_timing": self.other_cost_timing.value if self.other_cost_timing is not None else None,
            "amount_basis": self.amount_basis.value,
            "provenance": self.provenance, "policy_version": self.policy_version, "policy_id": self.policy_id,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "CostPolicy":
        raw = dict(row)

        def _opt_timing(key: str) -> CostTiming | None:
            value = raw.get(key)
            return CostTiming(value) if value else None

        return CostPolicy(
            timing=CostTiming(raw["timing"]), unit=ReturnUnit(raw["unit"]),
            commission=raw.get("commission", 0.0), tax=raw.get("tax", 0.0),
            slippage=raw.get("slippage", 0.0), other_cost=raw.get("other_cost", 0.0),
            commission_timing=_opt_timing("commission_timing"), tax_timing=_opt_timing("tax_timing"),
            slippage_timing=_opt_timing("slippage_timing"), other_cost_timing=_opt_timing("other_cost_timing"),
            amount_basis=CostAmountBasis(raw.get("amount_basis", CostAmountBasis.CANONICAL_TOTAL_CONTRIBUTION.value)),
            provenance=raw.get("provenance", ""), policy_version=raw.get("policy_version", "v1"),
            policy_id=raw.get("policy_id", ""),
        )


# =========================================================================
# Return Contract (item 6)
# =========================================================================


@dataclass(frozen=True)
class NetReturnRecord:
    """One canonical gross/cost/net return relationship -- never double-applies cost.

    `source_cost_semantics` is UEF-2A's own FROZEN `SourceResultCostSemantics`
    (read-only import; item 6's RAW_GROSS/COST_INCLUDED/NET_AUTHORITATIVE
    question is answered by reusing this existing enum, not duplicating
    it). The invariant `net_return = gross_return - cost_policy.total_cost`
    is enforced ONLY for `NetReturnComputationStatus.COMPUTED`, and
    `COMPUTED` is only legal when `source_cost_semantics is GROSS_ONLY` --
    a `NET_OR_COST_INCLUDED` source's own return figure is carried as
    `SOURCE_PROVIDED` with no arithmetic re-applied (never double-counted).
    `win_loss_flat`, when present, is cross-validated against `net_return`'s
    own sign using the canonical `WinLossFlat` rule -- this is a
    consistency CHECK on caller-supplied values, never a computation FROM
    a population.
    """

    gross_return: float | None
    return_unit: ReturnUnit
    source_cost_semantics: SourceResultCostSemantics
    computation_status: NetReturnComputationStatus
    cost_policy: CostPolicy | None = None
    net_return: float | None = None
    win_loss_flat: WinLossFlat | None = None

    def __post_init__(self) -> None:
        _require_enum_member(self.return_unit, ReturnUnit, "NetReturnRecord.return_unit")
        _require_enum_member(self.source_cost_semantics, SourceResultCostSemantics, "NetReturnRecord.source_cost_semantics")
        _require_enum_member(self.computation_status, NetReturnComputationStatus, "NetReturnRecord.computation_status")

        if self.computation_status is NetReturnComputationStatus.COMPUTED:
            _require(self.source_cost_semantics is SourceResultCostSemantics.GROSS_ONLY, "NetReturnComputationStatus.COMPUTED requires source_cost_semantics=GROSS_ONLY -- applying an explicit cost to an already-net source would double-count")
            _require(self.gross_return is not None, "NetReturnComputationStatus.COMPUTED requires a known gross_return")
            _require(self.cost_policy is not None, "NetReturnComputationStatus.COMPUTED requires a CostPolicy")
            _require(self.net_return is not None, "NetReturnComputationStatus.COMPUTED requires a net_return value")
            expected = self.gross_return - self.cost_policy.total_cost
            _require(abs(self.net_return - expected) < _NUMERIC_EPSILON, f"NetReturnRecord.net_return={self.net_return!r} does not equal gross_return-cost_policy.total_cost={expected!r} (within floating-point tolerance)")
        elif self.computation_status is NetReturnComputationStatus.SOURCE_PROVIDED:
            _require(self.source_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED, "NetReturnComputationStatus.SOURCE_PROVIDED requires source_cost_semantics=NET_OR_COST_INCLUDED")
            _require(self.net_return is not None, "NetReturnComputationStatus.SOURCE_PROVIDED requires the source's own net_return value")
            _require(self.cost_policy is None, "NetReturnComputationStatus.SOURCE_PROVIDED must not carry an explicit CostPolicy -- no arithmetic was applied by this record")
        elif self.computation_status is NetReturnComputationStatus.UNAVAILABLE:
            _require(self.net_return is None, "NetReturnComputationStatus.UNAVAILABLE must not carry a net_return value")

        if self.win_loss_flat is not None:
            _require_enum_member(self.win_loss_flat, WinLossFlat, "NetReturnRecord.win_loss_flat")
            _require(self.net_return is not None, "win_loss_flat can only be declared alongside a known net_return")
            expected_classification = WinLossFlat.WIN if self.net_return > 0 else (WinLossFlat.LOSS if self.net_return < 0 else WinLossFlat.FLAT)
            _require(self.win_loss_flat is expected_classification, f"NetReturnRecord.win_loss_flat={self.win_loss_flat.value!r} is inconsistent with net_return={self.net_return!r} (canonical rule: >0 WIN, <0 LOSS, ==0 FLAT, exact comparison)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gross_return": self.gross_return, "return_unit": self.return_unit.value,
            "source_cost_semantics": self.source_cost_semantics.value, "computation_status": self.computation_status.value,
            "cost_policy": self.cost_policy.to_dict() if self.cost_policy is not None else None,
            "net_return": self.net_return, "win_loss_flat": self.win_loss_flat.value if self.win_loss_flat is not None else None,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "NetReturnRecord":
        raw = dict(row)
        cost_policy_row = raw.get("cost_policy")
        win_loss_flat = raw.get("win_loss_flat")
        return NetReturnRecord(
            gross_return=raw.get("gross_return"), return_unit=ReturnUnit(raw["return_unit"]),
            source_cost_semantics=SourceResultCostSemantics(raw["source_cost_semantics"]),
            computation_status=NetReturnComputationStatus(raw["computation_status"]),
            cost_policy=CostPolicy.from_dict(cost_policy_row) if cost_policy_row else None,
            net_return=raw.get("net_return"), win_loss_flat=WinLossFlat(win_loss_flat) if win_loss_flat else None,
        )


# =========================================================================
# Aggregate Identity (item 12) -- REUSES UEF-1's AggregateIdentity, never duplicates it
#
# UEF-3A FIX1 (H2): moved ahead of the Sample/Population Contract below --
# `SamplePopulation` now structurally requires one of these as its
# `context`, so the class must exist first.
# =========================================================================


@dataclass(frozen=True)
class MetricAggregationContext:
    """The minimal additional dimension UEF-3 needs on top of UEF-1's own `AggregateIdentity`.

    Composition, not a new identity system: `aggregate_identity` IS UEF-1's
    existing `AggregateIdentity` (canonical/record.py), carrying
    `aggregate_ref`/`aggregation_scope`/`hypothesis_id`/`evaluator_version`
    already. The three `*_policy_id` fields below are the ONLY new
    dimension this contract adds -- references to a `forward.ForwardPolicy`
    (UEF-2A, frozen), this package's own `CostPolicy`, and this package's
    own `MetricPolicy` -- so one aggregate's result is traceable to
    EXACTLY which frozen forward-semantics and which cost/metric rules
    produced it. `horizon_label` names which `HorizonSpec.label` (UEF-2A)
    this aggregate covers (e.g. `"+30m"`) -- the minimum needed to
    disambiguate one calculator's several checkpoints, never a Q-specific
    schema.

    UEF-3A FIX1 (H2): `horizon_label` is now REQUIRED (non-empty). The
    prior optional default (`""`) meant a `SamplePopulation` could be
    (or, before this fix, HAD to be, since nothing linked the two at all)
    used interchangeably across two different horizons of the very same
    underlying event -- e.g. a `+5m` population silently reused where a
    `+30m` population was meant -- with nothing in either object's shape
    to catch the mistake. Requiring a real, non-empty `horizon_label` on
    every context is the minimum needed to make that distinction checkable
    at all.
    """

    aggregate_identity: AggregateIdentity
    horizon_label: str
    forward_policy_id: str = ""
    cost_policy_id: str = ""
    metric_policy_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.aggregate_identity, AggregateIdentity):
            raise MetricContractValidationError("MetricAggregationContext.aggregate_identity must be a UEF-1 AggregateIdentity -- a new identity system must never be invented here")
        _require(bool(self.horizon_label), "MetricAggregationContext.horizon_label must be non-empty (H2) -- a context with no declared horizon cannot be distinguished from another horizon's context of the same aggregate_identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregate_identity": {
                "canonical_aggregate_id": self.aggregate_identity.canonical_aggregate_id,
                "aggregation_scope": self.aggregate_identity.aggregation_scope,
                "hypothesis_id": self.aggregate_identity.hypothesis_id,
                "evaluator_version": self.aggregate_identity.evaluator_version,
            },
            "horizon_label": self.horizon_label,
            "forward_policy_id": self.forward_policy_id, "cost_policy_id": self.cost_policy_id,
            "metric_policy_id": self.metric_policy_id,
        }


# =========================================================================
# Sample / Population Contract (item 11)
# =========================================================================


@dataclass(frozen=True)
class SamplePopulation:
    """Canonical population accounting -- sample_count is the ONE authoritative total.

    `evaluated_count + missing_count + excluded_count == sample_count`
    (an exact-sum invariant, stronger than -- and implying -- item 18C's
    two weaker `evaluated_count <= sample_count`/`missing_count <=
    sample_count` inequalities). Canonical answers to item 11's required
    questions, evidence-derived (see contracts.py module docstring):
    - Missing forward outcomes are NEVER in a metric's denominator; the
      denominator is `evaluated_count` (matches `performance_metrics`'s
      real `win_rate = win_count/len(rows)` where `rows` already excludes
      missing observations).
    - An incomplete/missing observation counts in `sample_count` but NOT
      in `evaluated_count` (it WAS part of the candidate population, but
      never reached a determinable outcome) -- this is exactly UEF-2B's
      own `HorizonResult.missing_status` concept rolled up to population
      level; `missing_count`'s own per-item reasons are UEF-2B's
      `MissingObservationStatus` values, not re-derived here.
    - `excluded_count` is DIFFERENT from `missing_count`: an excluded
      sample was deliberately out of scope by POLICY (e.g. Q10
      Semiconductor's own `eligible` flag), never because its data was
      unavailable. The two must never be conflated into one count.
    - Deduplication of the underlying evidence is explicitly NOT this
      contract's job (UEF-6's responsibility, per item 11's own
      boundary) -- `SamplePopulation` assumes it already received a
      deduplicated candidate population; no hashing/lineage machinery is
      implemented here.

    UEF-3A FIX1 (H2): `context` (a `MetricAggregationContext`) is now a
    REQUIRED field. Before this fix, `SamplePopulation` carried no
    structural link to any aggregate/horizon at all -- nothing stopped
    the exact same population object from being (mis)used for two
    different horizons of one event. Every `SamplePopulation` now always
    declares, at the type level, exactly which aggregate+horizon it
    belongs to; `require_population_matches_context` below lets a
    consumer holding a separately-obtained `MetricAggregationContext`
    verify the two actually agree, rather than trusting a naming
    convention.
    """

    context: MetricAggregationContext
    sample_count: int
    evaluated_count: int
    missing_count: int
    excluded_count: int = 0
    exclusion_note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.context, MetricAggregationContext):
            raise MetricContractValidationError("SamplePopulation.context must be a MetricAggregationContext (H2) -- a population must always structurally declare which aggregate+horizon it belongs to")
        for count_name in ("sample_count", "evaluated_count", "missing_count", "excluded_count"):
            value = getattr(self, count_name)
            _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"SamplePopulation.{count_name} must be a non-negative integer")
        total = self.evaluated_count + self.missing_count + self.excluded_count
        _require(total == self.sample_count, f"SamplePopulation invariant violated: evaluated_count({self.evaluated_count}) + missing_count({self.missing_count}) + excluded_count({self.excluded_count}) = {total} != sample_count({self.sample_count})")
        if self.excluded_count > 0:
            _require(bool(self.exclusion_note), "SamplePopulation.excluded_count > 0 requires a non-empty exclusion_note -- an unexplained exclusion is exactly what item 5D/item 3's 'no unexplained null' principle forbids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "sample_count": self.sample_count, "evaluated_count": self.evaluated_count,
            "missing_count": self.missing_count, "excluded_count": self.excluded_count,
            "exclusion_note": self.exclusion_note,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any], *, context: "MetricAggregationContext") -> "SamplePopulation":
        """`context` is supplied by the caller (never reconstructed from `row`) --
        `MetricAggregationContext.to_dict()` intentionally drops back to
        `AggregateIdentity`'s plain fields, which cannot round-trip into a
        real `EventRef`/`AggregateIdentity` object here without reaching
        into UEF-1 machinery this module does not own."""

        raw = dict(row)
        return SamplePopulation(
            context=context,
            sample_count=raw["sample_count"], evaluated_count=raw["evaluated_count"],
            missing_count=raw["missing_count"], excluded_count=raw.get("excluded_count", 0),
            exclusion_note=raw.get("exclusion_note", ""),
        )


def require_population_matches_context(population: SamplePopulation, context: MetricAggregationContext) -> None:
    """Cross-check (H2, UEF-3A FIX2): a population obtained one way and a context
    obtained another must agree on the COMPLETE `MetricAggregationContext`
    identity -- never assumed from naming/call-order alone, and never
    checked against only a subset of its load-bearing fields.

    FIX1 checked only `aggregate_identity`/`horizon_label`, which let two
    contexts differing in `forward_policy_id`/`cost_policy_id`/
    `metric_policy_id` (while sharing the same aggregate+horizon) pass as
    "matching" -- exactly the incomplete binding this fix closes. Every
    field `MetricAggregationContext` declares is load-bearing (each names
    a distinct dimension of "which rules produced this population": which
    aggregate, which horizon, which forward/cost/metric policy) and is
    therefore checked here, each with its own explicit mismatch reason so
    a caller can tell exactly which dimension diverged.

    UEF-3A H2 FINAL AUTHORITY CORRECTION: the aggregate-identity check now
    uses UEF-1's own FULL `AggregateIdentity.__eq__` (a frozen dataclass:
    deterministic structural equality over all six of its fields --
    `aggregate_ref` (itself an `EventRef` with explicit tuple-based
    `__eq__`), `aggregation_scope`, `hypothesis_id`, `evaluator_version`,
    `evaluation_subject_id`, `evaluation_record_id`), NOT the narrower
    `canonical_aggregate_id` property it previously compared. A read-only
    architecture review established that `canonical_aggregate_id` commits
    ONLY to `aggregate_ref.canonical_event_id` and therefore cannot see
    the other five fields -- two genuinely different `AggregateIdentity`
    values (different scope/hypothesis/evaluator_version/subject id/
    record id) sharing one `aggregate_ref` produced an identical
    `canonical_aggregate_id` and were wrongly accepted as "the same
    aggregate". UEF-1's existing value-object equality is the authority
    here; no new id, hash, or identity concept is introduced, and no
    hand-picked subset of its fields is compared.
    """

    pc = population.context
    _require(
        pc.aggregate_identity == context.aggregate_identity,
        f"SamplePopulation.context.aggregate_identity={pc.aggregate_identity!r} does not match the supplied context's {context.aggregate_identity!r} -- aggregate identity mismatch (full UEF-1 AggregateIdentity equality: aggregate_ref/aggregation_scope/hypothesis_id/evaluator_version/evaluation_subject_id/evaluation_record_id must all agree; note that an equal canonical_aggregate_id alone is NOT sufficient)",
    )
    _require(
        pc.horizon_label == context.horizon_label,
        f"SamplePopulation.context.horizon_label={pc.horizon_label!r} does not match the supplied MetricAggregationContext.horizon_label={context.horizon_label!r} -- a population must never be reinterpreted under a different horizon than the one it was built for",
    )
    _require(
        pc.forward_policy_id == context.forward_policy_id,
        f"SamplePopulation.context.forward_policy_id={pc.forward_policy_id!r} does not match the supplied MetricAggregationContext.forward_policy_id={context.forward_policy_id!r} -- forward policy mismatch",
    )
    _require(
        pc.cost_policy_id == context.cost_policy_id,
        f"SamplePopulation.context.cost_policy_id={pc.cost_policy_id!r} does not match the supplied MetricAggregationContext.cost_policy_id={context.cost_policy_id!r} -- cost policy mismatch",
    )
    _require(
        pc.metric_policy_id == context.metric_policy_id,
        f"SamplePopulation.context.metric_policy_id={pc.metric_policy_id!r} does not match the supplied MetricAggregationContext.metric_policy_id={context.metric_policy_id!r} -- metric policy mismatch",
    )


@dataclass(frozen=True)
class WinLossFlatPopulation:
    """Canonical win/loss/flat breakdown of an EVALUATED population (never sample_count).

    `win_count + loss_count + flat_count == evaluated_count` of the
    `SamplePopulation` this breakdown belongs to -- cross-checked against
    it explicitly, never assumed.
    """

    win_count: int
    loss_count: int
    flat_count: int

    def __post_init__(self) -> None:
        for count_name in ("win_count", "loss_count", "flat_count"):
            value = getattr(self, count_name)
            _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"WinLossFlatPopulation.{count_name} must be a non-negative integer")

    @property
    def evaluated_count(self) -> int:
        return self.win_count + self.loss_count + self.flat_count

    def to_dict(self) -> dict[str, Any]:
        return {"win_count": self.win_count, "loss_count": self.loss_count, "flat_count": self.flat_count}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "WinLossFlatPopulation":
        raw = dict(row)
        return WinLossFlatPopulation(win_count=raw["win_count"], loss_count=raw["loss_count"], flat_count=raw["flat_count"])


def require_consistent_population(sample: SamplePopulation, breakdown: WinLossFlatPopulation) -> None:
    """Cross-contract invariant check (never an aggregation) -- raises on mismatch."""

    _require(
        breakdown.evaluated_count == sample.evaluated_count,
        f"WinLossFlatPopulation.evaluated_count={breakdown.evaluated_count} does not match SamplePopulation.evaluated_count={sample.evaluated_count}",
    )


# =========================================================================
# Metric Contract (item 7-10)
# =========================================================================


@dataclass(frozen=True)
class MetricPolicy:
    """Canonical, explicit rules a UEF-3B engine must follow -- no implicit defaults.

    `flat_tolerance` defaults to `0.0` (the ONLY value any real evidence in
    this inventory supports -- see `contracts.WinLossFlat`); changing it
    requires a new, justified, non-empty `flat_tolerance_provenance`.
    `minimum_evaluated_for_insufficient_evidence`: the policy-declared
    threshold below which a metric is `INSUFFICIENT_EVIDENCE` rather than
    `VALID` (0 disables this check -- any non-empty population is
    considered sufficient).
    """

    drawdown_arithmetic: DrawdownArithmetic = DrawdownArithmetic.ADDITIVE
    drawdown_ordering_authority: DrawdownOrderingAuthority = DrawdownOrderingAuthority.OBSERVED_TIMESTAMP
    flat_tolerance: float = 0.0
    flat_tolerance_provenance: str = ""
    minimum_evaluated_for_insufficient_evidence: int = 0
    policy_version: str = "v1"
    policy_id: str = field(default="")

    def __post_init__(self) -> None:
        _require_enum_member(self.drawdown_arithmetic, DrawdownArithmetic, "MetricPolicy.drawdown_arithmetic")
        _require_enum_member(self.drawdown_ordering_authority, DrawdownOrderingAuthority, "MetricPolicy.drawdown_ordering_authority")
        _require(isinstance(self.flat_tolerance, (int, float)) and self.flat_tolerance >= 0, "MetricPolicy.flat_tolerance must be non-negative")
        if self.flat_tolerance > 0:
            _require(bool(self.flat_tolerance_provenance), "MetricPolicy.flat_tolerance > 0 requires a non-empty flat_tolerance_provenance -- no arbitrary epsilon (item 8)")
        _require(isinstance(self.minimum_evaluated_for_insufficient_evidence, int) and self.minimum_evaluated_for_insufficient_evidence >= 0, "MetricPolicy.minimum_evaluated_for_insufficient_evidence must be a non-negative integer")
        computed_id = _stable_id("METRICPOL", {
            "drawdown_arithmetic": self.drawdown_arithmetic.value, "drawdown_ordering_authority": self.drawdown_ordering_authority.value,
            "flat_tolerance": self.flat_tolerance, "flat_tolerance_provenance": self.flat_tolerance_provenance,
            "minimum_evaluated_for_insufficient_evidence": self.minimum_evaluated_for_insufficient_evidence,
            "policy_version": self.policy_version,
        })
        if self.policy_id:
            _require(self.policy_id == computed_id, f"MetricPolicy.policy_id={self.policy_id!r} does not match its own content-derived id {computed_id!r}")
        else:
            object.__setattr__(self, "policy_id", computed_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drawdown_arithmetic": self.drawdown_arithmetic.value, "drawdown_ordering_authority": self.drawdown_ordering_authority.value,
            "flat_tolerance": self.flat_tolerance, "flat_tolerance_provenance": self.flat_tolerance_provenance,
            "minimum_evaluated_for_insufficient_evidence": self.minimum_evaluated_for_insufficient_evidence,
            "policy_version": self.policy_version, "policy_id": self.policy_id,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "MetricPolicy":
        raw = dict(row)
        return MetricPolicy(
            drawdown_arithmetic=DrawdownArithmetic(raw.get("drawdown_arithmetic", DrawdownArithmetic.ADDITIVE.value)),
            drawdown_ordering_authority=DrawdownOrderingAuthority(raw.get("drawdown_ordering_authority", DrawdownOrderingAuthority.OBSERVED_TIMESTAMP.value)),
            flat_tolerance=raw.get("flat_tolerance", 0.0), flat_tolerance_provenance=raw.get("flat_tolerance_provenance", ""),
            minimum_evaluated_for_insufficient_evidence=raw.get("minimum_evaluated_for_insufficient_evidence", 0),
            policy_version=raw.get("policy_version", "v1"), policy_id=raw.get("policy_id", ""),
        )


@dataclass(frozen=True)
class MetricValue:
    """One canonical scalar metric result -- `value` present if and only if `status is VALID`."""

    status: MetricComputationStatus
    value: float | None = None
    unit: ReturnUnit | None = None

    def __post_init__(self) -> None:
        _require_enum_member(self.status, MetricComputationStatus, "MetricValue.status")
        if self.status is MetricComputationStatus.VALID:
            _require(self.value is not None, "MetricComputationStatus.VALID requires a value")
        else:
            _require(self.value is None, f"MetricComputationStatus.{self.status.value} must not carry a value")
        if self.unit is not None:
            _require_enum_member(self.unit, ReturnUnit, "MetricValue.unit")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "value": self.value, "unit": self.unit.value if self.unit is not None else None}

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "MetricValue":
        raw = dict(row)
        unit = raw.get("unit")
        return MetricValue(status=MetricComputationStatus(raw["status"]), value=raw.get("value"), unit=ReturnUnit(unit) if unit else None)


# =========================================================================
# Objective status derivation (UEF-3A FIX1 H4, widened by FIX2 H4)
#
# Generic, metric-agnostic: decides only the population/policy-driven part
# of a `MetricComputationStatus`. A metric's own further-specific outcomes
# (PF's UNDEFINED_METRIC on a zero-loss denominator) are NOT decided here
# -- those stay each metric record's own responsibility, applied only
# once this function has already said "proceed" (VALID), never
# overriding an EMPTY_POPULATION/MISSING_EVIDENCE/INSUFFICIENT_EVIDENCE
# verdict. Operates on already-built objects, never a sequence -- stays
# inside the "no engine" boundary.
#
# UEF-3A FIX2 (H4): FIX1's `derive_population_status(evaluated_count, ...)`
# could not distinguish a truly empty population (sample_count==0) from
# one where evidence is simply MISSING (sample_count>0, evaluated_count==0
# because every candidate is still `missing`) -- both collapsed to
# EMPTY_POPULATION. The canonical function now consumes the full
# `SamplePopulation` (not just its `evaluated_count`) so this distinction,
# and the "all samples were policy-excluded" case, are both objectively
# derivable. See `derive_population_status` for the exact case table.
# =========================================================================


def derive_population_status(population: "SamplePopulation", policy: "MetricPolicy") -> MetricComputationStatus:
    """The OBJECTIVE population/policy-driven status for one `SamplePopulation`.

    Deterministic case table (UEF-3A FIX2, H4):

    - Case A (truly empty): `sample_count == 0` (which forces
      `evaluated_count == missing_count == excluded_count == 0` via
      `SamplePopulation`'s own exact-sum invariant) -> `EMPTY_POPULATION`.
    - Case B/C (evidence missing): `evaluated_count == 0`,
      `sample_count > 0`, `missing_count > 0` (regardless of whether
      `excluded_count` is also > 0 -- the missing-evidence fact is never
      hidden behind a coexisting exclusion) -> `MISSING_EVIDENCE`. This
      MUST NOT collapse to `EMPTY_POPULATION`: samples were candidated but
      never resolved, which is a materially different fact than "there
      were no candidates at all".
    - Case D (all policy-excluded): `evaluated_count == 0`,
      `sample_count > 0`, `missing_count == 0` (so, by the exact-sum
      invariant, `excluded_count == sample_count`) -> `INSUFFICIENT_EVIDENCE`.
      No new status is invented for this case: evidence exists at the
      sample/accounting level (a real candidate population existed) but
      none of it qualifies for evaluation -- the same "not enough
      evaluable evidence to trust a value" concept `INSUFFICIENT_EVIDENCE`
      already names.
    - Case E (below policy minimum): `evaluated_count > 0` and
      `evaluated_count < policy.minimum_evaluated_for_insufficient_evidence`
      (0 disables this check) -> `INSUFFICIENT_EVIDENCE`.
    - Case F (sufficient evidence): otherwise -> `VALID`, meaning only
      "population/policy do not forbid a value", NOT "this metric's own
      formula is well-defined" -- a metric-specific record (e.g.
      `ProfitFactorRecord`) may still narrow a `VALID` verdict down to its
      own `UNDEFINED_METRIC`.
    """

    if not isinstance(population, SamplePopulation):
        raise MetricContractValidationError("derive_population_status: population must be a SamplePopulation")
    if not isinstance(policy, MetricPolicy):
        raise MetricContractValidationError("derive_population_status: policy must be a MetricPolicy")

    if population.evaluated_count == 0:
        if population.sample_count == 0:
            return MetricComputationStatus.EMPTY_POPULATION
        if population.missing_count > 0:
            return MetricComputationStatus.MISSING_EVIDENCE
        return MetricComputationStatus.INSUFFICIENT_EVIDENCE

    if policy.minimum_evaluated_for_insufficient_evidence > 0 and population.evaluated_count < policy.minimum_evaluated_for_insufficient_evidence:
        return MetricComputationStatus.INSUFFICIENT_EVIDENCE
    return MetricComputationStatus.VALID


def require_status_consistent_with_population(status: MetricComputationStatus, population: "SamplePopulation", policy: "MetricPolicy") -> None:
    """Reject a caller-supplied `status` that the population/policy math contradicts (H4).

    Precedence (explicit, not caller-overridable):
    1. Derive the population's own objective evidence status.
    2. If that status is not `VALID`, the metric's `status` MUST equal it
       exactly (a caller cannot claim `EMPTY_POPULATION` for evidence that
       is actually `MISSING_EVIDENCE`, or `INSUFFICIENT_EVIDENCE` for a
       population that already meets the policy minimum, etc.).
    3. If that status IS `VALID`, population/policy no longer constrain
       the metric's status at all -- a metric-specific record may still
       narrow it further (e.g. PF's zero-loss `UNDEFINED_METRIC`), which
       this function deliberately does not decide.
    """

    _require_enum_member(status, MetricComputationStatus, "status")
    baseline = derive_population_status(population, policy)
    if baseline is not MetricComputationStatus.VALID:
        _require(status is baseline, f"population/policy objectively require status={baseline.value} (sample_count={population.sample_count}, evaluated_count={population.evaluated_count}, missing_count={population.missing_count}, excluded_count={population.excluded_count}, minimum_evaluated_for_insufficient_evidence={policy.minimum_evaluated_for_insufficient_evidence}) -- not caller-supplied {status.value}")
        return
    _require(status is not MetricComputationStatus.EMPTY_POPULATION, f"status=EMPTY_POPULATION is inconsistent with an objectively VALID population (evaluated_count={population.evaluated_count})")
    _require(status is not MetricComputationStatus.MISSING_EVIDENCE, f"status=MISSING_EVIDENCE is inconsistent with an objectively VALID population (evaluated_count={population.evaluated_count}, missing_count={population.missing_count})")
    _require(status is not MetricComputationStatus.INSUFFICIENT_EVIDENCE, f"status=INSUFFICIENT_EVIDENCE is inconsistent with evaluated_count={population.evaluated_count} already meeting/exceeding MetricPolicy.minimum_evaluated_for_insufficient_evidence={policy.minimum_evaluated_for_insufficient_evidence}")


# =========================================================================
# H3 (CLOSED, UEF-3A FIX2) -- DrawdownRecord-only evidence status
#
# A drawdown curve has no missing/excluded breakdown of its own within
# this contract's vocabulary (a point either contributed to the curve --
# counted in `sample_count_in_curve` -- or it structurally never existed
# as a curve point at all; there is no "missing curve point" concept
# analogous to `SamplePopulation.missing_count`). Widening `DrawdownRecord`
# to the FIX2 `SamplePopulation`-based rules would require inventing a
# curve-level missing/excluded concept H3's audit never asked for and
# UEF-2B evidence does not support -- exactly the opportunistic scope
# creep this Fix2 forbids. This keeps H3's ORIGINAL FIX1 evaluated-count-
# only rule verbatim, under a private name, so the public
# `derive_population_status`/`require_status_consistent_with_population`
# names can mean the richer FIX2 concept everywhere else without any
# semantic change to H3's own, already-CLOSED, validation.
# =========================================================================


def _derive_curve_evidence_status(evaluated_count: int, policy: "MetricPolicy") -> MetricComputationStatus:
    _require(isinstance(evaluated_count, int) and not isinstance(evaluated_count, bool) and evaluated_count >= 0, "_derive_curve_evidence_status: evaluated_count must be a non-negative integer")
    if not isinstance(policy, MetricPolicy):
        raise MetricContractValidationError("_derive_curve_evidence_status: policy must be a MetricPolicy")
    if evaluated_count == 0:
        return MetricComputationStatus.EMPTY_POPULATION
    if policy.minimum_evaluated_for_insufficient_evidence > 0 and evaluated_count < policy.minimum_evaluated_for_insufficient_evidence:
        return MetricComputationStatus.INSUFFICIENT_EVIDENCE
    return MetricComputationStatus.VALID


def _require_curve_status_consistent(status: MetricComputationStatus, evaluated_count: int, policy: "MetricPolicy") -> None:
    _require_enum_member(status, MetricComputationStatus, "status")
    baseline = _derive_curve_evidence_status(evaluated_count, policy)
    if baseline is MetricComputationStatus.EMPTY_POPULATION:
        _require(status is MetricComputationStatus.EMPTY_POPULATION, f"evaluated_count=0 objectively requires status=EMPTY_POPULATION, not caller-supplied {status.value} -- a caller cannot override an empty curve")
        return
    _require(status is not MetricComputationStatus.EMPTY_POPULATION, f"status=EMPTY_POPULATION is inconsistent with a non-empty evaluated_count={evaluated_count}")
    if baseline is MetricComputationStatus.INSUFFICIENT_EVIDENCE:
        _require(status is MetricComputationStatus.INSUFFICIENT_EVIDENCE, f"evaluated_count={evaluated_count} is below MetricPolicy.minimum_evaluated_for_insufficient_evidence={policy.minimum_evaluated_for_insufficient_evidence} -- status must be INSUFFICIENT_EVIDENCE, not caller-supplied {status.value}")
        return
    _require(status is not MetricComputationStatus.INSUFFICIENT_EVIDENCE, f"status=INSUFFICIENT_EVIDENCE is inconsistent with evaluated_count={evaluated_count} already meeting/exceeding MetricPolicy.minimum_evaluated_for_insufficient_evidence={policy.minimum_evaluated_for_insufficient_evidence}")


@dataclass(frozen=True)
class ProfitFactorRecord:
    """Canonical profit factor -- formula fixed (`sum(profits)/abs(sum(losses))`); every edge case explicit.

    Re-verified against all three legacy conventions (module docstring):
    the FORMULA itself is uncontested across every real implementation
    found; only the edge-case REPRESENTATION differed, and that is exactly
    what `MetricValue.status` now standardizes. Cross-validated against
    the `WinLossFlatPopulation` it was computed from -- `loss_count==0`
    can never produce `VALID` (division by zero), `evaluated_count==0` can
    never produce `VALID` (empty population).

    UEF-3A FIX1 (H4): `metric_policy` is now a REQUIRED field.

    UEF-3A FIX2 (H4): `sample` (a full `SamplePopulation`, cross-validated
    against `population` via `require_consistent_population`) is now ALSO
    a REQUIRED field, and `metric.status` is validated OBJECTIVELY against
    the FULL `sample`/`metric_policy` state via
    `require_status_consistent_with_population` -- FIX1's evaluated-count-
    only check could not distinguish an EMPTY_POPULATION sample from a
    MISSING_EVIDENCE one; this closes that gap. The zero-loss-denominator
    `UNDEFINED_METRIC` rule remains this record's own further,
    metric-specific narrowing, applied only once the population/policy
    check has already said "proceed" (`VALID`).
    """

    metric: MetricValue
    population: WinLossFlatPopulation
    sample: "SamplePopulation"
    metric_policy: "MetricPolicy"
    gross_profit: float | None = None
    gross_loss_abs: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricValue):
            raise MetricContractValidationError("ProfitFactorRecord.metric must be a MetricValue")
        if not isinstance(self.population, WinLossFlatPopulation):
            raise MetricContractValidationError("ProfitFactorRecord.population must be a WinLossFlatPopulation")
        if not isinstance(self.sample, SamplePopulation):
            raise MetricContractValidationError("ProfitFactorRecord.sample must be a SamplePopulation")
        if not isinstance(self.metric_policy, MetricPolicy):
            raise MetricContractValidationError("ProfitFactorRecord.metric_policy must be a MetricPolicy")

        require_consistent_population(self.sample, self.population)
        require_status_consistent_with_population(self.metric.status, self.sample, self.metric_policy)
        population_status = derive_population_status(self.sample, self.metric_policy)
        if population_status is MetricComputationStatus.VALID and self.population.loss_count == 0:
            _require(self.metric.status is MetricComputationStatus.UNDEFINED_METRIC, "profit factor with zero losses (whether or not there are gains) is mathematically undefined -- status must be UNDEFINED_METRIC, never inf/a sentinel/a string")

        if self.metric.status is MetricComputationStatus.VALID:
            _require(self.gross_profit is not None and self.gross_loss_abs is not None, "a VALID profit factor requires both gross_profit and gross_loss_abs")
            _require(self.gross_loss_abs > 0, "a VALID profit factor requires a strictly positive loss denominator")
            expected = self.gross_profit / self.gross_loss_abs
            _require(abs(self.metric.value - expected) < _NUMERIC_EPSILON, f"ProfitFactorRecord.metric.value={self.metric.value!r} does not equal gross_profit/gross_loss_abs={expected!r}")
        else:
            _require(self.gross_profit is None and self.gross_loss_abs is None, f"MetricComputationStatus.{self.metric.status.value} must not carry gross_profit/gross_loss_abs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.to_dict(), "population": self.population.to_dict(), "sample": self.sample.to_dict(),
            "metric_policy": self.metric_policy.to_dict(),
            "gross_profit": self.gross_profit, "gross_loss_abs": self.gross_loss_abs,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any], *, sample_context: "MetricAggregationContext") -> "ProfitFactorRecord":
        """`sample_context` is supplied by the caller for the same reason
        `SamplePopulation.from_dict` requires it -- see that method's
        docstring."""

        raw = dict(row)
        return ProfitFactorRecord(
            metric=MetricValue.from_dict(raw["metric"]), population=WinLossFlatPopulation.from_dict(raw["population"]),
            sample=SamplePopulation.from_dict(raw["sample"], context=sample_context),
            metric_policy=MetricPolicy.from_dict(raw["metric_policy"]),
            gross_profit=raw.get("gross_profit"), gross_loss_abs=raw.get("gross_loss_abs"),
        )


@dataclass(frozen=True)
class DrawdownRecord:
    """Canonical maximum-drawdown result -- arithmetic/ordering/starting-equity all explicit, never assumed.

    UEF-3A does not implement the walk itself (item 10: no MDD engine
    here) -- this record only fixes the SHAPE and the axes that must be
    pinned before any engine may walk an equity curve: `arithmetic`
    (additive vs compounding), `ordering_authority` (which timestamp field
    the input was sorted by), `starting_equity` (the curve's own t=0
    value), plus (UEF-3A FIX1, H3) `tie_break_authority`, `input_return_unit`,
    and `metric_policy`. See `contracts.DrawdownArithmetic.ADDITIVE`'s own
    docstring for the exact curve-math formula this record's fields pin
    down.

    UEF-3A FIX1 (H3) closes four incompleteness gaps found by audit:
    - Exact curve math: now formalized in `DrawdownArithmetic.ADDITIVE`'s
      docstring (curve_0=starting_equity, curve_i=curve_(i-1)+return_i,
      running_peak_i=max(curve_0..curve_i), drawdown_i=curve_i-running_peak_i,
      maximum_drawdown=min(drawdown_i)).
    - Input unit: `input_return_unit` (UEF-1's `ReturnUnit`, reused) now
      names the unit of the per-step returns the curve walks -- a VALID
      `metric.unit` must equal it (the output is a POINT figure in the
      same unit, never a percentage-of-equity ratio).
    - Tie-break ordering: `tie_break_authority` names the existing UEF-1
      identity (`evaluation_record_id`) that deterministically orders two
      curve points sharing one primary timestamp -- see
      `compare_drawdown_curve_order` below and
      `contracts.DrawdownTieBreakAuthority`.
    - Starting-state validation: `starting_equity` is now VALIDATED (must
      equal `0.0`, the only value with real evidence -- `performance_metrics`'s
      own loop) rather than merely defaulting to it.
    - Policy<->result binding: `metric_policy` (a `MetricPolicy`) is now a
      REQUIRED field, and `arithmetic`/`ordering_authority` are
      cross-validated against `metric_policy.drawdown_arithmetic`/
      `metric_policy.drawdown_ordering_authority` -- a `DrawdownRecord`
      can no longer be paired, even accidentally, with a `MetricPolicy`
      that would have produced a different arithmetic/ordering. `metric.status`
      is likewise validated OBJECTIVELY against `sample_count_in_curve`
      and `metric_policy` via the (now-private) `_require_curve_status_consistent`
      (H4) -- superseding the prior ad hoc `sample_count_in_curve==0` check.

    UEF-3A FIX2: H3 is CLOSED and UNCHANGED here -- no semantic edit.
    The ONLY change is that the status-check helper this record calls was
    renamed to `_require_curve_status_consistent` (private, verbatim
    logic) because FIX2's H4 widened the PUBLIC `derive_population_status`/
    `require_status_consistent_with_population` names to consume a full
    `SamplePopulation` (missing/excluded-aware) -- a concept a drawdown
    curve does not have and this fix does not invent for it. See the
    "H3 (CLOSED, UEF-3A FIX2)" section comment above `_derive_curve_evidence_status`.
    """

    metric: MetricValue
    arithmetic: DrawdownArithmetic
    ordering_authority: DrawdownOrderingAuthority
    tie_break_authority: DrawdownTieBreakAuthority
    input_return_unit: ReturnUnit
    metric_policy: "MetricPolicy"
    starting_equity: float = 0.0
    sample_count_in_curve: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricValue):
            raise MetricContractValidationError("DrawdownRecord.metric must be a MetricValue")
        _require_enum_member(self.arithmetic, DrawdownArithmetic, "DrawdownRecord.arithmetic")
        _require_enum_member(self.ordering_authority, DrawdownOrderingAuthority, "DrawdownRecord.ordering_authority")
        _require_enum_member(self.tie_break_authority, DrawdownTieBreakAuthority, "DrawdownRecord.tie_break_authority")
        _require_enum_member(self.input_return_unit, ReturnUnit, "DrawdownRecord.input_return_unit")
        if not isinstance(self.metric_policy, MetricPolicy):
            raise MetricContractValidationError("DrawdownRecord.metric_policy must be a MetricPolicy")
        _require(isinstance(self.sample_count_in_curve, int) and not isinstance(self.sample_count_in_curve, bool) and self.sample_count_in_curve >= 0, "DrawdownRecord.sample_count_in_curve must be a non-negative integer")
        _require(self.starting_equity == 0.0, f"DrawdownRecord.starting_equity={self.starting_equity!r} -- the ONLY value with real evidence (performance_metrics's own MDD loop) is 0.0; a nonzero starting_equity has no current real-calculator evidence and must not be silently accepted")

        _require(self.arithmetic is self.metric_policy.drawdown_arithmetic, f"DrawdownRecord.arithmetic={self.arithmetic.value} does not match metric_policy.drawdown_arithmetic={self.metric_policy.drawdown_arithmetic.value} -- a result must never be reinterpreted under a policy with different arithmetic than the one that actually governed it")
        _require(self.ordering_authority is self.metric_policy.drawdown_ordering_authority, f"DrawdownRecord.ordering_authority={self.ordering_authority.value} does not match metric_policy.drawdown_ordering_authority={self.metric_policy.drawdown_ordering_authority.value} -- a result must never be reinterpreted under a policy with different ordering than the one that actually governed it")

        _require_curve_status_consistent(self.metric.status, self.sample_count_in_curve, self.metric_policy)

        if self.metric.status is MetricComputationStatus.VALID:
            _require(self.metric.value is not None and self.metric.value <= 0, "a VALID maximum drawdown is never positive (0 means no drawdown occurred)")
            _require(self.metric.unit is not None, "a VALID maximum drawdown must declare metric.unit -- an ambiguous/absent output unit is exactly what H3's 'input unit explicit' fix forbids")
            _require(self.metric.unit is self.input_return_unit, f"DrawdownRecord.metric.unit={self.metric.unit.value} does not equal input_return_unit={self.input_return_unit.value} -- an ADDITIVE point-drawdown is a running sum of same-unit returns, so its output unit must match its input unit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.to_dict(), "arithmetic": self.arithmetic.value, "ordering_authority": self.ordering_authority.value,
            "tie_break_authority": self.tie_break_authority.value, "input_return_unit": self.input_return_unit.value,
            "metric_policy": self.metric_policy.to_dict(),
            "starting_equity": self.starting_equity, "sample_count_in_curve": self.sample_count_in_curve,
        }

    @staticmethod
    def from_dict(row: Mapping[str, Any]) -> "DrawdownRecord":
        raw = dict(row)
        return DrawdownRecord(
            metric=MetricValue.from_dict(raw["metric"]), arithmetic=DrawdownArithmetic(raw["arithmetic"]),
            ordering_authority=DrawdownOrderingAuthority(raw["ordering_authority"]),
            tie_break_authority=DrawdownTieBreakAuthority(raw["tie_break_authority"]),
            input_return_unit=ReturnUnit(raw["input_return_unit"]),
            metric_policy=MetricPolicy.from_dict(raw["metric_policy"]),
            starting_equity=raw.get("starting_equity", 0.0), sample_count_in_curve=raw.get("sample_count_in_curve", 0),
        )


def compare_drawdown_curve_order(
    *,
    ordering_authority: DrawdownOrderingAuthority,
    tie_break_authority: DrawdownTieBreakAuthority,
    primary_timestamp_a: int,
    tie_break_id_a: str,
    primary_timestamp_b: int,
    tie_break_id_b: str,
) -> int:
    """Deterministic pairwise curve-point comparator for H3's tie-break requirement.

    Pure and scalar (two candidate keys in, one of -1/0/1 out) -- never
    reduces a sequence, so it stays inside this module's "no engine"
    boundary exactly like `require_consistent_population`'s cross-check
    between two already-built objects. Orders first by
    `primary_timestamp` (the field named by `ordering_authority` --
    `HorizonResult.observed_timestamp`/`target_timestamp`, UEF-2B,
    referenced by name only); when two timestamps are exactly equal,
    orders by ascending `tie_break_id` (the identity named by
    `tie_break_authority` -- UEF-1's `evaluation_record_id`, referenced by
    name only). Symmetric by construction: comparing (a, b) and (b, a)
    always yields opposite (or both-zero) signs, so no input ordering can
    change the canonical result.
    """

    _require_enum_member(ordering_authority, DrawdownOrderingAuthority, "ordering_authority")
    _require_enum_member(tie_break_authority, DrawdownTieBreakAuthority, "tie_break_authority")
    _require(isinstance(primary_timestamp_a, int) and not isinstance(primary_timestamp_a, bool), "primary_timestamp_a must be an int")
    _require(isinstance(primary_timestamp_b, int) and not isinstance(primary_timestamp_b, bool), "primary_timestamp_b must be an int")
    _require(bool(tie_break_id_a) and bool(tie_break_id_b), "tie_break_id_a/tie_break_id_b must be non-empty")
    if primary_timestamp_a != primary_timestamp_b:
        return -1 if primary_timestamp_a < primary_timestamp_b else 1
    if tie_break_id_a == tie_break_id_b:
        return 0
    return -1 if tie_break_id_a < tie_break_id_b else 1


__all__ = [
    "METRIC_CONTRACT_SCHEMA_VERSION",
    "MetricContractValidationError",
    "CostPolicy",
    "NetReturnRecord",
    "MetricAggregationContext",
    "SamplePopulation",
    "require_population_matches_context",
    "WinLossFlatPopulation",
    "require_consistent_population",
    "MetricPolicy",
    "MetricValue",
    "derive_population_status",
    "require_status_consistent_with_population",
    "ProfitFactorRecord",
    "DrawdownRecord",
    "compare_drawdown_curve_order",
]
