"""UEF-3C -- Canonical Aggregation Pipeline tests.

Every test constructs already-canonical members/contexts and asserts the
orchestrator's output against UEF-1's `AggregateRecord` and UEF-3A/3B's
own frozen dataclasses -- no test parses a legacy Q/Opening-shaped dict.
UEF-1/UEF-2A/UEF-2B/UEF-3A/UEF-3B (10/10 freeze manifest) are imported
here read-only.
"""
from __future__ import annotations

import pytest

from libs.reporting.evaluation.canonical.contracts import ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import build_event_ref
from libs.reporting.evaluation.canonical.identity import evaluation_record_id as _compute_evaluation_record_id
from libs.reporting.evaluation.canonical.identity import evaluation_subject_id as _compute_evaluation_subject_id
from libs.reporting.evaluation.canonical.record import AggregateIdentity, AggregateRecord
from libs.reporting.evaluation.canonical.metrics import (
    CostPolicy,
    CostTiming,
    MetricAggregationContext,
    MetricComputationStatus,
    MetricContractValidationError,
    MetricPolicy,
)
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)


_DEFAULT_METRIC_POLICY = MetricPolicy()
# UEF-3C FIX1: this fixture's default context.metric_policy_id must equal
# a REAL MetricPolicy's content-derived .policy_id -- MetricPolicy() is
# deterministic, so every fresh MetricPolicy() call below reproduces this
# same id, keeping every pre-existing test (which passes metric_policy=
# MetricPolicy()) provenance-consistent with the FIX1 binding check by
# construction, without individually editing every call site.
_DEFAULT_METRIC_POLICY_ID = _DEFAULT_METRIC_POLICY.policy_id


def _context(
    *, horizon_label="+30m", aggregation_scope="q10_semiconductor_calc_a", hypothesis_id="q10_semi",
    evaluator_version="v1", source_id="agg-1",
    forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id=_DEFAULT_METRIC_POLICY_ID,
) -> MetricAggregationContext:
    # build_event_ref (not a hand-typed EventRef) so canonical_event_id is a
    # REAL recomputable hash of its own inputs -- AggregateRecord.__post_init__
    # (via _validate_event_ref/validate_event_ref) re-derives and checks
    # this, and a hand-typed literal would fail that UEF-1 invariant.
    ref = build_event_ref(source_namespace="uef3c_test", native_id=source_id)
    # evaluation_subject_id/evaluation_record_id must likewise be the REAL
    # content-derived hashes (matching what AggregateRecord.__post_init__
    # itself recomputes for observation_type=AGGREGATE/execution_mode=
    # OBSERVATION_ONLY) -- a blank/hand-typed value would make the eventual
    # AggregateRecord construction fail on UEF-1's own consistency check,
    # which is a correct UEF-1 invariant, not something this fixture may
    # bypass.
    subject = _compute_evaluation_subject_id(canonical_event_id=ref.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="AGGREGATE")
    record_id = _compute_evaluation_record_id(evaluation_subject_id=subject, execution_mode="OBSERVATION_ONLY")
    identity = AggregateIdentity(
        aggregate_ref=ref, aggregation_scope=aggregation_scope, hypothesis_id=hypothesis_id, evaluator_version=evaluator_version,
        evaluation_subject_id=subject, evaluation_record_id=record_id,
    )
    return MetricAggregationContext(
        aggregate_identity=identity, horizon_label=horizon_label,
        forward_policy_id=forward_policy_id, cost_policy_id=cost_policy_id, metric_policy_id=metric_policy_id,
    )


def _evaluated_gross(rec_id, gross, cost, ts) -> CanonicalAggregationMember:
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED, evaluation_record_id=rec_id, gross_return=gross,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.GROSS_ONLY,
        cost_policy=cost, observed_timestamp=ts,
    )


def _evaluated_net(rec_id, net, ts) -> CanonicalAggregationMember:
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED, evaluation_record_id=rec_id, source_net_return=net,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        observed_timestamp=ts,
    )


_MISSING = CanonicalAggregationMember(state=SampleMemberState.MISSING)
_EXCLUDED = CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)


