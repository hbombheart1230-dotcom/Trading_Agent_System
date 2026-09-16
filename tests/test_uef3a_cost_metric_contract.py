"""UEF-3A -- Canonical Cost & Metric Contract tests.

Contract-only (no engine): every test constructs objects and checks
invariants/serialization -- no test computes a metric from a raw sequence
of returns (that boundary belongs to UEF-3B). Additive-only; imports
nothing from any existing evaluator/report/runtime module.

UEF-3A FIX1 added H1-H4 closure tests and updated every pre-existing
construction site for the new required fields (`SamplePopulation.context`,
`ProfitFactorRecord.metric_policy`, `DrawdownRecord.tie_break_authority`/
`input_return_unit`/`metric_policy`, `MetricAggregationContext.horizon_label`
now mandatory).

UEF-3A FIX2 (this revision) closes 3 remaining HIGH findings from the
independent Codex closure audit -- H1 (component AMOUNT semantics, not
just timing), H2 (FULL `MetricAggregationContext` binding, not just
aggregate+horizon), H4 (`derive_population_status` widened to consume the
full `SamplePopulation` so EMPTY_POPULATION/MISSING_EVIDENCE/
INSUFFICIENT_EVIDENCE are all objectively distinguishable). H3 is CLOSED
and untouched -- see the "H3 CLOSURE" section below, unmodified from FIX1.
`ProfitFactorRecord` gained a required `sample: SamplePopulation` field
(FIX2 H4); `ProfitFactorRecord.from_dict` now takes a `sample_context`
kwarg for the same reason `SamplePopulation.from_dict` takes `context`.
"""
from __future__ import annotations

import pytest

from libs.reporting.evaluation.canonical.contracts import ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import EventRef, IdentityKind
from libs.reporting.evaluation.canonical.record import AggregateIdentity
from libs.reporting.evaluation.canonical.metrics import (
    CostAmountBasis,
    CostPolicy,
    CostTiming,
    DrawdownArithmetic,
    DrawdownOrderingAuthority,
    DrawdownRecord,
    DrawdownTieBreakAuthority,
    MetricAggregationContext,
    MetricComputationStatus,
    MetricContractValidationError,
    MetricPolicy,
    MetricValue,
    NetReturnComputationStatus,
    NetReturnRecord,
    ProfitFactorRecord,
    SamplePopulation,
    WinLossFlat,
    WinLossFlatPopulation,
    compare_drawdown_curve_order,
    derive_population_status,
    require_consistent_population,
    require_population_matches_context,
    require_status_consistent_with_population,
)


def _cost(**kwargs) -> CostPolicy:
    defaults = dict(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, slippage=0.05, provenance="test_provenance")
    defaults.update(kwargs)
    return CostPolicy(**defaults)


def _context(*, horizon_label="+30m", aggregation_scope="q10_semiconductor_calc_a", canonical_event_id="AGG_deadbeef", source_id="agg-1") -> MetricAggregationContext:
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id=source_id, canonical_event_id=canonical_event_id)
    identity = AggregateIdentity(aggregate_ref=ref, aggregation_scope=aggregation_scope, hypothesis_id="q10_semi", evaluator_version="v1")
    return MetricAggregationContext(aggregate_identity=identity, horizon_label=horizon_label)


def _sample(*, sample_count, evaluated_count, missing_count, excluded_count=0, exclusion_note="", context=None, horizon_label="+30m") -> SamplePopulation:
    return SamplePopulation(
        context=context if context is not None else _context(horizon_label=horizon_label),
        sample_count=sample_count, evaluated_count=evaluated_count, missing_count=missing_count,
        excluded_count=excluded_count, exclusion_note=exclusion_note,
    )


def _pf(*, metric, population, sample=None, metric_policy=None, gross_profit=None, gross_loss_abs=None) -> ProfitFactorRecord:
    if sample is None:
        # A default SamplePopulation consistent with `population`'s own
        # evaluated_count (require_consistent_population's own invariant) --
        # tests exercising H4's richer sample-shape rules pass an explicit
        # `sample=` instead.
        sample = _sample(sample_count=population.evaluated_count, evaluated_count=population.evaluated_count, missing_count=0)
    return ProfitFactorRecord(
        metric=metric, population=population, sample=sample,
        metric_policy=metric_policy if metric_policy is not None else MetricPolicy(),
        gross_profit=gross_profit, gross_loss_abs=gross_loss_abs,
    )


def _dd(
    *, metric, sample_count_in_curve=0, arithmetic=DrawdownArithmetic.ADDITIVE,
    ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP,
    tie_break_authority=DrawdownTieBreakAuthority.EVALUATION_RECORD_ID,
    input_return_unit=ReturnUnit.PERCENTAGE_POINTS, metric_policy=None, starting_equity=0.0,
) -> DrawdownRecord:
    if metric_policy is None:
        metric_policy = MetricPolicy(drawdown_arithmetic=arithmetic, drawdown_ordering_authority=ordering_authority)
    return DrawdownRecord(
        metric=metric, arithmetic=arithmetic, ordering_authority=ordering_authority,
        tie_break_authority=tie_break_authority, input_return_unit=input_return_unit,
        metric_policy=metric_policy, starting_equity=starting_equity, sample_count_in_curve=sample_count_in_curve,
    )


# =========================================================================
# A. Type/domain validation (item 18A)
# =========================================================================


def test_reject_invalid_cost_timing_raw_string():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing="ROUND_TRIP", unit=ReturnUnit.PERCENTAGE_POINTS, provenance="x", commission=0.1)


def test_reject_invalid_unit_raw_string():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.NO_COST, unit="PERCENTAGE_POINTS")


def test_reject_negative_cost_component():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=-0.1, provenance="x")


def test_reject_negative_sample_count():
    with pytest.raises(MetricContractValidationError):
        _sample(sample_count=-1, evaluated_count=0, missing_count=0)


def test_reject_negative_win_count():
    with pytest.raises(MetricContractValidationError):
        WinLossFlatPopulation(win_count=-1, loss_count=0, flat_count=0)


