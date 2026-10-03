"""UEF-3A -- Canonical Cost & Metric vocabulary (contract only, no engine).

This module names concepts only -- it computes nothing, and no function
here ever iterates over a population of samples to produce a number
(that boundary belongs to UEF-3B). Every member traces to real evidence
re-read from the current evaluation codebase (source authority order,
unchanged from every prior UEF phase: real legacy source code > real
artifact > documented source constant > this contract > any test).

Reused, never duplicated, from frozen upstream contracts:
- `libs/reporting/evaluation/canonical/contracts.py` (UEF-1): `ReturnUnit`
  (cost figures share the SAME unit axis as returns in every real source
  found -- no evidence anywhere of a bps/absolute-currency cost figure,
  so no separate `CostUnit` enum is introduced; `ReturnUnit` is reused
  directly), `LineageStatus`, `EvidenceStatus`.
- `libs/reporting/evaluation/canonical/record.py` (UEF-1): `AggregateIdentity`/
  `AggregateRecord` (the existing aggregate-identity system -- item 12's
  "do not build a new one").
- `libs/reporting/evaluation/canonical/forward/contracts.py` (UEF-2A, FROZEN):
  `SourceResultCostSemantics` (GROSS_ONLY/NET_OR_COST_INCLUDED/UNKNOWN) --
  this ALREADY answers item 6's "RAW_GROSS/COST_INCLUDED/NET_AUTHORITATIVE"
  question; a duplicate enum is not created here.
- `libs/reporting/evaluation/canonical/forward/engine.py` (UEF-2B, FROZEN):
  `HorizonResult.observed_timestamp` is the real ordering authority for
  chronological aggregation (drawdown curves, etc.) -- reused by reference
  (a field name / provenance note here), never re-imported into this
  frozen package.

Evidence inventory this module is built from (re-read, not assumed):
- `libs/reporting/evaluation/metrics.py::performance_metrics` -- the ONE
  shared aggregator reused across Q9/Q10 Semiconductor/Opening Shadow/etc:
  `win_count/loss_count/flat_count` via strict `>0`/`<0`/`==0` (no epsilon
  anywhere); `win_rate = win_count / len(rows)` where `rows` is the
  ALREADY-evaluated (missing-filtered) population -- missing observations
  are NEVER in this denominator; `profit_factor = gains/losses if losses
  else (999.0 if gains else 0.0)` -- a magic-number sentinel, never `inf`;
  MDD via a plain ADDITIVE running equity curve (`equity += value`, never
  compounded), starting equity 0.0, in whatever order `values` iterates
  (no explicit ordering authority declared by the function itself).
- `libs/research/opportunity_engine/simulator.py::summarize_trades` (Q11) --
  a SECOND, DIFFERENT profit_factor edge-case convention:
  `gross_profit/gross_loss if gross_loss>0.0 else None` (None, not a
  sentinel), and `win_rate`/every other metric is `None` (not 0.0) on an
  empty population.
- `libs/reporting/baseline_samsung_hynix/forward_validation/shadow_comparison.py::_metric`
  (Q10 Index) -- a THIRD convention:
  `profit_factor = gains/losses if losses else (None if not gains else "INF")`
  -- a bare STRING `"INF"`, not a float, not `inf`, not a sentinel number.
  These three real, live, simultaneously-shipping conventions are the
  concrete "legacy semantics가 서로 모순" case this contract must not
  silently inherit (item 22) -- none of the three is adopted verbatim;
  `MetricComputationStatus` below replaces all three with one explicit,
  never-a-magic-number, never-a-string-masquerading-as-a-number status.
- `libs/reporting/baseline_samsung_hynix/forward_returns.py::summarize_forward_returns`
  -- cost is applied per-sample BEFORE aggregation (`value - drag` for
  each observation, `drag = cost_pct + slippage_pct`), confirming
  `CostTiming.ROUND_TRIP` (a single combined subtraction, not separate
  entry/exit legs) is the dominant real pattern; also confirms this
  aggregator tracks only an EVALUATED count (`len(entered_gross)` etc.) --
  no `sample_count` (pre-missing-filter population size) survives at all,
  a real LEGACY_AMBIGUITY this contract closes rather than inherits.
- `libs/research/opportunity_engine/simulator.py::_net_return_pct` (Q11) and
  `libs/reporting/baseline_samsung_hynix/forward_validation/shadow_comparison.py`
  (`net_eod_return_pct = gross - total_cost`, `total_cost = cost_pct +
  slippage_pct`) and `libs/research/opening_rank1_longitudinal/delayed_outcomes.py::_net`
  (`ROUND_TRIP_COST_PCT=0.28` baked directly into the only return figure
  produced, no separable gross at all) -- all confirm `ROUND_TRIP` timing;
  Opening Shadow 1B/1C additionally confirm `ALREADY_INCLUDED` (source
  provides no separable gross figure whatsoever).
- Q13/Q14 (`libs/reporting/evaluation/q13_q14_validation.py`) and Q16
  (`libs/reporting/evaluation/q16_proxy_rejection_review.py`) re-read: both
  are pure downstream REVIEW/ATTRIBUTION reports that read an
  ALREADY-COMPUTED `metric` dict (win_rate/profit_factor/maximum_drawdown_pct)
  produced elsewhere -- neither defines its own independent cost/return/
  metric semantics. See §17 of the UEF-3A report for the full
  representability table and this finding's implication.
"""