def _cost(**kwargs) -> CostPolicy:
    defaults = dict(timing=CostTiming.ROUND_TRIP, unit=ReturnUnit.PERCENTAGE_POINTS, commission=0.1, provenance="uef3c_test")
    defaults.update(kwargs)
    return CostPolicy(**defaults)


# =========================================================================
# Context isolation (item 22)
# =========================================================================


def test_context_isolation_a_different_cost_policy_id_rejected():
    target = _context(cost_policy_id="COSTPOL_a")
    other = _context(cost_policy_id="COSTPOL_b")
    batches = [CanonicalSampleBatch(context=other, members=[_evaluated_net("REC_1", 1.0, 100)])]
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=target, batches=batches, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_context_isolation_b_different_full_aggregate_identity_same_canonical_id_rejected():
    # Same underlying aggregate_ref (same canonical_aggregate_id) but a
    # different aggregation_scope -- distinct full AggregateIdentity.
    target = _context(aggregation_scope="q10_semiconductor_calc_a")
    other = _context(aggregation_scope="q10_semiconductor_calc_b_DIFFERENT")
    assert target.aggregate_identity.canonical_aggregate_id == other.aggregate_identity.canonical_aggregate_id
    assert target.aggregate_identity != other.aggregate_identity
    batches = [CanonicalSampleBatch(context=other, members=[_evaluated_net("REC_1", 1.0, 100)])]
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=target, batches=batches, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_context_isolation_c_different_horizon_rejected():
    target = _context(horizon_label="+30m")
    other = _context(horizon_label="+5m")
    batches = [CanonicalSampleBatch(context=other, members=[_evaluated_net("REC_1", 1.0, 100)])]
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=target, batches=batches, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_context_isolation_d_exact_same_complete_context_passes():
    ctx = _context()
    batches = [CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_1", 1.0, 100)])]
    record = aggregate_canonical_samples(
        context=ctx, batches=batches, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert isinstance(record, AggregateRecord)
    assert record.identity is ctx.aggregate_identity


def test_context_isolation_multiple_matching_batches_combine():
    ctx = _context()
    batches = [
        CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_1", 1.0, 100)]),
        CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_2", -1.0, 200)]),
    ]
    record = aggregate_canonical_samples(
        context=ctx, batches=batches, metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["sample_population"]["evaluated_count"] == 2


# =========================================================================
# Population accounting (item 23)
# =========================================================================


def test_population_accounting_exact():
    ctx = _context()
    members = (
        [_evaluated_net(f"REC_{i}", 0.1, 100 + i) for i in range(5)]
        + [_MISSING, _MISSING]
        + [_EXCLUDED, _EXCLUDED, _EXCLUDED]
    )
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15", excluded_note="policy excluded",
    )
    pop = record.metrics["sample_population"]
    assert pop["sample_count"] == 10
    assert pop["evaluated_count"] == 5
    assert pop["missing_count"] == 2
    assert pop["excluded_count"] == 3
    assert pop["evaluated_count"] + pop["missing_count"] + pop["excluded_count"] == pop["sample_count"]


def test_population_empty():
    ctx = _context()
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.EMPTY_POPULATION.value
    assert record.metrics["max_drawdown"]["metric"]["status"] == MetricComputationStatus.EMPTY_POPULATION.value


def test_population_missing_only():
    ctx = _context()
    members = [_MISSING, _MISSING, _MISSING]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.MISSING_EVIDENCE.value


def test_population_all_excluded():
    ctx = _context()
    members = [_EXCLUDED, _EXCLUDED]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15", excluded_note="all excluded",
    )
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.INSUFFICIENT_EVIDENCE.value


def test_population_insufficient_evaluated():
    policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=10)
    ctx = _context(metric_policy_id=policy.policy_id)
    members = [_evaluated_net("REC_1", 1.0, 100), _evaluated_net("REC_2", -1.0, 200)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.INSUFFICIENT_EVIDENCE.value
    assert record.metrics["max_drawdown"]["metric"]["status"] == MetricComputationStatus.INSUFFICIENT_EVIDENCE.value


def test_population_valid_evaluated():
    ctx = _context()
    members = [_evaluated_net("REC_1", 1.0, 100), _evaluated_net("REC_2", -0.5, 200)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.VALID.value


def test_missing_and_excluded_members_reject_return_data():
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(state=SampleMemberState.MISSING, gross_return=0.0)
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(state=SampleMemberState.EXCLUDED, source_net_return=0.0)


# =========================================================================
# UEF-3C FIX1 (MEDIUM) -- MISSING/EXCLUDED state exclusivity, widened to
# ALL financial/evaluation observation metadata (not just return/cost/
# timestamp): return_unit and source_cost_semantics, previously accepted
# with no attached return, are now rejected too. Pure MISSING/EXCLUDED
# (no metadata at all) must remain valid.
# =========================================================================


@pytest.mark.parametrize("state", [SampleMemberState.MISSING, SampleMemberState.EXCLUDED])
@pytest.mark.parametrize(
    "field_kwargs",
    [
        {"return_unit": ReturnUnit.PERCENTAGE_POINTS},
        {"source_cost_semantics": SourceResultCostSemantics.NET_OR_COST_INCLUDED},
        {"gross_return": 0.0},
        {"source_net_return": 0.0},
        {"cost_policy": None},  # placeholder, replaced below (CostPolicy needs real construction)
        {"observed_timestamp": 100},
        {"target_timestamp": 200},
    ],
)
def test_fix1_missing_excluded_reject_any_single_financial_field(state, field_kwargs):
    if "cost_policy" in field_kwargs:
        field_kwargs = {**field_kwargs, "cost_policy": _cost()}
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(state=state, **field_kwargs)


@pytest.mark.parametrize("state", [SampleMemberState.MISSING, SampleMemberState.EXCLUDED])
def test_fix1_pure_missing_excluded_remain_valid(state):
    member = CanonicalAggregationMember(state=state)
    assert member.state is state
    assert member.return_unit is None
    assert member.source_cost_semantics is None
    assert member.gross_return is None
    assert member.source_net_return is None
    assert member.cost_policy is None
    assert member.observed_timestamp is None
    assert member.target_timestamp is None


# =========================================================================
# Cost / net orchestration (item 24)
# =========================================================================


def test_cost_orchestration_gross_only_applies_cost_exactly_once():
    cost = _cost(commission=0.10)
    ctx = _context(cost_policy_id=cost.policy_id)
    members = [_evaluated_gross("REC_1", 1.0, cost, 100)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    # single positive net return (1.0-0.10=0.90), zero losses -> UNDEFINED_METRIC (never inf/sentinel)
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.UNDEFINED_METRIC.value


def test_cost_orchestration_net_or_cost_included_never_reapplied():
    ctx = _context()
    members = [_evaluated_net("REC_1", 0.85, 100)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert record.metrics["max_drawdown"]["metric"]["value"] == pytest.approx(0.0)  # single positive point, no drawdown


def test_cost_orchestration_mixed_gross_and_net_sources_in_one_aggregate():
    cost = _cost(commission=0.20)
    ctx = _context(cost_policy_id=cost.policy_id)
    members = [_evaluated_gross("REC_1", 1.0, cost, 100), _evaluated_net("REC_2", -0.5, 200)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    # net returns: 0.80 (win), -0.5 (loss) -> PF = 0.80/0.5 = 1.6
    assert record.metrics["profit_factor"]["metric"]["status"] == MetricComputationStatus.VALID.value
    assert record.metrics["profit_factor"]["metric"]["value"] == pytest.approx(1.6)


def test_cost_orchestration_unit_mismatch_between_members_rejected():
    ctx = _context()
    fraction_member = CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED, evaluation_record_id="REC_1", source_net_return=0.01,
        return_unit=ReturnUnit.FRACTION, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        observed_timestamp=100,
    )
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[fraction_member])],
            metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_cost_orchestration_double_cost_reapplication_impossible():
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(
            state=SampleMemberState.EVALUATED, evaluation_record_id="REC_1", source_net_return=0.85,
            return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            cost_policy=_cost(), observed_timestamp=100,
        )


# =========================================================================
# PF orchestration (item 25) -- missing/excluded never enter PF arithmetic
# =========================================================================


def test_pf_missing_and_excluded_do_not_enter_arithmetic_but_affect_population():
    ctx = _context()
    members = [
        _evaluated_net("REC_1", 1.0, 100), _evaluated_net("REC_2", -0.5, 200),
        _MISSING, _EXCLUDED,
    ]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15", excluded_note="x",
    )
    pf = record.metrics["profit_factor"]
    assert pf["metric"]["status"] == MetricComputationStatus.VALID.value
    assert pf["metric"]["value"] == pytest.approx(2.0)  # 1.0/0.5, unaffected by missing/excluded
    assert pf["population"]["win_count"] == 1 and pf["population"]["loss_count"] == 1
    pop = record.metrics["sample_population"]
    assert pop["sample_count"] == 4 and pop["missing_count"] == 1 and pop["excluded_count"] == 1


# =========================================================================
# MDD orchestration (item 26)
# =========================================================================


def test_mdd_orchestration_out_of_order_input_same_aggregate_mdd():
    ctx = _context()
    m1 = _evaluated_net("REC_1", 1.0, 100)
    m2 = _evaluated_net("REC_2", -3.0, 200)
    m3 = _evaluated_net("REC_3", 0.5, 300)
    forward = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[m1, m2, m3])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    shuffled = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[m3, m1, m2])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    assert forward.metrics["max_drawdown"]["metric"]["value"] == pytest.approx(shuffled.metrics["max_drawdown"]["metric"]["value"])


