"""UEF-3C -- Canonical Aggregation Pipeline (orchestration only, no new financial math).

UEF-3A (contracts.py/policy.py, FROZEN) defined the vocabulary. UEF-3B
(engine.py, FROZEN) implemented the actual cost/net-return/PF/MDD
arithmetic. UEF-3C's job is narrower than either: take already-canonical
per-observation members, verify they all belong to exactly ONE complete
`MetricAggregationContext`, build the `SamplePopulation` accounting, hand
the evaluated members' figures to UEF-3B's frozen functions untouched,
and package the result into UEF-1's existing `AggregateRecord` -- never a
new identity, never a new record kind, never a new financial formula.

WHAT UEF-1 ALREADY OWNS (inspected before writing a single line here --
see `record.py`, frozen, read-only import):
- identity: `AggregateIdentity` (`aggregate_ref`/`aggregation_scope`/
  `hypothesis_id`/`evaluator_version`/`evaluation_subject_id`/
  `evaluation_record_id`, `canonical_aggregate_id` property). Fully
  sufficient -- reused directly via `context.aggregate_identity`, never
  duplicated.
- aggregate record: `AggregateRecord` (`identity`, `aggregation_window_start`/
  `_end`, `symbol`, `episode_count`, `source_episode_ids`, `lineage_status`,
  `metric_semantics: str` (a free-form tag), `metrics: Mapping[str, Any]`
  (a free-form payload), `quality`, `provenance`, `metadata`,
  `schema_version`). Sufficient AS-IS as UEF-3C's final output type --
  `metric_semantics`/`metrics` are exactly the extension points UEF-1
  already designed for a caller like this one; no `CanonicalAggregateV2`
  or parallel authority is created.
- evidence/status: `LineageStatus`/`EvaluationQuality` are general-purpose
  legacy/lineage concepts, NOT UEF-3A's own `SamplePopulation`/
  `MetricComputationStatus`. UEF-3C leaves them at their UEF-1 defaults
  (`LineageStatus.UNKNOWN`, default `EvaluationQuality`) rather than
  reinterpreting them -- populating them meaningfully would reach into
  UEF-6's future evidence-lineage/dedup domain, explicitly out of scope
  here.
- metric/unit representation: none of its own -- `AggregateRecord.metrics`
  is deliberately untyped, so UEF-1 left the metric shape to the caller.
  UEF-3C fills it with the frozen UEF-3A/3B `.to_dict()` shapes
  (`SamplePopulation`, `ProfitFactorRecord`, `DrawdownRecord`) under
  `metric_semantics="UEF3A_CANONICAL_V1"` -- a new STRING VALUE for an
  existing free-text field, not a new UEF-1 enum or schema change.
- `record.build_aggregate_record(...)`: builds a BRAND NEW identity from
  raw `native_id`/`derived_fields`. NOT reused here -- UEF-3C's
  `context.aggregate_identity` already exists, fully built upstream;
  calling that helper again would construct a second, competing identity.
  UEF-3C constructs `AggregateRecord` directly with
  `identity=context.aggregate_identity`.

UEF-3C therefore adds ONLY what UEF-1/UEF-3A/UEF-3B do not already own:
a per-member input tag (`SampleMemberState`/`CanonicalAggregationMember`
-- nothing existing classifies a raw candidate observation as evaluated/
missing/excluded) and a context-tagged batch wrapper
(`CanonicalSampleBatch`) so multi-source-batch context isolation can be
checked via UEF-3A's own `require_population_matches_context`, never a
reimplementation of it.

Boundaries preserved:
- Zero Q-specific/Opening-specific/strategy-name branches (verified by
  AST scan) -- this module consumes canonical members only, never a
  legacy-shaped dict (that is UEF-4's job).
- Zero duplicate/duplicated financial math -- `calculate_net_return`/
  `calculate_profit_factor`/`calculate_max_drawdown` (UEF-3B, frozen) are
  the SOLE calculation authority; this module only partitions/counts/
  delegates.
- Zero dedup/evidence-lineage logic (UEF-6's future job) -- a duplicate
  canonical MDD ordering key or an empty `evaluation_record_id` is never
  caught-and-dropped here; it propagates straight out of the frozen
  UEF-3B engine as a hard failure.
- Missing/excluded members never become a fake `0.0` return -- they are
  counted, never fed to any return-consuming function.
- Deterministic: same canonical members (in any order) + same frozen
  policies/context -> same `AggregateRecord`. No `datetime.now()`, no
  randomness, no filesystem, no environment config.

Not part of the frozen UEF manifest (a NEW sibling file inside
`metrics/`; adding it does not alter the bytes of the 10 already-frozen
files) and not re-exported through the frozen `metrics/__init__.py`;
import it directly:
    from libs.reporting.evaluation.canonical.metrics.aggregation import ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from ..forward.contracts import SourceResultCostSemantics
from ..record import AggregateRecord
from .contracts import METRIC_CONTRACT_SCHEMA_VERSION
from .engine import DrawdownCurvePoint, calculate_max_drawdown, calculate_net_return, calculate_profit_factor
from .policy import (
    CostPolicy,
    MetricAggregationContext,
    MetricContractValidationError,
    MetricPolicy,
    SamplePopulation,
    require_population_matches_context,
)
from ..contracts import ReturnUnit

_AGGREGATE_METRIC_SEMANTICS = "UEF3A_CANONICAL_V1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MetricContractValidationError(message)


class SampleMemberState(str, Enum):
    """Which of UEF-3A's frozen population-accounting states one candidate
    observation is in, before it enters aggregation.

    Definitions are UEF-3A's own, unchanged (H2/H4): `EVALUATED` = a
    canonical evaluable outcome exists; `MISSING` = evaluation expected,
    canonical observation unavailable; `EXCLUDED` = policy explicitly
    excludes this sample. This enum only TAGS one member as one of the
    three -- it decides nothing about metric math.
    """

    EVALUATED = "EVALUATED"
    MISSING = "MISSING"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True)
class CanonicalAggregationMember:
    """One candidate observation for one aggregation batch.

    `MISSING`/`EXCLUDED` members carry NO return/cost/timestamp data at
    all (structurally enforced below) -- they affect only population
    counts, never metric arithmetic, per UEF-3A's frozen population
    semantics ("missing/excluded must never become a fake 0.0 return").
    `EVALUATED` members carry exactly what UEF-3B's frozen
    `calculate_net_return`/MDD engine need: a resolved gross-or-source
    return, its `ReturnUnit`, UEF-2A's `SourceResultCostSemantics`, an
    explicit `CostPolicy` when the source is `GROSS_ONLY`, and the
    identity/ordering fields `calculate_max_drawdown` requires
    (`evaluation_record_id`, `observed_timestamp`, optional
    `target_timestamp`).
    """

    state: SampleMemberState
    evaluation_record_id: str = ""
    gross_return: float | None = None
    return_unit: ReturnUnit | None = None
    source_cost_semantics: SourceResultCostSemantics | None = None
    cost_policy: CostPolicy | None = None
    source_net_return: float | None = None
    observed_timestamp: int | None = None
    target_timestamp: int | None = None

    def __post_init__(self) -> None:
        _require(isinstance(self.state, SampleMemberState), "CanonicalAggregationMember.state must be a real SampleMemberState member")
        if self.state is SampleMemberState.EVALUATED:
            _require(bool(self.evaluation_record_id), "an EVALUATED CanonicalAggregationMember requires a non-empty evaluation_record_id (UEF-3B's frozen MDD tie-break authority)")
            _require(self.return_unit is not None, "an EVALUATED CanonicalAggregationMember requires return_unit")
            _require(self.source_cost_semantics is not None, "an EVALUATED CanonicalAggregationMember requires source_cost_semantics")
            _require(
                self.source_cost_semantics is not SourceResultCostSemantics.UNKNOWN,
                "an EVALUATED member's source_cost_semantics must not be UNKNOWN -- if the net return cannot be determined at all, "
                "this observation is not a canonical evaluable outcome and belongs in MISSING, not EVALUATED",
            )
            _require(self.observed_timestamp is not None, "an EVALUATED CanonicalAggregationMember requires observed_timestamp (UEF-3B's frozen MDD ordering authority)")
            if self.source_cost_semantics is SourceResultCostSemantics.GROSS_ONLY:
                _require(self.gross_return is not None, "GROSS_ONLY requires gross_return")
                _require(self.cost_policy is not None, "GROSS_ONLY requires an explicit cost_policy")
                _require(self.source_net_return is None, "GROSS_ONLY must not also carry source_net_return")
            elif self.source_cost_semantics is SourceResultCostSemantics.NET_OR_COST_INCLUDED:
                _require(self.source_net_return is not None, "NET_OR_COST_INCLUDED requires source_net_return")
                _require(self.cost_policy is None, "NET_OR_COST_INCLUDED must not carry an explicit cost_policy -- reapplying cost would double-count it")
                _require(self.gross_return is None, "NET_OR_COST_INCLUDED must not also carry gross_return for recomputation")
        else:
            # UEF-3C FIX1 (MEDIUM): ALL financial/evaluation observation
            # metadata must be absent for MISSING/EXCLUDED -- widened from
            # the original check (which missed return_unit/source_cost_semantics)
            # to every non-state, non-evaluation_record_id field this
            # dataclass carries. A MISSING/EXCLUDED member declaring a unit
            # or a cost-semantics convention with no actual return attached
            # is still a partially-populated financial observation, which
            # missing/excluded members must never be.
            _require(
                self.gross_return is None and self.source_net_return is None and self.cost_policy is None
                and self.return_unit is None and self.source_cost_semantics is None
                and self.observed_timestamp is None and self.target_timestamp is None,
                f"a {self.state.value} CanonicalAggregationMember must carry no financial/evaluation observation "
                "metadata at all (gross_return, source_net_return, cost_policy, return_unit, source_cost_semantics, "
                "observed_timestamp, target_timestamp must all be absent) -- missing/excluded members are "
                "accounting states, never financial observations, and must never be represented as a fake 0.0 "
                "return or a partially-populated observation",
            )


@dataclass(frozen=True)
class CanonicalSampleBatch:
    """One caller-supplied group of members, all originally recorded under
    ONE `context`. `aggregate_canonical_samples` combines multiple batches
    into a single aggregate ONLY if EVERY batch's own `context` matches
    the call's target context exactly (full `AggregateIdentity` equality
    + `horizon_label` + `forward_policy_id` + `cost_policy_id` +
    `metric_policy_id`, via UEF-3A's own `require_population_matches_context`
    -- never reimplemented). A single homogeneous list of members is just
    one batch.
    """

    context: MetricAggregationContext
    members: Sequence[CanonicalAggregationMember] = field(default_factory=tuple)


def aggregate_canonical_samples(
    *,
    context: MetricAggregationContext,
    batches: Sequence[CanonicalSampleBatch],
    metric_policy: MetricPolicy,
    input_return_unit: ReturnUnit,
    aggregation_window_start: str,
    aggregation_window_end: str = "",
    excluded_note: str = "",
) -> AggregateRecord:
    """Combine already-canonical members into ONE deterministic `AggregateRecord`.

    Provenance chain (UEF-3C FIX1 -- an aggregate is emitted only if ALL
    THREE hold; none is repaired, all fail fast):
    - every batch's own `context` matches the call's target `context`
      (`require_population_matches_context`, below);
    - the ACTUAL `metric_policy.policy_id` matches `context.metric_policy_id`
      (checked once, before any batch/context loop);
    - every EVALUATED member's ACTUALLY-USED explicit `CostPolicy.policy_id`
      (GROSS_ONLY only -- never synthesized for NET_OR_COST_INCLUDED)
      matches `context.cost_policy_id` (checked per member, before that
      member's `calculate_net_return` call).

    Steps (orchestration only -- every arithmetic step below is a direct,
    unmodified call into frozen UEF-3A/UEF-3B code):
    1. Every batch's own `context` is checked against the call's target
       `context` via `require_population_matches_context` -- a mismatch on
       ANY dimension (aggregate identity, horizon, forward/cost/metric
       policy id) rejects the WHOLE call; no partial/best-effort merge.
    2. Every member across all batches is partitioned by `state` into
       evaluated/missing/excluded, and folded into one `SamplePopulation`
       (the exact-sum invariant holds automatically -- these three groups
       are a strict partition of the input, never independently supplied
       counts that could disagree).
    3. Each EVALUATED member's return is resolved via UEF-3B's
       `calculate_net_return` (GROSS_ONLY: cost applied exactly once;
       NET_OR_COST_INCLUDED: source value as-is, no reapplication). Every
       resulting `NetReturnRecord.return_unit` must equal `input_return_unit`
       -- a population mixing PERCENTAGE_POINTS and FRACTION members fails
       explicitly here rather than being silently coerced (item 16: no
       implicit conversion, ever).
    4. The resolved net returns feed UEF-3B's `calculate_profit_factor`
       (population-evidence status is decided there, not re-decided here)
       and, packaged as `DrawdownCurvePoint`s (never sorted/reduced by
       this module -- that is `calculate_max_drawdown`'s own job), UEF-3B's
       `calculate_max_drawdown`. Neither call is wrapped in a try/except
       that could mask an invalid MDD input (empty id, duplicate canonical
       ordering key) -- such a failure propagates straight out.
    5. The `SamplePopulation`, `ProfitFactorRecord`, and `DrawdownRecord`
       results are packaged into `AggregateRecord.metrics` (a plain dict of
       their own `.to_dict()` output) under `metric_semantics="UEF3A_CANONICAL_V1"`,
       with `identity=context.aggregate_identity` -- UEF-1's existing
       identity, never a new one.

    Deterministic under any member/batch ordering: `SamplePopulation`
    counts are order-independent sums, `calculate_profit_factor` sums
    (mathematically order-independent), and `calculate_max_drawdown`
    explicitly re-sorts its points by the frozen canonical ordering key
    before walking the curve -- this function performs no ordering
    decision of its own.
    """

    _require(isinstance(context, MetricAggregationContext), "aggregate_canonical_samples: context must be a MetricAggregationContext")
    _require(isinstance(metric_policy, MetricPolicy), "aggregate_canonical_samples: metric_policy must be a MetricPolicy")
    _require(len(batches) > 0, "aggregate_canonical_samples: at least one CanonicalSampleBatch is required")

    # UEF-3C FIX1 (HIGH-1): the ACTUAL MetricPolicy used for PF/MDD must be
    # the one the declared context claims governs this aggregate -- fail
    # fast, before any batch/context loop and before any PF/MDD
    # calculation runs, never by rewriting context.metric_policy_id or
    # silently substituting a different policy object.
    _require(
        metric_policy.policy_id == context.metric_policy_id,
        f"aggregate_canonical_samples: metric_policy.policy_id={metric_policy.policy_id!r} does not match "
        f"context.metric_policy_id={context.metric_policy_id!r} -- the actual MetricPolicy used for PF/MDD must "
        "match the canonical aggregation context's declared provenance; a mismatch is rejected outright, never "
        "repaired by rewriting the context or substituting a policy object",
    )

    all_evaluated_members: list[CanonicalAggregationMember] = []
    total_sample = 0
    total_evaluated = 0
    total_missing = 0
    total_excluded = 0

    for batch in batches:
        _require(isinstance(batch, CanonicalSampleBatch), "aggregate_canonical_samples: every batch must be a CanonicalSampleBatch")
        members = batch.members
        evaluated = [m for m in members if m.state is SampleMemberState.EVALUATED]
        missing = [m for m in members if m.state is SampleMemberState.MISSING]
        excluded = [m for m in members if m.state is SampleMemberState.EXCLUDED]

        batch_population = SamplePopulation(
            context=batch.context, sample_count=len(members),
            evaluated_count=len(evaluated), missing_count=len(missing), excluded_count=len(excluded),
            exclusion_note=excluded_note if excluded else "",
        )
        # Full context-isolation authority, reused verbatim -- rejects the
        # WHOLE call if this batch's context diverges on any dimension.
        require_population_matches_context(batch_population, context)

        all_evaluated_members.extend(evaluated)
        total_sample += len(members)
        total_evaluated += len(evaluated)
        total_missing += len(missing)
        total_excluded += len(excluded)

    sample_population = SamplePopulation(
        context=context, sample_count=total_sample, evaluated_count=total_evaluated,
        missing_count=total_missing, excluded_count=total_excluded,
        exclusion_note=excluded_note if total_excluded else "",
    )

    net_returns: list[float] = []
    drawdown_points: list[DrawdownCurvePoint] = []
    for member in all_evaluated_members:
        # UEF-3C FIX1 (HIGH-2): for every member that ACTUALLY uses an
        # explicit CostPolicy (GROSS_ONLY only -- CanonicalAggregationMember's
        # own __post_init__ already forbids NET_OR_COST_INCLUDED from
        # carrying one at all, so this check naturally never fires for it;
        # no synthetic CostPolicy is invented for NET_OR_COST_INCLUDED just
        # to satisfy this rule), that policy's identity must match the
        # declared context provenance -- checked BEFORE calculate_net_return
        # is called for this member, fail fast, never overwritten.
        if member.cost_policy is not None:
            _require(
                member.cost_policy.policy_id == context.cost_policy_id,
                f"aggregate_canonical_samples: member evaluation_record_id={member.evaluation_record_id!r} "
                f"cost_policy.policy_id={member.cost_policy.policy_id!r} does not match context.cost_policy_id="
                f"{context.cost_policy_id!r} -- the actual CostPolicy applied to a GROSS_ONLY member must match "
                "the canonical aggregation context's declared cost-policy provenance; a mismatch is rejected "
                "outright, never repaired by overwriting the member's policy",
            )
        net_return_record = calculate_net_return(
            gross_return=member.gross_return, return_unit=member.return_unit,
            source_cost_semantics=member.source_cost_semantics, cost_policy=member.cost_policy,
            source_net_return=member.source_net_return, classify=False,
        )
        _require(
            net_return_record.return_unit is input_return_unit,
            f"aggregate_canonical_samples: member evaluation_record_id={member.evaluation_record_id!r} has "
            f"return_unit={net_return_record.return_unit.value} but the aggregation's input_return_unit is "
            f"{input_return_unit.value} -- no implicit PERCENTAGE_POINTS<->FRACTION conversion, ever; every "
            "evaluated member in one aggregate must already share one unit",
        )
        _require(
            net_return_record.net_return is not None,
            f"aggregate_canonical_samples: member evaluation_record_id={member.evaluation_record_id!r} resolved to no net_return "
            "-- an EVALUATED member must always resolve to a determinate value",
        )
        net_returns.append(net_return_record.net_return)
        drawdown_points.append(DrawdownCurvePoint(
            canonical_return=net_return_record.net_return, observed_timestamp=member.observed_timestamp,
            evaluation_record_id=member.evaluation_record_id, target_timestamp=member.target_timestamp,
        ))

    profit_factor_record = calculate_profit_factor(net_returns=net_returns, sample=sample_population, metric_policy=metric_policy)
    drawdown_record = calculate_max_drawdown(points=drawdown_points, metric_policy=metric_policy, input_return_unit=input_return_unit)

    metrics_payload = {
        "metric_contract_schema_version": METRIC_CONTRACT_SCHEMA_VERSION,
        "context": context.to_dict(),
        "sample_population": sample_population.to_dict(),
        "profit_factor": profit_factor_record.to_dict(),
        "max_drawdown": drawdown_record.to_dict(),
    }

    return AggregateRecord(
        identity=context.aggregate_identity,
        aggregation_window_start=aggregation_window_start,
        aggregation_window_end=aggregation_window_end,
        metric_semantics=_AGGREGATE_METRIC_SEMANTICS,
        metrics=metrics_payload,
    )


__all__ = [
    "SampleMemberState",
    "CanonicalAggregationMember",
    "CanonicalSampleBatch",
    "aggregate_canonical_samples",
]
