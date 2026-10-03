"""UEF-6B Direct Evidence Lineage Sidecar tests.

Every test constructs already-canonical members/contexts via the SAME
proven fixture pattern as ``tests/test_uef3c_aggregation_pipeline.py``
(the frozen UEF-3C aggregation pipeline's own test suite) -- no test
parses a legacy Q/Opening-shaped dict, no test reimplements PF/MDD math.
"""

from __future__ import annotations

import inspect

import pytest

from libs.reporting.evaluation.canonical.contracts import ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import build_event_ref
from libs.reporting.evaluation.canonical.identity import evaluation_record_id as _compute_evaluation_record_id
from libs.reporting.evaluation.canonical.identity import evaluation_subject_id as _compute_evaluation_subject_id
from libs.reporting.evaluation.canonical.record import AggregateIdentity, EpisodeRecord, build_episode_record
from libs.reporting.evaluation.canonical.metrics import MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    CanonicalSampleBatch,
    SampleMemberState,
    aggregate_canonical_samples,
)

from libs.reporting.evaluation.uef6.lineage_model import (
    DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE,
    UEF6LineagePopulationMismatchError,
)
from libs.reporting.evaluation.uef6.lineage_verify import verify_witness_against_episode_population
from libs.reporting.evaluation.uef6.lineage_witness import (
    aggregate_canonical_samples_with_lineage,
    lineage_status_without_direct_witness,
)
from libs.reporting.evaluation.uef6.population_dedup import UEF6IdentityContentCollisionError


_DEFAULT_METRIC_POLICY = MetricPolicy()
_DEFAULT_METRIC_POLICY_ID = _DEFAULT_METRIC_POLICY.policy_id


def _context(
    *, horizon_label="+30m", aggregation_scope="uef6b_test_scope", hypothesis_id="q10_semi",
    evaluator_version="v1", source_id="agg-1",
    forward_policy_id="FWDPOL_a", cost_policy_id="COSTPOL_a", metric_policy_id=_DEFAULT_METRIC_POLICY_ID,
) -> MetricAggregationContext:
    ref = build_event_ref(source_namespace="uef6b_test", native_id=source_id)
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


def _evaluated_net(rec_id, net, ts) -> CanonicalAggregationMember:
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED, evaluation_record_id=rec_id, source_net_return=net,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        observed_timestamp=ts,
    )


_MISSING = CanonicalAggregationMember(state=SampleMemberState.MISSING)
_EXCLUDED = CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)


def _episode(native_id, hypothesis_id="q10_semi", execution_mode=ExecutionMode.OBSERVATION_ONLY) -> EpisodeRecord:
    return build_episode_record(
        source_namespace="uef6b_test_episode", hypothesis_id=hypothesis_id, observation_type=ObservationType.CANDIDATE,
        execution_mode=execution_mode, trading_date="2026-01-01", symbol="005930", native_id=native_id,
    )


def _run(ctx, members, excluded_note=""):
    return aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS,
        aggregation_window_start="2026-09-15", excluded_note=excluded_note,
    )


# ---------------------------------------------------------------------------
# A. Two evaluated members
# ---------------------------------------------------------------------------


def test_a_two_evaluated_members():
    ctx = _context()
    result = _run(ctx, [_evaluated_net("REC_A", 1.0, 100), _evaluated_net("REC_B", -0.5, 200)])
    assert result.witness.sample_count == 2
    assert result.witness.evaluated_count == 2
    pop = result.aggregate_record.metrics["sample_population"]
    assert pop["sample_count"] == result.witness.sample_count
    assert pop["evaluated_count"] == result.witness.evaluated_count
    assert result.witness.witness_id.startswith("UEF6BWITNESS_")


# ---------------------------------------------------------------------------
# B. Input order permutation
# ---------------------------------------------------------------------------


def test_b_input_order_permutation_same_witness():
    ctx = _context()
    m_a, m_b = _evaluated_net("REC_A", 1.0, 100), _evaluated_net("REC_B", -0.5, 200)
    r1 = _run(ctx, [m_a, m_b])
    r2 = _run(ctx, [m_b, m_a])
    assert r1.witness.member_multiset_digest == r2.witness.member_multiset_digest
    assert r1.witness.witness_id == r2.witness.witness_id
    assert r1.witness.to_dict() == r2.witness.to_dict()


# ---------------------------------------------------------------------------
# C. Multiplicity mutation
# ---------------------------------------------------------------------------