def test_reject_inconsistent_sample_evaluated_missing_counts():
    with pytest.raises(MetricContractValidationError):
        _sample(sample_count=100, evaluated_count=92, missing_count=5)  # 92+5 != 100, excluded=0


def test_reject_cost_with_no_cost_timing_but_nonzero_magnitude():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.NO_COST, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, provenance="x")


def test_reject_already_included_with_nonzero_magnitude():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ALREADY_INCLUDED, unit=ReturnUnit.PERCENTAGE_POINTS, slippage=0.28, provenance="x")


def test_reject_excluded_count_without_exclusion_note():
    with pytest.raises(MetricContractValidationError):
        _sample(sample_count=10, evaluated_count=8, missing_count=1, excluded_count=1, exclusion_note="")


def test_reject_metric_value_valid_without_a_value():
    with pytest.raises(MetricContractValidationError):
        MetricValue(status=MetricComputationStatus.VALID, value=None)


def test_reject_metric_value_non_valid_with_a_value():
    with pytest.raises(MetricContractValidationError):
        MetricValue(status=MetricComputationStatus.EMPTY_POPULATION, value=0.0)


def test_reject_arbitrary_flat_tolerance_without_provenance():
    with pytest.raises(MetricContractValidationError):
        MetricPolicy(flat_tolerance=0.0001)


def test_flat_tolerance_zero_is_the_default_and_legal():
    policy = MetricPolicy()
    assert policy.flat_tolerance == 0.0


# =========================================================================
# B. Identity/provenance (item 18B)
# =========================================================================


def test_cost_policy_id_stable_and_content_derived():
    a = _cost()
    b = _cost()
    assert a.policy_id == b.policy_id
    different = _cost(commission=0.2)
    assert different.policy_id != a.policy_id


def test_cost_policy_provenance_required_for_nonzero_cost():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, provenance="")


def test_cost_provenance_preserved_through_round_trip():
    cp = _cost(provenance="q11_simulator_cost_pct_plus_slippage_pct")
    restored = CostPolicy.from_dict(cp.to_dict())
    assert restored.provenance == "q11_simulator_cost_pct_plus_slippage_pct"
    assert restored.policy_id == cp.policy_id


def test_metric_policy_id_changes_with_content():
    a = MetricPolicy()
    b = MetricPolicy(drawdown_arithmetic=DrawdownArithmetic.COMPOUNDING)
    assert a.policy_id != b.policy_id


def test_net_return_record_rejects_mismatched_source_cost_semantics():
    # COMPUTED requires GROSS_ONLY -- NET_OR_COST_INCLUDED must never be
    # paired with an explicit re-applied CostPolicy (double-counting).
    with pytest.raises(MetricContractValidationError):
        NetReturnRecord(
            gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            computation_status=NetReturnComputationStatus.COMPUTED,
            cost_policy=_cost(), net_return=0.85,
        )


def test_net_return_record_source_provided_rejects_explicit_cost_policy():
    with pytest.raises(MetricContractValidationError):
        NetReturnRecord(
            gross_return=None, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            computation_status=NetReturnComputationStatus.SOURCE_PROVIDED,
            cost_policy=_cost(), net_return=1.22,
        )


def test_net_return_record_unavailable_rejects_a_net_value():
    with pytest.raises(MetricContractValidationError):
        NetReturnRecord(
            gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.UNKNOWN,
            computation_status=NetReturnComputationStatus.UNAVAILABLE,
            net_return=0.5,
        )


def test_win_loss_flat_cross_validated_against_net_return_sign():
    with pytest.raises(MetricContractValidationError):
        NetReturnRecord(
            gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
            computation_status=NetReturnComputationStatus.COMPUTED,
            cost_policy=_cost(), net_return=1.0 - _cost().total_cost,
            win_loss_flat=WinLossFlat.LOSS,  # net_return is positive -- must be WIN, not LOSS
        )


def test_win_loss_flat_exact_zero_is_flat_never_epsilon():
    record = NetReturnRecord(
        gross_return=0.15, return_unit=ReturnUnit.PERCENTAGE_POINTS,
        source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        computation_status=NetReturnComputationStatus.COMPUTED,
        cost_policy=_cost(commission=0.1, slippage=0.05), net_return=0.0,
        win_loss_flat=WinLossFlat.FLAT,
    )
    assert record.win_loss_flat is WinLossFlat.FLAT


# =========================================================================
# C. Sample invariants (item 18C)
# =========================================================================


def test_sample_population_evaluated_le_sample():
    sp = _sample(sample_count=100, evaluated_count=92, missing_count=8)
    assert sp.evaluated_count <= sp.sample_count


def test_sample_population_missing_le_sample():
    sp = _sample(sample_count=100, evaluated_count=92, missing_count=8)
    assert sp.missing_count <= sp.sample_count


def test_sample_population_exact_sum_invariant_stronger_than_inequalities():
    # A count set that satisfies BOTH inequalities but not the exact-sum
    # invariant must still be rejected.
    with pytest.raises(MetricContractValidationError):
        _sample(sample_count=100, evaluated_count=50, missing_count=10, excluded_count=10)  # sums to 70, not 100


def test_win_loss_flat_population_cross_check_against_sample_population():
    sample = _sample(sample_count=100, evaluated_count=92, missing_count=8)
    breakdown = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)
    require_consistent_population(sample, breakdown)  # 50+30+12 == 92, must not raise


def test_win_loss_flat_population_cross_check_rejects_mismatch():
    sample = _sample(sample_count=100, evaluated_count=92, missing_count=8)
    breakdown = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=11)  # sums to 91, not 92
    with pytest.raises(MetricContractValidationError):
        require_consistent_population(sample, breakdown)