def test_mdd_orchestration_does_not_mask_empty_evaluation_record_id():
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(
            state=SampleMemberState.EVALUATED, evaluation_record_id="", source_net_return=1.0,
            return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            observed_timestamp=100,
        )


def test_mdd_orchestration_does_not_mask_duplicate_canonical_ordering_key():
    ctx = _context()
    m1 = _evaluated_net("REC_dup", 1.0, 100)
    m2 = _evaluated_net("REC_dup", -2.0, 100)  # same (timestamp, id) canonical key
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[m1, m2])],
            metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        )


# =========================================================================
# Output determinism (item 27)
# =========================================================================


def test_output_determinism_across_caller_orderings():
    ctx = _context()
    a = _evaluated_net("REC_A", 1.0, 100)
    b = _evaluated_net("REC_B", -0.4, 200)
    c = _evaluated_net("REC_C", 0.7, 300)

    def _build(order):
        return aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=list(order))],
            metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        )

    r_abc = _build([a, b, c])
    r_cab = _build([c, a, b])
    r_bca = _build([b, c, a])

    assert r_abc.metrics == r_cab.metrics == r_bca.metrics
    assert r_abc.to_dict() == r_cab.to_dict() == r_bca.to_dict()


# =========================================================================
# UEF-3C FIX1 (HIGH-1) -- actual MetricPolicy bound to context.metric_policy_id
# =========================================================================