def test_c_multiplicity_mutation_changes_digest():
    ctx = _context()
    m_a, m_b = _evaluated_net("REC_A", 1.0, 100), _evaluated_net("REC_B", -0.5, 200)
    # The frozen UEF-3B MDD engine rejects two points sharing one exact
    # (observed_timestamp, evaluation_record_id) ordering key -- a
    # genuinely different observed_timestamp for the SAME
    # evaluation_record_id is still a real, legitimate "duplicate member
    # identity" occurrence for UEF-6B's own purposes.
    m_b_repeat = _evaluated_net("REC_B", -0.5, 201)
    r1 = _run(ctx, [m_a, m_b])
    r2 = _run(ctx, [m_a, m_b, m_b_repeat])
    assert r1.witness.member_multiset_digest != r2.witness.member_multiset_digest
    assert r1.witness.witness_id != r2.witness.witness_id
    assert r2.witness.duplicate_member_ids == ("REC_B",)
    assert r2.witness.duplicate_member_identity_count == 1
    assert r1.witness.duplicate_member_identity_count == 0


# ---------------------------------------------------------------------------
# D. Member semantic mutation
# ---------------------------------------------------------------------------


def test_d_member_semantic_mutation_changes_digest():
    ctx = _context()
    r1 = _run(ctx, [_evaluated_net("REC_A", 1.0, 100)])
    r2 = _run(ctx, [_evaluated_net("REC_A", 1.0, 999)])  # observed_timestamp changed, still valid
    assert r1.witness.member_multiset_digest != r2.witness.member_multiset_digest
    assert r1.witness.witness_id != r2.witness.witness_id


# ---------------------------------------------------------------------------
# E. Context mutation
# ---------------------------------------------------------------------------


def test_e_context_mutation_changes_context_digest():
    ctx1 = _context(horizon_label="+30m")
    ctx2 = _context(horizon_label="+5m")
    r1 = _run(ctx1, [_evaluated_net("REC_A", 1.0, 100)])
    r2 = _run(ctx2, [_evaluated_net("REC_A", 1.0, 100)])
    assert r1.witness.context_digest != r2.witness.context_digest
    assert r1.witness.witness_id != r2.witness.witness_id


# ---------------------------------------------------------------------------
# F. EVALUATED + MISSING + EXCLUDED
# ---------------------------------------------------------------------------


def test_f_evaluated_missing_excluded_population():
    ctx = _context()
    result = _run(ctx, [_evaluated_net("REC_A", 1.0, 100), _MISSING, _EXCLUDED], excluded_note="uef6b_test exclusion")
    assert result.witness.sample_count == 3
    assert result.witness.evaluated_count == 1
    assert result.witness.missing_count == 1
    assert result.witness.excluded_count == 1
    for occurrence in result.witness.member_occurrences:
        if occurrence.state != "EVALUATED":
            assert occurrence.evaluation_record_id == ""  # no fake episode ID ever invented


# ---------------------------------------------------------------------------
# G. Population count mismatch -> FAIL CLOSED
# ---------------------------------------------------------------------------