def test_missing_and_excluded_are_distinct_counts():
    # Same total sample/evaluated split, different missing/excluded
    # attribution -- both must be independently constructible and distinct.
    missing_case = _sample(sample_count=100, evaluated_count=90, missing_count=10)
    excluded_case = _sample(sample_count=100, evaluated_count=90, missing_count=0, excluded_count=10, exclusion_note="not eligible per Q10 Semiconductor's own eligible flag")
    assert missing_case.missing_count != excluded_case.excluded_count or missing_case.excluded_count == 0
    assert missing_case.to_dict() != excluded_case.to_dict()


# =========================================================================
# D. Serialization determinism (item 18D)
# =========================================================================


def test_cost_policy_serialization_deterministic():
    cp = _cost()
    assert cp.to_dict() == CostPolicy.from_dict(cp.to_dict()).to_dict()


def test_net_return_record_serialization_round_trip():
    record = NetReturnRecord(
        gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS,
        source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        computation_status=NetReturnComputationStatus.COMPUTED,
        cost_policy=_cost(), net_return=1.0 - _cost().total_cost, win_loss_flat=WinLossFlat.WIN,
    )
    restored = NetReturnRecord.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()


def test_sample_population_serialization_round_trip():
    sp = _sample(sample_count=100, evaluated_count=92, missing_count=8)
    restored = SamplePopulation.from_dict(sp.to_dict(), context=sp.context)
    assert restored.to_dict() == sp.to_dict()


def test_metric_policy_serialization_deterministic_same_inputs_same_id():
    a = MetricPolicy.from_dict(MetricPolicy().to_dict())
    b = MetricPolicy.from_dict(MetricPolicy().to_dict())
    assert a.policy_id == b.policy_id


def test_profit_factor_record_serialization_round_trip():
    pop = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)
    mv = MetricValue(status=MetricComputationStatus.VALID, value=2.0, unit=ReturnUnit.PERCENTAGE_POINTS)
    record = _pf(metric=mv, population=pop, gross_profit=100.0, gross_loss_abs=50.0)
    restored = ProfitFactorRecord.from_dict(record.to_dict(), sample_context=record.sample.context)
    assert restored.to_dict() == record.to_dict()


# =========================================================================
# Profit factor edge cases (item 9) -- explicit, never inf/sentinel/string
# =========================================================================


def test_profit_factor_zero_losses_is_undefined_metric_never_inf_or_sentinel():
    pop = WinLossFlatPopulation(win_count=10, loss_count=0, flat_count=0)
    mv = MetricValue(status=MetricComputationStatus.UNDEFINED_METRIC)
    record = _pf(metric=mv, population=pop)
    assert record.metric.value is None
    assert record.metric.status is MetricComputationStatus.UNDEFINED_METRIC
    with pytest.raises(MetricContractValidationError):
        # zero losses + declaring VALID must be rejected outright
        _pf(metric=MetricValue(status=MetricComputationStatus.VALID, value=999.0), population=pop, gross_profit=10.0, gross_loss_abs=0.0)


def test_profit_factor_empty_population_is_empty_population_status():
    pop = WinLossFlatPopulation(win_count=0, loss_count=0, flat_count=0)
    mv = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    record = _pf(metric=mv, population=pop)
    assert record.metric.value is None


def test_profit_factor_valid_matches_formula_exactly():
    pop = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)
    mv = MetricValue(status=MetricComputationStatus.VALID, value=2.0, unit=ReturnUnit.PERCENTAGE_POINTS)
    record = _pf(metric=mv, population=pop, gross_profit=100.0, gross_loss_abs=50.0)
    assert record.metric.value == pytest.approx(record.gross_profit / record.gross_loss_abs)


def test_profit_factor_value_inconsistent_with_formula_rejected():
    pop = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)
    mv = MetricValue(status=MetricComputationStatus.VALID, value=3.0, unit=ReturnUnit.PERCENTAGE_POINTS)  # wrong
    with pytest.raises(MetricContractValidationError):
        _pf(metric=mv, population=pop, gross_profit=100.0, gross_loss_abs=50.0)


# =========================================================================
# Drawdown contract (item 10)
# =========================================================================


def test_drawdown_record_valid_value_never_positive():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=1.0, unit=ReturnUnit.PERCENTAGE_POINTS)  # invalid: positive drawdown
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=10)


def test_drawdown_record_empty_curve_is_empty_population():
    mv = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    record = _dd(metric=mv, sample_count_in_curve=0)
    assert record.sample_count_in_curve == 0


def test_drawdown_record_ordering_authority_explicit_no_default_guessing():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=-4.2, unit=ReturnUnit.PERCENTAGE_POINTS)
    record = _dd(metric=mv, sample_count_in_curve=92)
    assert record.ordering_authority is DrawdownOrderingAuthority.OBSERVED_TIMESTAMP
    restored = DrawdownRecord.from_dict(record.to_dict())
    assert restored.ordering_authority is DrawdownOrderingAuthority.OBSERVED_TIMESTAMP


# =========================================================================
# Aggregate identity reuse (item 12)
# =========================================================================


def test_metric_aggregation_context_reuses_uef1_aggregate_identity():
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id="agg-1", canonical_event_id="AGG_deadbeef")
    identity = AggregateIdentity(aggregate_ref=ref, aggregation_scope="q10_semiconductor_calc_a", hypothesis_id="q10_semi", evaluator_version="v1")
    context = MetricAggregationContext(aggregate_identity=identity, forward_policy_id="FWDPOL_abc", cost_policy_id="COSTPOL_def", metric_policy_id="METRICPOL_ghi", horizon_label="+30m")
    assert context.aggregate_identity is identity
    assert context.to_dict()["aggregate_identity"]["aggregation_scope"] == "q10_semiconductor_calc_a"


def test_metric_aggregation_context_rejects_non_aggregate_identity():
    with pytest.raises(MetricContractValidationError):
        MetricAggregationContext(aggregate_identity={"not": "an AggregateIdentity"}, horizon_label="+30m")


# =========================================================================
# H1 CLOSURE -- cost component timing (UEF-3A FIX1)
# =========================================================================