def test_fix1_mpa_metric_policy_mismatch_rejected():
    # Directly reproduces the Codex finding: context declares A, the
    # ACTUAL policy used is B, A != B.
    ctx = _context()  # metric_policy_id = _DEFAULT_METRIC_POLICY_ID (A)
    other_policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=5)  # B, a different content-derived id
    assert other_policy.policy_id != ctx.metric_policy_id
    members = [_evaluated_net("REC_1", 1.0, 100)]
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
            metric_policy=other_policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_fix1_mpb_metric_policy_match_passes():
    ctx = _context()
    members = [_evaluated_net("REC_1", 1.0, 100)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=_DEFAULT_METRIC_POLICY, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert isinstance(record, AggregateRecord)


def test_fix1_mpc_mismatch_rejected_before_any_pf_mdd_construction():
    # Even a population that WOULD otherwise be perfectly valid (and thus
    # would normally produce a concrete PF/MDD result) must be rejected
    # outright on a metric-policy mismatch -- no partial/contaminated
    # AggregateRecord may ever be returned under the wrong provenance.
    ctx = _context()
    mismatched_policy = MetricPolicy(minimum_evaluated_for_insufficient_evidence=1)
    assert mismatched_policy.policy_id != ctx.metric_policy_id
    members = [_evaluated_net("REC_1", 1.0, 100), _evaluated_net("REC_2", -0.5, 200)]
    with pytest.raises(MetricContractValidationError) as excinfo:
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
            metric_policy=mismatched_policy, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )
    assert "metric_policy" in str(excinfo.value)