def test_g_population_count_mismatch_fails_closed():
    from libs.reporting.evaluation.uef6.lineage_witness import _build_witness, _cross_check_population

    ctx = _context()
    witness = _build_witness(ctx, [CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_A", 1.0, 100)])])

    class _FakeRecord:
        metrics = {"sample_population": {"sample_count": 2, "evaluated_count": 2, "missing_count": 0, "excluded_count": 0}}

    with pytest.raises(UEF6LineagePopulationMismatchError):
        _cross_check_population(witness, _FakeRecord())


# ---------------------------------------------------------------------------
# H. Full evaluated episode match
# ---------------------------------------------------------------------------


def test_h_full_evaluated_episode_match():
    ep_a, ep_b = _episode("EV_A"), _episode("EV_B")
    ctx = _context()
    result = _run(ctx, [
        _evaluated_net(ep_a.identity.evaluation_record_id, 1.0, 100),
        _evaluated_net(ep_b.identity.evaluation_record_id, -0.5, 200),
    ])
    verification = verify_witness_against_episode_population(result.witness, [ep_a, ep_b])
    assert verification.exact_evaluated_episode_membership_proven is True
    assert verification.evaluated_episode_missing_count == 0
    assert verification.evaluated_episode_match_count == 2


# ---------------------------------------------------------------------------
# I. Partial evaluated episode match
# ---------------------------------------------------------------------------


def test_i_partial_evaluated_episode_match():
    ep_a = _episode("EV_A")
    ctx = _context()
    result = _run(ctx, [
        _evaluated_net(ep_a.identity.evaluation_record_id, 1.0, 100),
        _evaluated_net("REC_UNKNOWN_NOT_IN_POPULATION", -0.5, 200),
    ])
    verification = verify_witness_against_episode_population(result.witness, [ep_a])
    assert verification.exact_evaluated_episode_membership_proven is False
    assert verification.evaluated_episode_missing_count == 1
    assert "REC_UNKNOWN_NOT_IN_POPULATION" in verification.missing_evaluation_record_ids


# ---------------------------------------------------------------------------
# J. Episode identity/content collision
# ---------------------------------------------------------------------------


def test_j_episode_identity_content_collision_fails_closed():
    ep = _episode("EV_A")
    mutated_payload = dict(ep.to_dict())
    mutated_payload["metadata"] = {"tampered": True}
    mutated = EpisodeRecord.from_dict(mutated_payload)
    assert mutated.identity.evaluation_record_id == ep.identity.evaluation_record_id  # same identity, different body

    ctx = _context()
    result = _run(ctx, [_evaluated_net(ep.identity.evaluation_record_id, 1.0, 100)])
    with pytest.raises(UEF6IdentityContentCollisionError):
        verify_witness_against_episode_population(result.witness, [ep, mutated])


# ---------------------------------------------------------------------------
# K. Duplicate evaluated member occurrence
# ---------------------------------------------------------------------------


def test_k_duplicate_evaluated_member_occurrence():
    ctx = _context()
    result = _run(ctx, [
        _evaluated_net("REC_A", 1.0, 100),
        _evaluated_net("REC_A", 1.0, 101),  # same identity, different observed_timestamp (frozen MDD ordering-key rule)
        _evaluated_net("REC_B", -0.5, 200),
    ])
    assert result.witness.sample_count == 3  # no collapse
    assert result.witness.identified_member_count == 3
    unique_ids = {o.evaluation_record_id for o in result.witness.member_occurrences}
    assert unique_ids == {"REC_A", "REC_B"}
    assert result.witness.duplicate_member_ids == ("REC_A",)
    assert result.witness.duplicate_member_identity_count == 1


# ---------------------------------------------------------------------------
# L. Heuristic reconstruction rejection
# ---------------------------------------------------------------------------


def test_l_heuristic_reconstruction_rejected():
    ctx = _context()
    aggregate_record = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_A", 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    # Coincidentally-matching correlating data (same hypothesis_id/day) --
    # explicitly NOT enough to prove membership.
    _matching_episode = _episode("EV_A", hypothesis_id=ctx.aggregate_identity.hypothesis_id)
    assert aggregate_record.identity.hypothesis_id == ctx.aggregate_identity.hypothesis_id  # correlation exists...

    status = lineage_status_without_direct_witness()
    assert status == DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE

    # Structural guarantee: the function accepts NO arguments at all, so it
    # cannot possibly consult aggregate_record/_matching_episode's
    # day/hypothesis/count to infer a witness.
    sig = inspect.signature(lineage_status_without_direct_witness)
    assert len(sig.parameters) == 0


# ---------------------------------------------------------------------------
# M. Frozen aggregate unchanged
# ---------------------------------------------------------------------------


def test_m_frozen_aggregate_unchanged_by_wrapper():
    ctx = _context()
    members = [_evaluated_net("REC_A", 1.0, 100), _evaluated_net("REC_B", -0.5, 200), _MISSING, _EXCLUDED]
    direct = aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        excluded_note="policy excluded",
    )
    wrapped = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
        excluded_note="policy excluded",
    )
    assert direct.to_dict() == wrapped.aggregate_record.to_dict()


# ---------------------------------------------------------------------------
# N. Implementation mutation
# ---------------------------------------------------------------------------


def test_n_implementation_mutation_changes_witness_id(monkeypatch):
    ctx = _context()
    r1 = _run(ctx, [_evaluated_net("REC_A", 1.0, 100)])

    import libs.reporting.evaluation.uef6.lineage_witness as lw
    monkeypatch.setattr(lw, "lineage_implementation_digest", lambda: "DIFFERENT_IMPLEMENTATION_DIGEST")
    r2 = _run(ctx, [_evaluated_net("REC_A", 1.0, 100)])

    assert r1.witness.witness_id != r2.witness.witness_id
    assert r1.witness.implementation_digest != r2.witness.implementation_digest
    # frozen aggregate result itself is untouched by the monkeypatch
    assert r1.aggregate_record.to_dict() == r2.aggregate_record.to_dict()