from __future__ import annotations

from enum import Enum


METRIC_CONTRACT_SCHEMA_VERSION = "uef3a_cost_metric.v1"


class CostTiming(str, Enum):
    """WHEN a cost figure applies relative to one round-trip trade.

    `ROUND_TRIP` and `ALREADY_INCLUDED` and `NO_COST` all have direct real
    evidence (see module docstring). `ENTRY_ONLY`/`EXIT_ONLY` have NO
    current real-calculator evidence in this inventory -- they are kept
    ONLY because item 5C of the UEF-3A request explicitly mandates this
    exact 5-member vocabulary as the contract's required expressive range
    (a round-trip cost conceptually decomposes into entry+exit legs even
    where no current Q calculator happens to report them separately yet).
    Any future profile declaring ENTRY_ONLY/EXIT_ONLY must cite real
    evidence at the point of use, per this project's "no evidence -> no
    active semantic" rule applied everywhere else in UEF-2A/2B.

    UEF-3A FIX1 (H1): a single ``CostPolicy`` applies exactly ONE
    ``CostTiming`` value across all four of its cost components
    (commission/tax/slippage/other_cost) by default -- this remains the
    common case and matches the dominant real evidence (a single combined
    ROUND_TRIP subtraction). A real cost structure can still legitimately
    mix timings within one round trip (e.g. a commission charged on both
    legs alongside a transaction tax that applies only at exit) -- the
    prior single-field design could not represent this at all, forcing a
    silent, ambiguous choice of one timing for the whole policy. See
    ``CostPolicy``'s own per-component ``*_timing`` override fields, which
    close this gap explicitly rather than inventing a new aggregate-only
    representation.
    """

    ENTRY_ONLY = "ENTRY_ONLY"
    EXIT_ONLY = "EXIT_ONLY"
    ROUND_TRIP = "ROUND_TRIP"
    ALREADY_INCLUDED = "ALREADY_INCLUDED"
    NO_COST = "NO_COST"


class CostAmountBasis(str, Enum):
    """WHAT a nonzero `CostPolicy` component MAGNITUDE means, independent of `CostTiming`.

    UEF-3A FIX2 (H1): closes a REJECT-level ambiguity `CostTiming` alone
    could not close. `CostTiming` answers WHEN/on-which-leg a cost applies
    (semantic/provenance applicability information) -- it never answers
    WHAT a component's numeric magnitude itself represents. Without this
    enum, `commission=0.10, commission_timing=ROUND_TRIP` was open to two
    readings: (A) `0.10` is the already-resolved total contribution for
    the whole evaluated round trip, or (B) `0.10` is a PER-LEG figure a
    consumer must double (`0.10 * 2 = 0.20`) to get the round-trip total.
    UEF-3B must never be free to choose between these.

    `CANONICAL_TOTAL_CONTRIBUTION` is the ONLY member -- and the ONLY
    interpretation with any real evidence in this inventory: every real
    cost figure found (`ROUND_TRIP_COST_PCT=0.28`, every `cost_pct`/
    `slippage_pct` parameter) is already a single, fully-resolved total
    contribution for the interval it covers, never a per-leg tariff a
    caller must further multiply. A per-leg/raw-tariff basis has NO
    current real-calculator evidence anywhere in this repository, so it
    is deliberately NOT represented as a second member (this project's
    "no evidence -> no active semantic" rule, and item 5's explicit "do
    not create unnecessary future modes") -- a caller attempting to
    declare one is rejected outright (`_require_enum_member`), never
    silently reinterpreted.

    CRITICAL RULE: `CostTiming` is never a multiplier. `CostPolicy.total_cost`
    (and each component's own contribution to it) is computed by plain
    addition of already-resolved magnitudes -- `commission + tax +
    slippage + other_cost`, each counted EXACTLY ONCE -- regardless of
    which `CostTiming` a component (or its override) declares. A future
    UEF-3B engine must never derive additional cost by multiplying a
    `ROUND_TRIP`-timed magnitude by 2, by leg count, or by any other
    factor derived from `CostTiming`.
    """

    CANONICAL_TOTAL_CONTRIBUTION = "CANONICAL_TOTAL_CONTRIBUTION"


