"""UEF-3A -- Canonical Cost & Metric Contract (contract only -- no engine).

Turns UEF-2B's canonical forward evidence/gross-return output into ONE
evaluation language for cost, return, metric, and sample/aggregation
semantics, so that "N=100", "PF=1.4", "net +0.3%", "MDD=-4%" mean exactly
the same thing regardless of which of the 12+ evaluation families (Q9
through Q18, Opening Alpha) produced them.

    - `contracts.py` -- the generic vocabulary (enums only): `CostTiming`,
      `NetReturnComputationStatus`, `WinLossFlat`, `MetricComputationStatus`,
      `DrawdownArithmetic`, `DrawdownOrderingAuthority`.
    - `policy.py` -- the policy/record dataclasses: `CostPolicy`,
      `NetReturnRecord`, `SamplePopulation`, `WinLossFlatPopulation`,
      `MetricPolicy`, `MetricValue`, `ProfitFactorRecord`, `DrawdownRecord`,
      `MetricAggregationContext`.

No calculation engine lives here (that is UEF-3B); no aggregation
implementation lives here (that is UEF-3C). Nothing here is wired into any
existing evaluator, report, or runtime path -- importing this package has
zero effect on existing behavior. UEF-1's `ReturnUnit`/`AggregateIdentity`
and UEF-2A's (frozen) `SourceResultCostSemantics` are reused throughout,
never duplicated or redefined.
"""

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
from .policy import (
    CostPolicy,
    DrawdownRecord,
    MetricAggregationContext,
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
    require_population_matches_context,
    require_status_consistent_with_population,
)

__all__ = [
    "METRIC_CONTRACT_SCHEMA_VERSION",
    "CostTiming",
    "CostAmountBasis",
    "NetReturnComputationStatus",
    "WinLossFlat",
    "MetricComputationStatus",
    "DrawdownArithmetic",
    "DrawdownOrderingAuthority",
    "DrawdownTieBreakAuthority",
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