def test_h1_cost_policy_mixed_component_timing_losslessly_representable():
    # Real mixed structure: commission charged on BOTH legs (ROUND_TRIP,
    # the policy-level default) alongside a transaction tax that applies
    # ONLY at exit (an explicit per-component override).
    cp = CostPolicy(
        timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS,
        commission=0.05, tax=0.02, tax_timing=CostTiming.EXIT_ONLY,
        provenance="mixed_commission_both_leg_tax_exit_only",
    )
    assert cp.timing_for("commission") is CostTiming.ROUND_TRIP
    assert cp.timing_for("tax") is CostTiming.EXIT_ONLY
    assert cp.timing_for("slippage") is CostTiming.ROUND_TRIP  # no override -> falls back to policy default
    assert cp.total_cost == pytest.approx(0.07)


def test_h1_cost_policy_component_timing_serialization_deterministic():
    cp = CostPolicy(
        timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS,
        commission=0.05, tax=0.02, tax_timing=CostTiming.EXIT_ONLY,
        provenance="mixed_commission_both_leg_tax_exit_only",
    )
    restored = CostPolicy.from_dict(cp.to_dict())
    assert restored.to_dict() == cp.to_dict()
    assert restored.timing_for("commission") is CostTiming.ROUND_TRIP
    assert restored.timing_for("tax") is CostTiming.EXIT_ONLY
    assert restored.policy_id == cp.policy_id


def test_h1_component_timing_override_rejected_on_zero_magnitude_component():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, tax=0.0, tax_timing=CostTiming.EXIT_ONLY, provenance="x")


def test_h1_component_timing_override_rejected_when_policy_timing_is_no_cost():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.NO_COST, unit=ReturnUnit.PERCENTAGE_POINTS, commission_timing=CostTiming.ENTRY_ONLY)


def test_h1_component_timing_override_rejects_raw_string():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, commission_timing="ROUND_TRIP", provenance="x")


def test_h1_gross_only_computed_applies_mixed_timing_cost_exactly_once():
    cp = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.05, tax=0.02, tax_timing=CostTiming.EXIT_ONLY, provenance="x")
    record = NetReturnRecord(
        gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS,
        source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        computation_status=NetReturnComputationStatus.COMPUTED,
        cost_policy=cp, net_return=1.0 - cp.total_cost,
    )
    assert record.net_return == pytest.approx(1.0 - 0.07)


def test_h1_net_or_cost_included_cannot_receive_explicit_reapplication_policy():
    # Same invariant as the pre-existing SOURCE_PROVIDED test, re-verified
    # against a mixed-component-timing CostPolicy shape.
    cp = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.05, tax=0.02, tax_timing=CostTiming.EXIT_ONLY, provenance="x")
    with pytest.raises(MetricContractValidationError):
        NetReturnRecord(
            gross_return=None, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            computation_status=NetReturnComputationStatus.SOURCE_PROVIDED,
            cost_policy=cp, net_return=1.22,
        )


# =========================================================================
# H1 CLOSURE -- component AMOUNT semantics (UEF-3A FIX2)
# =========================================================================


def test_h1a_round_trip_magnitude_is_total_contribution_not_per_leg():
    cp = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="x")
    assert cp.amount_basis is CostAmountBasis.CANONICAL_TOTAL_CONTRIBUTION
    # canonically means total contribution 0.10, never 0.10*2=0.20
    assert cp.total_cost == pytest.approx(0.10)
    assert cp.total_cost != pytest.approx(0.20)


def test_h1b_asymmetric_components_sum_to_canonical_total_without_q_specific_logic():
    cp = CostPolicy(
        timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS,
        commission=0.10, tax=0.20, tax_timing=CostTiming.EXIT_ONLY, provenance="x",
    )
    assert cp.total_cost == pytest.approx(0.30)


def test_h1c_amount_basis_participates_in_stable_policy_identity():
    a = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="x")
    b = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="x", amount_basis=CostAmountBasis.CANONICAL_TOTAL_CONTRIBUTION)
    assert a.policy_id == b.policy_id
    restored = CostPolicy.from_dict(a.to_dict())
    assert restored.policy_id == a.policy_id
    assert restored.amount_basis is CostAmountBasis.CANONICAL_TOTAL_CONTRIBUTION


def test_h1d_unsupported_amount_basis_rejected_not_silently_reinterpreted():
    with pytest.raises(MetricContractValidationError):
        CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="x", amount_basis="PER_LEG")


def test_h1_timing_is_never_a_multiplier_across_all_timings():
    # The SAME magnitude must mean the SAME canonical total regardless of
    # which CostTiming it is declared under -- CostTiming is applicability
    # information, never a multiplier.
    for timing in (CostTiming.ROUND_TRIP, CostTiming.ENTRY_ONLY, CostTiming.EXIT_ONLY):
        cp = CostPolicy(timing=timing, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="x")
        assert cp.total_cost == pytest.approx(0.10)


# =========================================================================
# H2 CLOSURE -- sample population bound to aggregation context/horizon (UEF-3A FIX1)
# =========================================================================


def test_h2_sample_population_requires_metric_aggregation_context():
    with pytest.raises(MetricContractValidationError):
        SamplePopulation(context={"not": "a context"}, sample_count=10, evaluated_count=10, missing_count=0)


def test_h2_metric_aggregation_context_requires_nonempty_horizon_label():
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id="agg-1", canonical_event_id="AGG_deadbeef")
    identity = AggregateIdentity(aggregate_ref=ref, aggregation_scope="q10_semiconductor_calc_a")
    with pytest.raises(MetricContractValidationError):
        MetricAggregationContext(aggregate_identity=identity, horizon_label="")