class NetReturnComputationStatus(str, Enum):
    """The OUTCOME of attempting to relate one record's gross/net return figures.

    Distinct from (and composed with) UEF-2A's frozen `SourceResultCostSemantics`:
    that enum classifies what the SOURCE's own result already contains
    (a static, per-calculator fact); this enum classifies whether THIS
    canonical record's own gross/cost/net arithmetic was actually able to
    run for one instance. `COMPUTED` only ever applies when
    `SourceResultCostSemantics.GROSS_ONLY` (an explicit `CostPolicy` was
    applied to a genuinely gross figure); `SOURCE_PROVIDED` only ever
    applies when `SourceResultCostSemantics.NET_OR_COST_INCLUDED` (the
    source's own net figure is used as-is, no arithmetic, since applying a
    SECOND cost subtraction on top would double-count); `UNAVAILABLE`
    applies when `SourceResultCostSemantics.UNKNOWN` (or any other case
    where net cannot be safely determined) -- net_return stays `None`
    rather than a guessed value.
    """

    COMPUTED = "COMPUTED"
    SOURCE_PROVIDED = "SOURCE_PROVIDED"
    UNAVAILABLE = "UNAVAILABLE"


class WinLossFlat(str, Enum):
    """Canonical trade outcome classification -- EXACT comparison, no epsilon.

    `net_return > 0 -> WIN`, `net_return < 0 -> LOSS`, `net_return == 0 ->
    FLAT`. This is the REAL rule already used, uncontested, by every
    profit-factor/win-rate implementation found in this inventory
    (`performance_metrics`, `simulator.py::summarize_trades`,
    `shadow_comparison.py::_metric` all agree on this exact three-way
    split, even though they disagree on downstream edge-case formatting).
    No floating-point tolerance is introduced: no real source uses one,
    and item 8 of the UEF-3A request explicitly forbids an arbitrary
    epsilon. If a genuine need for a tolerance is found later, it must be
    declared as an explicit, justified, named policy field (see
    `policy.MetricPolicy.flat_tolerance`) -- never a hardcoded constant.
    """

    WIN = "WIN"
    LOSS = "LOSS"
    FLAT = "FLAT"