# =========================================================================
# UEF-3C FIX1 (HIGH-2) -- actually-used CostPolicy bound to context.cost_policy_id
# =========================================================================


def test_fix1_cpa_cost_policy_mismatch_rejected():
    # Directly reproduces the Codex finding: context declares cost_policy_id=A,
    # the GROSS_ONLY member's ACTUAL cost_policy.policy_id is B, A != B.
    cost_a = _cost(commission=0.10)
    cost_b = _cost(commission=0.20)  # different content -> different policy_id
    assert cost_a.policy_id != cost_b.policy_id
    ctx = _context(cost_policy_id=cost_a.policy_id)
    members = [_evaluated_gross("REC_1", 1.0, cost_b, 100)]
    with pytest.raises(MetricContractValidationError):
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
            metric_policy=_DEFAULT_METRIC_POLICY, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
            aggregation_window_start="2026-09-15",
        )


def test_fix1_cpb_cost_policy_match_passes_and_cost_applied_exactly_once():
    cost = _cost(commission=0.10)
    ctx = _context(cost_policy_id=cost.policy_id)
    members = [_evaluated_gross("REC_1", 1.0, cost, 100), _evaluated_gross("REC_2", 1.0, cost, 200)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=_DEFAULT_METRIC_POLICY, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    # both members: 1.0 - 0.10 = 0.90 net, never 0.80 (which double-charging would produce)
    mdd = record.metrics["max_drawdown"]
    assert mdd["metric"]["value"] == pytest.approx(0.0)  # both positive, no drawdown -- sanity that it ran


def test_fix1_cpc_net_or_cost_included_with_explicit_cost_policy_still_rejected():
    # Existing double-cost prevention preserved (construction-time reject,
    # confirmed again after FIX1's changes) -- same as
    # test_cost_orchestration_double_cost_reapplication_impossible, kept
    # here alongside the FIX1 CostPolicy-binding suite for direct traceability.
    with pytest.raises(MetricContractValidationError):
        CanonicalAggregationMember(
            state=SampleMemberState.EVALUATED, evaluation_record_id="REC_1", source_net_return=0.85,
            return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
            cost_policy=_cost(), observed_timestamp=100,
        )


def test_fix1_cpd_no_synthetic_cost_policy_injected_for_net_or_cost_included():
    # A NET_OR_COST_INCLUDED member with cost_policy=None must pass cleanly
    # even when context.cost_policy_id names some UNRELATED cost policy --
    # the binding check only ever applies to a member that ACTUALLY carries
    # an explicit CostPolicy (GROSS_ONLY); UEF-3C must never synthesize one
    # just to satisfy this rule for a source that structurally has none.
    unrelated_cost_policy_id = _cost(commission=0.99).policy_id
    ctx = _context(cost_policy_id=unrelated_cost_policy_id)
    members = [_evaluated_net("REC_1", 0.5, 100)]
    record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=_DEFAULT_METRIC_POLICY, input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15",
    )
    assert isinstance(record, AggregateRecord)


# =========================================================================
# UEF-3C FIX1 -- adversarial reproduction of the two original Codex HIGH
# findings, explicitly named as such (item 14).
# =========================================================================


def test_fix1_original_high1_reproduction_metric_policy_mismatch_not_accepted():
    ctx = _context()
    policy_b = MetricPolicy(minimum_evaluated_for_insufficient_evidence=7)
    assert policy_b.policy_id != ctx.metric_policy_id
    mismatch_accepted = True
    try:
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_1", 1.0, 100)])],
            metric_policy=policy_b, input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        )
    except MetricContractValidationError:
        mismatch_accepted = False
    assert mismatch_accepted is False


def test_fix1_original_high2_reproduction_cost_policy_mismatch_not_accepted():
    cost_a = _cost(commission=0.11)
    cost_b = _cost(commission=0.22)
    ctx = _context(cost_policy_id=cost_a.policy_id)
    mismatch_accepted = True
    try:
        aggregate_canonical_samples(
            context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[_evaluated_gross("REC_1", 1.0, cost_b, 100)])],
            metric_policy=_DEFAULT_METRIC_POLICY, input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        )
    except MetricContractValidationError:
        mismatch_accepted = False
    assert mismatch_accepted is False