def test_h2_same_event_different_horizons_cannot_silently_share_one_population_context():
    context_5m = _context(horizon_label="+5m")
    context_30m = _context(horizon_label="+30m")
    assert context_5m.aggregate_identity.canonical_aggregate_id == context_30m.aggregate_identity.canonical_aggregate_id
    pop_5m = _sample(sample_count=100, evaluated_count=92, missing_count=8, horizon_label="+5m")
    pop_30m = _sample(sample_count=100, evaluated_count=80, missing_count=20, horizon_label="+30m")
    assert pop_5m.context.horizon_label != pop_30m.context.horizon_label
    require_population_matches_context(pop_5m, context_5m)  # must not raise
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop_5m, context_30m)


def test_h2_population_context_horizon_mismatch_rejected():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, horizon_label="+5m")
    other_context = _context(horizon_label="+30m")
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, other_context)


def test_h2_sample_arithmetic_remains_exact_with_context_bound():
    sp = _sample(sample_count=100, evaluated_count=92, missing_count=8, horizon_label="+5m")
    assert sp.evaluated_count + sp.missing_count + sp.excluded_count == sp.sample_count


def test_h2_missing_and_excluded_remain_distinct_with_context_bound():
    missing_case = _sample(sample_count=100, evaluated_count=90, missing_count=10, horizon_label="+5m")
    excluded_case = _sample(sample_count=100, evaluated_count=90, missing_count=0, excluded_count=10, exclusion_note="not eligible", horizon_label="+5m")
    assert missing_case.missing_count == 10 and missing_case.excluded_count == 0
    assert excluded_case.missing_count == 0 and excluded_case.excluded_count == 10


# =========================================================================
# H2 CLOSURE -- FULL MetricAggregationContext binding (UEF-3A FIX2)
# =========================================================================


def _full_context(*, horizon_label="+30m", forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id="METRICPOL_a") -> MetricAggregationContext:
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id="agg-1", canonical_event_id="AGG_deadbeef")
    identity = AggregateIdentity(aggregate_ref=ref, aggregation_scope="q10_semiconductor_calc_a", hypothesis_id="q10_semi", evaluator_version="v1")
    return MetricAggregationContext(
        aggregate_identity=identity, horizon_label=horizon_label,
        forward_policy_id=forward_policy_id, cost_policy_id=cost_policy_id, metric_policy_id=metric_policy_id,
    )


def test_h2_full_context_exact_match_passes():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context())
    require_population_matches_context(pop, _full_context())  # must not raise


def test_h2_full_context_horizon_mismatch_rejected():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context(horizon_label="+5m"))
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, _full_context(horizon_label="+30m"))


def test_h2_full_context_aggregate_identity_mismatch_rejected():
    other_ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id="agg-2", canonical_event_id="AGG_feedface")
    other_identity = AggregateIdentity(aggregate_ref=other_ref, aggregation_scope="q10_semiconductor_calc_b", hypothesis_id="q10_semi", evaluator_version="v1")
    other_context = MetricAggregationContext(aggregate_identity=other_identity, horizon_label="+30m", forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id="METRICPOL_a")
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context())
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, other_context)


def test_h2_full_context_forward_policy_id_mismatch_rejected():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context(forward_policy_id="FWDPOL_a"))
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, _full_context(forward_policy_id="FWDPOL_b"))


def test_h2_full_context_cost_policy_id_mismatch_rejected():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context(cost_policy_id="COSTPOL_a"))
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, _full_context(cost_policy_id="COSTPOL_b"))


def test_h2_full_context_metric_policy_id_mismatch_rejected():
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_full_context(metric_policy_id="METRICPOL_a"))
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, _full_context(metric_policy_id="METRICPOL_b"))


def test_h2_sample_arithmetic_invariant_still_exact_under_full_context():
    sp = _sample(sample_count=100, evaluated_count=92, missing_count=8, context=_full_context())
    assert sp.evaluated_count + sp.missing_count + sp.excluded_count == sp.sample_count


# =========================================================================
# H2 FINAL AUTHORITY CORRECTION -- full UEF-1 AggregateIdentity equality
#
# `canonical_aggregate_id` commits ONLY to `aggregate_ref.canonical_event_id`
# and cannot see AggregateIdentity's other five fields. Every helper below
# holds `aggregate_ref` CONSTANT, so every variant shares one identical
# `canonical_aggregate_id` -- precisely the condition under which the
# previous (narrower) authority wrongly accepted a genuine mismatch. The
# authority is now UEF-1's own `AggregateIdentity.__eq__`.
# =========================================================================


def _identity_variant(
    *, aggregation_scope="q10_semiconductor_calc_a", hypothesis_id="q10_semi", evaluator_version="v1",
    evaluation_subject_id="", evaluation_record_id="",
) -> AggregateIdentity:
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3a_test", source_id="agg-1", canonical_event_id="AGG_deadbeef")
    return AggregateIdentity(
        aggregate_ref=ref, aggregation_scope=aggregation_scope, hypothesis_id=hypothesis_id,
        evaluator_version=evaluator_version, evaluation_subject_id=evaluation_subject_id,
        evaluation_record_id=evaluation_record_id,
    )


def _context_for(identity: AggregateIdentity, *, horizon_label="+30m") -> MetricAggregationContext:
    return MetricAggregationContext(
        aggregate_identity=identity, horizon_label=horizon_label,
        forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id="METRICPOL_a",
    )


def _reject_identity_variant(variant: AggregateIdentity) -> None:
    """Shared body for Tests A-E: the variant shares one canonical_aggregate_id
    with the baseline identity (so the OLD authority would have accepted it)
    but differs in another AggregateIdentity field, so the NEW full-equality
    authority must reject it."""

    baseline = _identity_variant()
    assert baseline.canonical_aggregate_id == variant.canonical_aggregate_id  # precondition: old authority would accept
    assert baseline != variant  # full UEF-1 equality distinguishes them
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_context_for(baseline))
    with pytest.raises(MetricContractValidationError):
        require_population_matches_context(pop, _context_for(variant))


def test_h2_authority_a_same_canonical_id_different_aggregation_scope_rejected():
    _reject_identity_variant(_identity_variant(aggregation_scope="q10_semiconductor_calc_b_DIFFERENT"))