class MetricComputationStatus(str, Enum):
    """The one, generic, explicit status for any canonical metric that cannot
    be reduced to a plain finite number.

    Replaces THREE simultaneously-shipping, mutually inconsistent legacy
    conventions found in this inventory for exactly this situation
    (`performance_metrics`'s `999.0` sentinel, `simulator.py`'s bare
    `None`, `shadow_comparison.py`'s literal string `"INF"`) with one
    taxonomy. Never `inf`, never a sentinel number, never a string
    masquerading as a number. The precise REASON a metric is
    `UNDEFINED_METRIC` (e.g. profit factor with zero losses vs. profit
    factor with zero gains AND zero losses) is always losslessly
    reconstructable from the population counts already carried alongside
    it (see `policy.WinLossFlatPopulation`) -- a second, more granular
    status taxonomy is deliberately not created on top of this one
    (checked against UEF-1's `EvidenceStatus`/UEF-2A's
    `MissingObservationStatus` first -- neither fits: `EvidenceStatus` is a
    program-lifecycle/research-maturity concept, and
    `MissingObservationStatus` explains why ONE observation is missing;
    neither answers "can THIS aggregate metric's arithmetic run".).

    - VALID: the metric was computed from a well-defined, non-degenerate
      population; `value` is present.
    - EMPTY_POPULATION: the evaluated population itself is empty (there is
      nothing to compute over at all).
    - UNDEFINED_METRIC: the population is non-empty but the metric's own
      formula is mathematically undefined for it (e.g. profit factor with
      a zero-loss denominator).
    - INSUFFICIENT_EVIDENCE: the population exists but does not meet a
      policy-declared minimum sample-size threshold for this metric to be
      considered meaningful (distinct from EMPTY_POPULATION -- some
      evidence exists, just not enough).
    - MISSING_EVIDENCE: the specific inputs this metric needs were never
      resolved at all (e.g. an MFE/MAE aggregate requested over a
      calculator whose real source never computes MFE/MAE for that
      checkpoint -- see UEF-2A's Q11 EOD `ABSENT` precedent).
    """

    VALID = "VALID"
    EMPTY_POPULATION = "EMPTY_POPULATION"
    UNDEFINED_METRIC = "UNDEFINED_METRIC"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class DrawdownArithmetic(str, Enum):
    """HOW successive returns combine into a running equity curve.

    `ADDITIVE` (`equity += return_i`, never compounded) is the ONLY member
    with real evidence -- `performance_metrics`'s own maximum-drawdown
    loop. `COMPOUNDING` is kept representable (a canonical contract must
    be able to express the general concept) but is not currently backed
    by any real calculator in this inventory; a profile declaring it must
    cite real evidence at the point of use.

    UEF-3A FIX1 (H3): the exact curve math `ADDITIVE` names, re-derived
    from `performance_metrics`'s own loop (`equity=0.0; peak=0.0; mdd=0.0;
    for value in rows: equity+=value; peak=max(peak,equity);
    mdd=min(mdd,equity-peak)`), formalized as, for a curve of `n` inputs
    ordered by `DrawdownRecord.ordering_authority` (secondary tie-break:
    `DrawdownRecord.tie_break_authority`) and a declared
    `DrawdownRecord.starting_equity` (`curve_0`):

        curve_0 = starting_equity
        curve_i = curve_(i-1) + canonical_return_i   for i = 1..n
        running_peak_i = max(curve_0, curve_1, ..., curve_i)
        drawdown_i = curve_i - running_peak_i         (always <= 0)
        maximum_drawdown = min(drawdown_1, ..., drawdown_n)

    Every `canonical_return_i` is expressed in `DrawdownRecord`'s own
    `input_return_unit` (UEF-1's `ReturnUnit`, reused) -- the resulting
    `maximum_drawdown` is a POINT figure in that SAME unit, never a
    percentage-of-equity ratio (no real evidence of the latter in this
    inventory). This module still computes nothing (UEF-3B's job) -- this
    formula is the exact contract a future engine's ADDITIVE
    implementation must satisfy, not code that runs here.
    """

    ADDITIVE = "ADDITIVE"
    COMPOUNDING = "COMPOUNDING"


class DrawdownOrderingAuthority(str, Enum):
    """WHICH timestamp field orders the equity curve `DrawdownArithmetic` walks.

    `performance_metrics` itself has NO explicit ordering authority -- it
    silently trusts whatever order its `values` iterable arrives in. This
    canonical contract does not repeat that gap (item 14's "no unordered/
    implicit-order dependency"): `OBSERVED_TIMESTAMP` names UEF-2B's own
    `HorizonResult.observed_timestamp` (frozen, engine.py) as the primary,
    always-populated-when-a-value-exists ordering authority; `TARGET_TIMESTAMP`
    names `HorizonResult.target_timestamp` as the fallback for the rare
    case an aggregate is ordered by nominal target instead of actual
    observation. Neither UEF-2A nor UEF-2B is modified to add this --
    these are pre-existing frozen field names, referenced here by name only.
    """

    OBSERVED_TIMESTAMP = "OBSERVED_TIMESTAMP"
    TARGET_TIMESTAMP = "TARGET_TIMESTAMP"


class DrawdownTieBreakAuthority(str, Enum):
    """WHICH existing canonical identity breaks a tie between two curve points
    that share the exact same primary `DrawdownOrderingAuthority` timestamp.

    UEF-3A FIX1 (H3): `DrawdownOrderingAuthority` alone is insufficient --
    two genuinely different observations (e.g. two different symbols'
    episodes) can legitimately share one `observed_timestamp`/
    `target_timestamp`, and `performance_metrics`'s own loop has no
    tie-break at all (it silently trusts whatever order its `values`
    iterable happens to arrive in -- exactly the "unordered/implicit-order
    dependency" this project already forbids for the primary axis, item
    14). `EVALUATION_RECORD_ID` names UEF-1's own `evaluation_record_id`
    (frozen, `canonical/record.py` -- content-derived, present on every
    canonical record kind uniformly, therefore always deterministic and
    always available whenever a curve point exists at all) as the
    secondary sort key: two points with an identical primary timestamp are
    ordered by ascending `evaluation_record_id` string. No new identity
    concept is introduced -- this only NAMES which existing UEF-1 identity
    resolves the tie, exactly as `DrawdownOrderingAuthority` names which
    existing timestamp field is primary. Kept as an enum (not a bare
    constant) so a future genuinely-evidenced alternative authority can be
    added without breaking this contract's shape.
    """

    EVALUATION_RECORD_ID = "EVALUATION_RECORD_ID"


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
]
