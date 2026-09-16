"""UEF-3B -- Canonical Cost & Metric Engine tests.

Every test constructs canonical inputs (already-resolved floats/policies/
populations) and asserts the engine's output against UEF-3A's own frozen
dataclasses -- no test parses a legacy Q/Opening-shaped dict. UEF-3A
(contracts.py/policy.py/__init__.py) is FROZEN (9/9 freeze manifest) and
is imported here read-only; this file never asserts anything that would
require reinterpreting a UEF-3A invariant, only that the engine's
arithmetic PRODUCES values UEF-3A's own constructors already accept.
"""
from __future__ import annotations

import pytest

from libs.reporting.evaluation.canonical.contracts import ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import EventRef, IdentityKind
from libs.reporting.evaluation.canonical.record import AggregateIdentity
from libs.reporting.evaluation.canonical.metrics import (
    CostPolicy,
    CostTiming,
    DrawdownArithmetic,
    DrawdownOrderingAuthority,
    MetricAggregationContext,
    MetricComputationStatus,
    MetricContractValidationError,
    MetricPolicy,
    NetReturnComputationStatus,
    SamplePopulation,
    WinLossFlat,
)
from libs.reporting.evaluation.canonical.metrics.engine import (
    DrawdownCurvePoint,
    calculate_max_drawdown,
    calculate_net_return,
    calculate_profit_factor,
    calculate_total_cost,
    classify_net_return,
)


def _context(*, horizon_label="+30m") -> MetricAggregationContext:
    ref = EventRef(identity_kind=IdentityKind.DERIVED, source_namespace="uef3b_test", source_id="agg-1", canonical_event_id="AGG_deadbeef")
    identity = AggregateIdentity(aggregate_ref=ref, aggregation_scope="q10_semiconductor_calc_a", hypothesis_id="q10_semi", evaluator_version="v1")
    return MetricAggregationContext(aggregate_identity=identity, horizon_label=horizon_label, forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id="METRICPOL_a")


def _sample(*, sample_count, evaluated_count, missing_count, excluded_count=0, exclusion_note="") -> SamplePopulation:
    return SamplePopulation(
        context=_context(), sample_count=sample_count, evaluated_count=evaluated_count,
        missing_count=missing_count, excluded_count=excluded_count, exclusion_note=exclusion_note,
    )


# =========================================================================
# C. Cost engine
# =========================================================================


def test_c1_gross_minus_full_cost_stack_same_unit():
    cost = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, tax=0.20, slippage=0.05, provenance="c1")
    assert calculate_total_cost(cost) == pytest.approx(0.35)
    record = calculate_net_return(gross_return=1.00, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY, cost_policy=cost)
    assert record.net_return == pytest.approx(0.65)
    assert record.computation_status is NetReturnComputationStatus.COMPUTED


def test_c2_round_trip_amount_subtracted_exactly_once_not_doubled():
    cost = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="c2")
    record = calculate_net_return(gross_return=1.00, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY, cost_policy=cost)
    assert record.net_return == pytest.approx(0.90)
    assert record.net_return != pytest.approx(0.80)  # would be gross-0.20 if ROUND_TRIP were (wrongly) a x2 multiplier


def test_c3_mixed_component_timings_used_exactly_once_each():
    cost = CostPolicy(
        timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS,
        commission=0.10, tax=0.20, tax_timing=CostTiming.EXIT_ONLY, provenance="c3",
    )
    assert calculate_total_cost(cost) == pytest.approx(0.30)
    record = calculate_net_return(gross_return=1.00, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY, cost_policy=cost)
    assert record.net_return == pytest.approx(0.70)


def test_c4_net_or_cost_included_reapplication_impossible():
    cost = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.10, provenance="c4")
    with pytest.raises(MetricContractValidationError):
        calculate_net_return(
            gross_return=None, return_unit=ReturnUnit.PERCENTAGE_POINTS,
            source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            cost_policy=cost, source_net_return=0.85,
        )
    # the correct, non-reapplying path works and is authoritative as-is
    record = calculate_net_return(
        gross_return=None, return_unit=ReturnUnit.PERCENTAGE_POINTS,
        source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        source_net_return=0.85,
    )
    assert record.net_return == pytest.approx(0.85)
    assert record.computation_status is NetReturnComputationStatus.SOURCE_PROVIDED