def test_h2_authority_b_same_canonical_id_different_hypothesis_id_rejected():
    _reject_identity_variant(_identity_variant(hypothesis_id="q10_semi_DIFFERENT"))


def test_h2_authority_c_same_canonical_id_different_evaluator_version_rejected():
    _reject_identity_variant(_identity_variant(evaluator_version="v2_DIFFERENT"))


def test_h2_authority_d_same_canonical_id_different_evaluation_subject_id_rejected():
    _reject_identity_variant(_identity_variant(evaluation_subject_id="SUBJ_different"))


def test_h2_authority_e_same_canonical_id_different_evaluation_record_id_rejected():
    _reject_identity_variant(_identity_variant(evaluation_record_id="REC_different"))


def test_h2_authority_f_structurally_equal_but_distinct_objects_pass():
    # Two INDEPENDENTLY constructed AggregateIdentity values (distinct
    # objects, distinct nested EventRef objects) that are structurally
    # equal must be accepted -- proving structural equality, never object
    # identity, is the authority.
    identity_a = _identity_variant()
    identity_b = _identity_variant()
    assert identity_a is not identity_b
    assert identity_a.aggregate_ref is not identity_b.aggregate_ref
    assert identity_a == identity_b
    pop = _sample(sample_count=10, evaluated_count=10, missing_count=0, context=_context_for(identity_a))
    require_population_matches_context(pop, _context_for(identity_b))  # must not raise


# =========================================================================
# H3 CLOSURE -- MDD exact curve math / input unit / tie-break / starting-state / policy binding (UEF-3A FIX1)
# =========================================================================


def test_h3_drawdown_record_input_unit_explicit_and_matches_output_unit():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=-4.2, unit=ReturnUnit.PERCENTAGE_POINTS)
    record = _dd(metric=mv, sample_count_in_curve=10, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.input_return_unit is ReturnUnit.PERCENTAGE_POINTS
    assert record.metric.unit is record.input_return_unit


def test_h3_drawdown_record_output_unit_mismatch_with_input_unit_rejected():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=-4.2, unit=ReturnUnit.FRACTION)
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=10, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)


def test_h3_drawdown_record_valid_requires_a_declared_unit():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=-4.2, unit=None)
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=10)


def test_h3_drawdown_record_rejects_nonzero_starting_equity():
    mv = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=0, starting_equity=100.0)


def test_h3_drawdown_record_rejects_policy_mismatch_arithmetic():
    policy = MetricPolicy(drawdown_arithmetic=DrawdownArithmetic.COMPOUNDING, drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    mv = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=0, arithmetic=DrawdownArithmetic.ADDITIVE, metric_policy=policy)


def test_h3_drawdown_record_rejects_policy_mismatch_ordering_authority():
    policy = MetricPolicy(drawdown_arithmetic=DrawdownArithmetic.ADDITIVE, drawdown_ordering_authority=DrawdownOrderingAuthority.TARGET_TIMESTAMP)
    mv = MetricValue(status=MetricComputationStatus.EMPTY_POPULATION)
    with pytest.raises(MetricContractValidationError):
        _dd(metric=mv, sample_count_in_curve=0, ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP, metric_policy=policy)


def test_h3_compare_drawdown_curve_order_same_timestamp_different_identities_deterministic():
    kwargs = dict(ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP, tie_break_authority=DrawdownTieBreakAuthority.EVALUATION_RECORD_ID)
    result_ab = compare_drawdown_curve_order(primary_timestamp_a=1000, tie_break_id_a="REC_aaa", primary_timestamp_b=1000, tie_break_id_b="REC_bbb", **kwargs)
    result_ba = compare_drawdown_curve_order(primary_timestamp_a=1000, tie_break_id_a="REC_bbb", primary_timestamp_b=1000, tie_break_id_b="REC_aaa", **kwargs)
    assert result_ab == -1
    assert result_ba == 1
    assert result_ab == -result_ba
    result_tied = compare_drawdown_curve_order(primary_timestamp_a=1000, tie_break_id_a="REC_aaa", primary_timestamp_b=1000, tie_break_id_b="REC_aaa", **kwargs)
    assert result_tied == 0


def test_h3_compare_drawdown_curve_order_input_ordering_does_not_alter_canonical_ordering():
    kwargs = dict(ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP, tie_break_authority=DrawdownTieBreakAuthority.EVALUATION_RECORD_ID)
    forward = compare_drawdown_curve_order(primary_timestamp_a=100, tie_break_id_a="REC_x", primary_timestamp_b=200, tie_break_id_b="REC_y", **kwargs)
    backward = compare_drawdown_curve_order(primary_timestamp_a=200, tie_break_id_a="REC_y", primary_timestamp_b=100, tie_break_id_b="REC_x", **kwargs)
    assert forward == -1
    assert backward == 1


def test_h3_drawdown_record_serialization_round_trip_preserves_h3_fields():
    mv = MetricValue(status=MetricComputationStatus.VALID, value=-4.2, unit=ReturnUnit.PERCENTAGE_POINTS)
    record = _dd(metric=mv, sample_count_in_curve=92)
    restored = DrawdownRecord.from_dict(record.to_dict())
    assert restored.to_dict() == record.to_dict()
    assert restored.tie_break_authority is DrawdownTieBreakAuthority.EVALUATION_RECORD_ID
    assert restored.input_return_unit is ReturnUnit.PERCENTAGE_POINTS


# =========================================================================
# H4 CLOSURE -- metric status objectively bound to full SamplePopulation + policy (UEF-3A FIX2)
#
# Case table (see `derive_population_status`'s own docstring for the
# authoritative version): A truly-empty (sample_count==0) -> EMPTY_POPULATION;
# B/C evidence-missing (evaluated==0, sample>0, missing>0) -> MISSING_EVIDENCE;
# D all-excluded (evaluated==0, sample>0, missing==0) -> INSUFFICIENT_EVIDENCE;
# E below policy minimum -> INSUFFICIENT_EVIDENCE; F sufficient -> VALID.
# =========================================================================


def test_h4_case_a_truly_empty_is_empty_population():
    sample = _sample(sample_count=0, evaluated_count=0, missing_count=0)
    assert derive_population_status(sample, MetricPolicy()) is MetricComputationStatus.EMPTY_POPULATION


def test_h4_case_b_missing_only_is_missing_evidence_never_empty_population():
    sample = _sample(sample_count=10, evaluated_count=0, missing_count=10, excluded_count=0)
    assert derive_population_status(sample, MetricPolicy()) is MetricComputationStatus.MISSING_EVIDENCE


def test_h4_case_c_missing_and_excluded_coexisting_still_missing_evidence():
    sample = _sample(sample_count=10, evaluated_count=0, missing_count=7, excluded_count=3, exclusion_note="not eligible")
    assert derive_population_status(sample, MetricPolicy()) is MetricComputationStatus.MISSING_EVIDENCE


def test_h4_case_d_all_policy_excluded_is_insufficient_evidence():
    sample = _sample(sample_count=10, evaluated_count=0, missing_count=0, excluded_count=10, exclusion_note="all excluded per policy")
    assert derive_population_status(sample, MetricPolicy()) is MetricComputationStatus.INSUFFICIENT_EVIDENCE


def test_h4_case_e_below_policy_minimum_is_insufficient_evidence():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    sample = _sample(sample_count=3, evaluated_count=3, missing_count=0)
    assert derive_population_status(sample, policy) is MetricComputationStatus.INSUFFICIENT_EVIDENCE


def test_h4_case_f_meeting_policy_minimum_is_valid():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    sample = _sample(sample_count=5, evaluated_count=5, missing_count=0)
    assert derive_population_status(sample, policy) is MetricComputationStatus.VALID


def test_h4_case_g_pf_undefined_precedence_only_applies_after_valid_population():
    # Sufficient PF population (VALID) + zero losses -> the PF-specific
    # UNDEFINED_METRIC narrowing applies; this is NOT a population-evidence
    # failure (population status is VALID, metric status is UNDEFINED_METRIC).
    policy = MetricPolicy()
    sample = _sample(sample_count=10, evaluated_count=10, missing_count=0)
    assert derive_population_status(sample, policy) is MetricComputationStatus.VALID
    pop = WinLossFlatPopulation(win_count=10, loss_count=0, flat_count=0)
    record = _pf(metric=MetricValue(status=MetricComputationStatus.UNDEFINED_METRIC), population=pop, sample=sample, metric_policy=policy)
    assert record.metric.status is MetricComputationStatus.UNDEFINED_METRIC


def test_h4_case_h_contradictory_caller_status_rejected():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    # sample=10, evaluated=10, minimum=5 -> objectively VALID; caller claims INSUFFICIENT_EVIDENCE
    with pytest.raises(MetricContractValidationError):
        require_status_consistent_with_population(
            MetricComputationStatus.INSUFFICIENT_EVIDENCE,
            _sample(sample_count=10, evaluated_count=10, missing_count=0), policy,
        )
    # sample=10, missing=10, evaluated=0 -> objectively MISSING_EVIDENCE; caller claims EMPTY_POPULATION
    with pytest.raises(MetricContractValidationError):
        require_status_consistent_with_population(
            MetricComputationStatus.EMPTY_POPULATION,
            _sample(sample_count=10, evaluated_count=0, missing_count=10), policy,
        )
    # sample=0 -> objectively EMPTY_POPULATION; caller claims MISSING_EVIDENCE
    with pytest.raises(MetricContractValidationError):
        require_status_consistent_with_population(
            MetricComputationStatus.MISSING_EVIDENCE,
            _sample(sample_count=0, evaluated_count=0, missing_count=0), policy,
        )


def test_h4_require_status_consistent_accepts_non_contradictory_status():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    require_status_consistent_with_population(MetricComputationStatus.EMPTY_POPULATION, _sample(sample_count=0, evaluated_count=0, missing_count=0), policy)
    require_status_consistent_with_population(MetricComputationStatus.MISSING_EVIDENCE, _sample(sample_count=10, evaluated_count=0, missing_count=10), policy)
    require_status_consistent_with_population(MetricComputationStatus.INSUFFICIENT_EVIDENCE, _sample(sample_count=10, evaluated_count=0, missing_count=0, excluded_count=10, exclusion_note="x"), policy)
    require_status_consistent_with_population(MetricComputationStatus.INSUFFICIENT_EVIDENCE, _sample(sample_count=3, evaluated_count=3, missing_count=0), policy)
    require_status_consistent_with_population(MetricComputationStatus.VALID, _sample(sample_count=50, evaluated_count=50, missing_count=0), policy)


def test_h4_profit_factor_record_rejects_valid_below_policy_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=100)
    pop = WinLossFlatPopulation(win_count=5, loss_count=3, flat_count=2)  # evaluated_count=10 < 100
    sample = _sample(sample_count=10, evaluated_count=10, missing_count=0)
    with pytest.raises(MetricContractValidationError):
        _pf(metric=MetricValue(status=MetricComputationStatus.VALID, value=1.0, unit=ReturnUnit.PERCENTAGE_POINTS), population=pop, sample=sample, metric_policy=policy, gross_profit=10.0, gross_loss_abs=10.0)


def test_h4_profit_factor_record_accepts_insufficient_evidence_below_policy_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=100)
    pop = WinLossFlatPopulation(win_count=5, loss_count=3, flat_count=2)  # evaluated_count=10 < 100
    sample = _sample(sample_count=10, evaluated_count=10, missing_count=0)
    record = _pf(metric=MetricValue(status=MetricComputationStatus.INSUFFICIENT_EVIDENCE), population=pop, sample=sample, metric_policy=policy)
    assert record.metric.status is MetricComputationStatus.INSUFFICIENT_EVIDENCE