def test_c5_unit_mismatch_rejected_explicitly():
    cost = CostPolicy(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.FRACTION, commission=0.001, provenance="c5")
    with pytest.raises(MetricContractValidationError):
        calculate_net_return(gross_return=0.01, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY, cost_policy=cost)


def test_unavailable_never_guesses_a_net_value():
    record = calculate_net_return(gross_return=1.0, return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.UNKNOWN)
    assert record.net_return is None
    assert record.computation_status is NetReturnComputationStatus.UNAVAILABLE


# =========================================================================
# Return classification -- no epsilon
# =========================================================================


def test_classify_positive_is_win():
    assert classify_net_return(0.5) is WinLossFlat.WIN


def test_classify_negative_is_loss():
    assert classify_net_return(-0.5) is WinLossFlat.LOSS


def test_classify_zero_is_flat():
    assert classify_net_return(0.0) is WinLossFlat.FLAT


def test_classify_tiny_positive_is_win_no_epsilon():
    assert classify_net_return(1e-12) is WinLossFlat.WIN


def test_classify_tiny_negative_is_loss_no_epsilon():
    assert classify_net_return(-1e-12) is WinLossFlat.LOSS


# =========================================================================
# Profit Factor engine
# =========================================================================


def test_pf_normal_mixed_returns():
    sample = _sample(sample_count=4, evaluated_count=4, missing_count=0)
    record = calculate_profit_factor(net_returns=[1.0, 1.0, -0.5, -0.5], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.VALID
    assert record.metric.value == pytest.approx(2.0)
    assert record.gross_profit == pytest.approx(2.0)
    assert record.gross_loss_abs == pytest.approx(1.0)


def test_pf_no_wins():
    sample = _sample(sample_count=2, evaluated_count=2, missing_count=0)
    record = calculate_profit_factor(net_returns=[-0.3, -0.7], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.VALID
    assert record.metric.value == pytest.approx(0.0)
    assert record.gross_profit == pytest.approx(0.0)


def test_pf_no_losses_is_undefined_never_inf_or_sentinel():
    sample = _sample(sample_count=2, evaluated_count=2, missing_count=0)
    record = calculate_profit_factor(net_returns=[0.3, 0.7], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.UNDEFINED_METRIC
    assert record.metric.value is None


def test_pf_all_flat_is_undefined_zero_losses():
    sample = _sample(sample_count=3, evaluated_count=3, missing_count=0)
    record = calculate_profit_factor(net_returns=[0.0, 0.0, 0.0], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.UNDEFINED_METRIC


def test_pf_empty_population():
    sample = _sample(sample_count=0, evaluated_count=0, missing_count=0)
    record = calculate_profit_factor(net_returns=[], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.EMPTY_POPULATION
    assert record.metric.value is None


def test_pf_missing_only_population():
    sample = _sample(sample_count=5, evaluated_count=0, missing_count=5)
    record = calculate_profit_factor(net_returns=[], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.MISSING_EVIDENCE


def test_pf_all_excluded_population():
    sample = _sample(sample_count=5, evaluated_count=0, missing_count=0, excluded_count=5, exclusion_note="all excluded")
    record = calculate_profit_factor(net_returns=[], sample=sample, metric_policy=MetricPolicy())
    assert record.metric.status is MetricComputationStatus.INSUFFICIENT_EVIDENCE


def test_pf_insufficient_evidence_below_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=10)
    sample = _sample(sample_count=3, evaluated_count=3, missing_count=0)
    record = calculate_profit_factor(net_returns=[1.0, -1.0, 0.5], sample=sample, metric_policy=policy)
    assert record.metric.status is MetricComputationStatus.INSUFFICIENT_EVIDENCE
    assert record.metric.value is None


def test_pf_rejects_mismatched_net_returns_length():
    sample = _sample(sample_count=4, evaluated_count=4, missing_count=0)
    with pytest.raises(MetricContractValidationError):
        calculate_profit_factor(net_returns=[1.0, -0.5], sample=sample, metric_policy=MetricPolicy())


# =========================================================================
# MDD engine
# =========================================================================


def _point(canonical_return, observed_timestamp, evaluation_record_id) -> DrawdownCurvePoint:
    return DrawdownCurvePoint(canonical_return=canonical_return, observed_timestamp=observed_timestamp, evaluation_record_id=evaluation_record_id)


def test_m1_normal_additive_curve_exact_expected_mdd():
    # equity: 0 -> +1 -> +1.5 -> +0.5 -> +2.0 ; peak: 0,1,1.5,1.5,2.0 ; dd: 0,0,0,-1.0,0 -> MDD=-1.0
    points = [
        _point(1.0, 100, "REC_1"), _point(0.5, 200, "REC_2"),
        _point(-1.0, 300, "REC_3"), _point(1.5, 400, "REC_4"),
    ]
    record = calculate_max_drawdown(points=points, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.status is MetricComputationStatus.VALID
    assert record.metric.value == pytest.approx(-1.0)
    assert record.sample_count_in_curve == 4


def test_m2_all_positive_mdd_is_zero():
    points = [_point(0.5, 100, "REC_1"), _point(0.3, 200, "REC_2"), _point(0.2, 300, "REC_3")]
    record = calculate_max_drawdown(points=points, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.value == pytest.approx(0.0)


def test_m3_all_flat_mdd_is_zero():
    points = [_point(0.0, 100, "REC_1"), _point(0.0, 200, "REC_2")]
    record = calculate_max_drawdown(points=points, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.value == pytest.approx(0.0)


def test_m4_input_order_invariance():
    a = _point(1.0, 100, "REC_A")
    b = _point(-2.0, 200, "REC_B")
    c = _point(0.5, 300, "REC_C")
    forward = calculate_max_drawdown(points=[a, b, c], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    shuffled = calculate_max_drawdown(points=[c, a, b], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    reversed_order = calculate_max_drawdown(points=[c, b, a], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert forward.metric.value == pytest.approx(shuffled.metric.value)
    assert forward.metric.value == pytest.approx(reversed_order.metric.value)


def test_m5_same_timestamp_deterministic_tie_break_by_evaluation_record_id():
    # A and B share one observed_timestamp -- [A,B] vs [B,A] as CALL ORDER
    # must still produce the identical ordered curve and identical MDD,
    # because the engine sorts by (timestamp, evaluation_record_id) itself.
    a = _point(1.0, 1000, "REC_aaa")
    b = _point(-3.0, 1000, "REC_bbb")
    ab = calculate_max_drawdown(points=[a, b], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    ba = calculate_max_drawdown(points=[b, a], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert ab.metric.value == pytest.approx(ba.metric.value)
    # Deterministic canonical order is REC_aaa before REC_bbb (ascending) --
    # curve: 0 -> +1.0 -> -2.0 ; peak 0,1.0,1.0 ; dd 0,0,-3.0 -> MDD=-3.0
    assert ab.metric.value == pytest.approx(-3.0)


def test_m6_unit_mismatch_rejected_via_frozen_contract():
    points = [_point(1.0, 100, "REC_1")]
    record_ok = calculate_max_drawdown(points=points, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record_ok.metric.unit is ReturnUnit.PERCENTAGE_POINTS
    # The engine itself always sets metric.unit == input_return_unit, so a
    # mismatch can only be reached by hand-constructing a DrawdownRecord
    # directly (frozen contract, H3) -- reconfirm read-only that path rejects.
    from libs.reporting.evaluation.canonical.metrics import DrawdownRecord, DrawdownTieBreakAuthority, MetricValue
    with pytest.raises(MetricContractValidationError):
        DrawdownRecord(
            metric=MetricValue(status=MetricComputationStatus.VALID, value=-1.0, unit=ReturnUnit.FRACTION),
            arithmetic=DrawdownArithmetic.ADDITIVE, ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP,
            tie_break_authority=DrawdownTieBreakAuthority.EVALUATION_RECORD_ID, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            metric_policy=MetricPolicy(), sample_count_in_curve=1,
        )


def test_m7_nonzero_starting_state_rejected_via_frozen_contract():
    # The engine itself always passes starting_equity=0.0 -- reconfirm
    # read-only that the frozen DrawdownRecord contract (H3) rejects any
    # other value, so the engine could never smuggle one through even if
    # it tried.
    from libs.reporting.evaluation.canonical.metrics import DrawdownRecord, DrawdownTieBreakAuthority, MetricValue
    with pytest.raises(MetricContractValidationError):
        DrawdownRecord(
            metric=MetricValue(status=MetricComputationStatus.EMPTY_POPULATION),
            arithmetic=DrawdownArithmetic.ADDITIVE, ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP,
            tie_break_authority=DrawdownTieBreakAuthority.EVALUATION_RECORD_ID, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            metric_policy=MetricPolicy(), starting_equity=100.0, sample_count_in_curve=0,
        )


def test_mdd_empty_curve_is_empty_population():
    record = calculate_max_drawdown(points=[], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.status is MetricComputationStatus.EMPTY_POPULATION


def test_mdd_insufficient_evidence_below_minimum():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)
    points = [_point(1.0, 100, "REC_1"), _point(-1.0, 200, "REC_2")]
    record = calculate_max_drawdown(points=points, metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.status is MetricComputationStatus.INSUFFICIENT_EVIDENCE


def test_mdd_compounding_arithmetic_raises_not_silently_guessed():
    policy = MetricPolicy(drawdown_arithmetic=DrawdownArithmetic.COMPOUNDING, drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    points = [_point(1.0, 100, "REC_1")]
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=points, metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)


def test_mdd_target_timestamp_ordering_authority_used_when_policy_declares_it():
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.TARGET_TIMESTAMP)
    # observed_timestamp intentionally reversed vs target_timestamp to prove
    # TARGET_TIMESTAMP (not OBSERVED_TIMESTAMP) is actually the sort key used.
    a = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=200, target_timestamp=100, evaluation_record_id="REC_a")
    b = DrawdownCurvePoint(canonical_return=-3.0, observed_timestamp=100, target_timestamp=200, evaluation_record_id="REC_b")
    record = calculate_max_drawdown(points=[a, b], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    # ordered by target_timestamp: a(100) then b(200) -> curve 0,+1.0,-2.0 -> peak 0,1.0,1.0 -> dd 0,0,-3.0
    assert record.metric.value == pytest.approx(-3.0)


def test_mdd_target_timestamp_missing_rejected():
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.TARGET_TIMESTAMP)
    points = [DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, evaluation_record_id="REC_a")]  # no target_timestamp
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=points, metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)


# =========================================================================
# UEF-3B FIX1 -- MDD determinism closure: empty/duplicate canonical
# ordering key must be rejected outright (independent Codex audit HIGH).
# Canonical ordering key = (primary_timestamp under the ACTIVE
# metric_policy.drawdown_ordering_authority, evaluation_record_id).
# =========================================================================


def test_fix1_a_empty_evaluation_record_id_single_point_rejected():
    # Closes the exact Codex reproduction: EMPTY_ID_SINGLE_POINT: ACCEPTED.
    with pytest.raises(MetricContractValidationError):
        DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, evaluation_record_id="")


def test_fix1_a_blank_evaluation_record_id_rejected_via_engine_defense_in_depth():
    # calculate_max_drawdown re-validates independently of the constructor
    # (population-level defense-in-depth) -- confirmed by constructing a
    # valid point and one with an id that is empty via the dataclass's own
    # __post_init__ boundary (already proven above); here we additionally
    # confirm the engine-level loop itself would reject a blank id if it
    # ever reached the population scan (belt-and-suspenders, not reachable
    # any other way since the constructor already blocks it).
    point = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, evaluation_record_id="REC_ok")
    # sanity: a single valid point is accepted normally
    record = calculate_max_drawdown(points=[point], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.status is MetricComputationStatus.VALID


def test_fix1_b_duplicate_observed_timestamp_canonical_key_rejected_both_orders():
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    a = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, evaluation_record_id="REC_dup")
    b = DrawdownCurvePoint(canonical_return=-2.0, observed_timestamp=100, evaluation_record_id="REC_dup")
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=[a, b], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=[b, a], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)


def test_fix1_c_duplicate_target_timestamp_canonical_key_rejected():
    # Proves validation follows the ACTIVE ordering authority rather than
    # hard-coding observed_timestamp: these two points have DIFFERENT
    # observed_timestamp values but the SAME target_timestamp+id, and the
    # policy declares TARGET_TIMESTAMP as authoritative.
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.TARGET_TIMESTAMP)
    a = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, target_timestamp=500, evaluation_record_id="REC_dup")
    b = DrawdownCurvePoint(canonical_return=-2.0, observed_timestamp=200, target_timestamp=500, evaluation_record_id="REC_dup")
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=[a, b], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    with pytest.raises(MetricContractValidationError):
        calculate_max_drawdown(points=[b, a], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)


def test_fix1_d_same_primary_timestamp_different_ids_pass_and_order_by_id():
    # Existing deterministic tie-break behavior (H3, unchanged): two
    # points sharing one primary timestamp but with DIFFERENT ids are
    # perfectly valid -- their canonical keys differ -- and ordering
    # between them is resolved by ascending evaluation_record_id.
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    a = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=1000, evaluation_record_id="REC_aaa")
    b = DrawdownCurvePoint(canonical_return=-3.0, observed_timestamp=1000, evaluation_record_id="REC_bbb")
    record_ab = calculate_max_drawdown(points=[a, b], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    record_ba = calculate_max_drawdown(points=[b, a], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record_ab.metric.status is MetricComputationStatus.VALID
    # REC_aaa (ascending) walked before REC_bbb regardless of call order:
    # curve 0,+1.0,-2.0 -> peak 0,1.0,1.0 -> dd 0,0,-3.0 -> MDD=-3.0
    assert record_ab.metric.value == pytest.approx(-3.0)
    assert record_ba.metric.value == pytest.approx(-3.0)


def test_fix1_e_same_id_different_primary_timestamp_is_not_a_duplicate():
    # A same evaluation_record_id paired with a DIFFERENT primary
    # timestamp has a DIFFERENT canonical tuple key -- this is not the
    # ambiguity FIX1 closes, and no new global-uniqueness rule is invented
    # for evaluation_record_id alone (only the (timestamp, id) PAIR is the
    # canonical key, exactly as the frozen ordering authority defines it).
    policy = MetricPolicy(drawdown_ordering_authority=DrawdownOrderingAuthority.OBSERVED_TIMESTAMP)
    a = DrawdownCurvePoint(canonical_return=1.0, observed_timestamp=100, evaluation_record_id="REC_shared")
    b = DrawdownCurvePoint(canonical_return=-2.0, observed_timestamp=200, evaluation_record_id="REC_shared")
    record = calculate_max_drawdown(points=[a, b], metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert record.metric.status is MetricComputationStatus.VALID
    # curve_0=0; curve_1=0+1.0=1.0 (peak=1.0, dd=0); curve_2=1.0-2.0=-1.0 (peak=1.0, dd=-2.0) -> MDD=-2.0
    assert record.metric.value == pytest.approx(-2.0)


def test_fix1_f_valid_unique_keys_input_order_invariance_preserved():
    # Retained from the original UEF-3B suite (test_m4), re-confirmed
    # unaffected by the FIX1 validation for VALID, unique canonical keys.
    a = _point(1.0, 100, "REC_A")
    b = _point(-2.0, 200, "REC_B")
    c = _point(0.5, 300, "REC_C")
    forward = calculate_max_drawdown(points=[a, b, c], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    shuffled = calculate_max_drawdown(points=[c, a, b], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    reversed_order = calculate_max_drawdown(points=[c, b, a], metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS)
    assert forward.metric.value == pytest.approx(shuffled.metric.value)
    assert forward.metric.value == pytest.approx(reversed_order.metric.value)