def test_h4_profit_factor_record_rejects_insufficient_evidence_when_evidence_is_sufficient():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    pop = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)  # evaluated_count=92 >= 5
    sample = _sample(sample_count=92, evaluated_count=92, missing_count=0)
    with pytest.raises(MetricContractValidationError):
        _pf(metric=MetricValue(status=MetricComputationStatus.INSUFFICIENT_EVIDENCE), population=pop, sample=sample, metric_policy=policy)


def test_h4_profit_factor_record_rejects_missing_evidence_caller_status_when_population_is_missing_evidence():
    # A sample with missing evidence, but a WinLossFlatPopulation of zeros
    # (no evaluated trades) -- metric.status must be MISSING_EVIDENCE, and
    # nothing else, including a caller-supplied EMPTY_POPULATION.
    policy = MetricPolicy()
    sample = _sample(sample_count=10, evaluated_count=0, missing_count=10)
    pop = WinLossFlatPopulation(win_count=0, loss_count=0, flat_count=0)
    with pytest.raises(MetricContractValidationError):
        _pf(metric=MetricValue(status=MetricComputationStatus.EMPTY_POPULATION), population=pop, sample=sample, metric_policy=policy)
    record = _pf(metric=MetricValue(status=MetricComputationStatus.MISSING_EVIDENCE), population=pop, sample=sample, metric_policy=policy)
    assert record.metric.status is MetricComputationStatus.MISSING_EVIDENCE


def test_h4_drawdown_record_rejects_valid_below_policy_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=50, drawdown_arithmetic=DrawdownArithmetic.ADDITIVE, drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    with pytest.raises(MetricContractValidationError):
        _dd(
            metric=MetricValue(status=MetricComputationStatus.VALID, value=-1.0, unit=ReturnUnit.PERCENTAGE_POINTS),
            sample_count_in_curve=10, metric_policy=policy,
        )


def test_h4_drawdown_record_accepts_insufficient_evidence_below_policy_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=50, drawdown_arithmetic=DrawdownArithmetic.ADDITIVE, drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    record = _dd(metric=MetricValue(status=MetricComputationStatus.INSUFFICIENT_EVIDENCE), sample_count_in_curve=10, metric_policy=policy)
    assert record.metric.status is MetricComputationStatus.INSUFFICIENT_EVIDENCE


# =========================================================================
# E. All-family representability (item 18E / item 17)
# =========================================================================


FAMILIES_WITH_INDEPENDENT_COST_METRIC_SEMANTICS = {
    "Q9": dict(timing=CostTiming.NO_COST, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY),
    "Q10_SEMICONDUCTOR": dict(timing=CostTiming.ROUND_TRIP, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY),  # cost applied downstream (summarize_forward_returns), source itself GROSS_ONLY
    "Q10_INDEX": dict(timing=CostTiming.ROUND_TRIP, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED),  # shadow_comparison.py bakes total_cost into net_eod_return_pct
    "Q11": dict(timing=CostTiming.ROUND_TRIP, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED),
    "Q12": dict(timing=CostTiming.ROUND_TRIP, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED),  # vnext/hypothesis_forward both bake net_return_pct
    "OPENING_ALPHA": dict(timing=CostTiming.ALREADY_INCLUDED, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED),  # forward_30m_net/delayed_path _net() -- no separable gross at all
}

FAMILIES_WITHOUT_INDEPENDENT_SEMANTICS = ("Q13", "Q14", "Q15", "Q16", "Q17", "Q18")


@pytest.mark.parametrize("family", sorted(FAMILIES_WITH_INDEPENDENT_COST_METRIC_SEMANTICS))
def test_family_cost_return_metric_sample_representable(family):
    spec = FAMILIES_WITH_INDEPENDENT_COST_METRIC_SEMANTICS[family]
    timing = spec["timing"]
    source_cost_semantics = spec["source_cost_semantics"]

    if source_cost_semantics is SourceResultCostSemantics.GROSS_ONLY:
        # COMPUTED always carries an explicit CostPolicy for full
        # provenance -- even a genuinely zero-magnitude one (NO_COST),
        # rather than a bare None that would be ambiguous with "no cost
        # policy was ever considered at all".
        if timing is CostTiming.NO_COST:
            cost_policy = CostPolicy(timing=CostTiming.NO_COST, unit=ReturnUnit.PERCENTAGE_POINTS)
        else:
            cost_policy = CostPolicy(timing=timing, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, slippage=0.05, provenance=f"{family.lower()}_representability_fixture")
        gross_return = 1.5
        net_return = gross_return - cost_policy.total_cost
        record = NetReturnRecord(
            gross_return=gross_return, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=source_cost_semantics,
            computation_status=NetReturnComputationStatus.COMPUTED, cost_policy=cost_policy,
            net_return=net_return, win_loss_flat=WinLossFlat.WIN,
        )
    else:
        # SOURCE_PROVIDED never carries an explicit CostPolicy -- the
        # source's own figure (ROUND_TRIP baked in, or ALREADY_INCLUDED
        # with no separable magnitude) is used as-is, no re-application.
        record = NetReturnRecord(
            gross_return=None, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            computation_status=NetReturnComputationStatus.SOURCE_PROVIDED, net_return=1.22, win_loss_flat=WinLossFlat.WIN,
        )

    sample = _sample(sample_count=100, evaluated_count=92, missing_count=8, horizon_label="+30m")
    breakdown = WinLossFlatPopulation(win_count=50, loss_count=30, flat_count=12)
    require_consistent_population(sample, breakdown)

    assert record.net_return is not None
    assert record.to_dict()  # serializable


def test_all_12_plus_families_accounted_for():
    represented = set(FAMILIES_WITH_INDEPENDENT_COST_METRIC_SEMANTICS) | {"Q13", "Q14", "Q15", "Q16", "Q17", "Q18"}
    assert represented == {"Q9", "Q10_SEMICONDUCTOR", "Q10_INDEX", "Q11", "Q12", "Q13", "Q14", "Q15", "Q16", "Q17", "Q18", "OPENING_ALPHA"}
    assert len(represented) == 12
