"""UEF-6C Historical Dedup & Direct-Lineage Validation tests.

End-to-end pipeline tests (E/F/M-family) reuse ONE real, already-CLEAN
legacy artifact directory (``reports/evaluation/opportunity_engine_shadow/
2026-09-22/``, Q11 v2 -- no secondary candle dependency, the simplest real
admission path) copied into an ISOLATED ``tmp_path`` snapshot -- never the
live-growing repository. Pure coverage/accounting tests reuse the SAME
UEF-3C fixture pattern as ``tests/test_uef6_lineage_sidecar.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import ReturnUnit
from libs.reporting.evaluation.canonical.forward.contracts import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import build_event_ref
from libs.reporting.evaluation.canonical.identity import evaluation_record_id as _compute_evaluation_record_id
from libs.reporting.evaluation.canonical.identity import evaluation_subject_id as _compute_evaluation_subject_id
from libs.reporting.evaluation.canonical.record import AggregateIdentity, build_episode_record
from libs.reporting.evaluation.canonical.contracts import ObservationType, ExecutionMode
from libs.reporting.evaluation.canonical.metrics import MetricAggregationContext, MetricPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import (
    CanonicalAggregationMember,
    CanonicalSampleBatch,
    SampleMemberState,
)

from libs.reporting.evaluation.uef5 import historical_recompute as hr

from libs.reporting.evaluation.uef6.lineage_coverage import (
    account_witnesses_against_aggregates,
    aggregate_coverage_totals,
    compute_witness_coverage,
    find_cross_aggregate_physical_event_reuse,
    find_cross_aggregate_record_reuse,
    scan_duplicate_members,
)
from libs.reporting.evaluation.uef6.lineage_model import DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE
from libs.reporting.evaluation.uef6.lineage_witness import aggregate_canonical_samples_with_lineage, lineage_status_without_direct_witness
from libs.reporting.evaluation.uef6.validation_replay import (
    LINKED_TO_FROZEN_HISTORICAL_RESULT,
    NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT,
    aggregate_population_semantic_digest,
    compare_recompute_runs,
    compute_uef6c_run_id,
    episode_population_semantic_digest,
    intercept_aggregation_for_validation,
    link_witnesses_to_frozen_result,
    original_aggregator_is_restored,
    run_baseline_replay,
    run_instrumented_replay,
)


_REAL_Q11_DAY = Path("reports/evaluation/opportunity_engine_shadow/2026-09-22")


def _q11_snapshot(tmp_path: Path) -> Path:
    dst_day = tmp_path / "reports" / "evaluation" / "opportunity_engine_shadow" / "2026-09-22"
    dst_day.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_REAL_Q11_DAY, dst_day)
    return tmp_path


# ---------------------------------------------------------------------------
# UEF-3C fixture helpers (same pattern as test_uef6_lineage_sidecar.py)
# ---------------------------------------------------------------------------

_DEFAULT_METRIC_POLICY_ID = MetricPolicy().policy_id


def _context(*, horizon_label="+30m", aggregation_scope="uef6c_test_scope", hypothesis_id="q10_semi", source_id="agg-1") -> MetricAggregationContext:
    ref = build_event_ref(source_namespace="uef6c_test", native_id=source_id)
    subject = _compute_evaluation_subject_id(canonical_event_id=ref.canonical_event_id, hypothesis_id=hypothesis_id, observation_type="AGGREGATE")
    record_id = _compute_evaluation_record_id(evaluation_subject_id=subject, execution_mode="OBSERVATION_ONLY")
    identity = AggregateIdentity(
        aggregate_ref=ref, aggregation_scope=aggregation_scope, hypothesis_id=hypothesis_id, evaluator_version="v1",
        evaluation_subject_id=subject, evaluation_record_id=record_id,
    )
    return MetricAggregationContext(aggregate_identity=identity, horizon_label=horizon_label, metric_policy_id=_DEFAULT_METRIC_POLICY_ID)


def _evaluated_net(rec_id, net, ts) -> CanonicalAggregationMember:
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED, evaluation_record_id=rec_id, source_net_return=net,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        observed_timestamp=ts,
    )


_MISSING = CanonicalAggregationMember(state=SampleMemberState.MISSING)


def _episode(native_id, hypothesis_id="q10_semi"):
    return build_episode_record(
        source_namespace="uef6c_test_episode", hypothesis_id=hypothesis_id, observation_type=ObservationType.CANDIDATE,
        execution_mode=ExecutionMode.OBSERVATION_ONLY, trading_date="2026-01-01", symbol="005930", native_id=native_id,
    )


def _direct_call(ctx, members):
    return hr.aggregate_canonical_samples(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )


# ---------------------------------------------------------------------------
# A. Instrumentation install / restore
# ---------------------------------------------------------------------------


def test_a_instrumentation_install_and_restore():
    assert original_aggregator_is_restored()
    with intercept_aggregation_for_validation() as recorder:
        assert not original_aggregator_is_restored()
        _direct_call(_context(), [_evaluated_net("REC_A", 1.0, 100)])
        assert recorder.call_count == 1
    assert original_aggregator_is_restored()


# ---------------------------------------------------------------------------
# B. Restore on exception
# ---------------------------------------------------------------------------


def test_b_restore_on_exception():
    assert original_aggregator_is_restored()
    with pytest.raises(RuntimeError):
        with intercept_aggregation_for_validation():
            assert not original_aggregator_is_restored()
            raise RuntimeError("simulated failure inside validation context")
    assert original_aggregator_is_restored()


# ---------------------------------------------------------------------------
# C. One aggregate call -> one witness
# ---------------------------------------------------------------------------


def test_c_one_call_one_witness_no_double_aggregation():
    ctx = _context()
    with intercept_aggregation_for_validation() as recorder:
        record = _direct_call(ctx, [_evaluated_net("REC_A", 1.0, 100)])
    assert recorder.call_count == 1
    assert len(recorder.witnesses) == 1
    assert recorder.witnesses[0].aggregate_evaluation_record_id == record.identity.evaluation_record_id


# ---------------------------------------------------------------------------
# D. Multiple aggregate calls
# ---------------------------------------------------------------------------


def test_d_multiple_calls_exact_n_witnesses():
    with intercept_aggregation_for_validation() as recorder:
        for i in range(3):
            _direct_call(_context(source_id=f"agg-{i}"), [_evaluated_net(f"REC_{i}", 1.0, 100)])
    assert recorder.call_count == 3
    assert len(recorder.witnesses) == 3


# ---------------------------------------------------------------------------
# E. Baseline vs instrumented parity (real frozen pipeline, isolated snapshot)
# ---------------------------------------------------------------------------


def test_e_baseline_vs_instrumented_canonical_parity(tmp_path: Path):
    snapshot = _q11_snapshot(tmp_path)
    baseline = run_baseline_replay(snapshot)
    instrumented = run_instrumented_replay(snapshot)

    assert instrumented.aggregate_call_count > 0
    assert len(instrumented.witnesses) == instrumented.aggregate_call_count

    parity = compare_recompute_runs(baseline.run, instrumented.run)
    assert parity.identical, parity.differences
    assert baseline.run.run_id == instrumented.run.run_id


# ---------------------------------------------------------------------------
# F. Witness/output aggregate 1:1 mapping
# ---------------------------------------------------------------------------


def test_f_witness_to_output_aggregate_mapping(tmp_path: Path):
    snapshot = _q11_snapshot(tmp_path)
    instrumented = run_instrumented_replay(snapshot)
    accounting = account_witnesses_against_aggregates(instrumented.witnesses, instrumented.run.aggregates)

    assert accounting.aggregate_call_count == accounting.captured_witness_count
    assert accounting.missing_aggregate_occurrences == ()
    assert accounting.orphan_witness_occurrences == ()
    assert accounting.matched_occurrence_count == accounting.persisted_aggregate_count


# ---------------------------------------------------------------------------
# G. Orphan witness detection
# ---------------------------------------------------------------------------


def test_g_orphan_witness_detected():
    with intercept_aggregation_for_validation() as recorder:
        _direct_call(_context(source_id="orphan-source"), [_evaluated_net("REC_ORPHAN", 1.0, 100)])
    accounting = account_witnesses_against_aggregates(recorder.witnesses, persisted_aggregates=[])  # nothing "persisted"
    assert accounting.orphan_witness_occurrence_count == 1
    assert accounting.missing_aggregate_occurrences == ()


# ---------------------------------------------------------------------------
# H. Missing witness detection
# ---------------------------------------------------------------------------


def test_h_missing_witness_detected():
    record = _direct_call(_context(source_id="missing-witness-source"), [_evaluated_net("REC_MW", 1.0, 100)])
    accounting = account_witnesses_against_aggregates(witnesses=[], persisted_aggregates=[(record, {})])
    assert accounting.missing_aggregate_occurrence_count == 1
    assert accounting.missing_aggregate_occurrences[0]["evaluation_record_id"] == record.identity.evaluation_record_id
    assert accounting.orphan_witness_occurrences == ()


# ---------------------------------------------------------------------------
# I. Evaluated-only population: both memberships provable
# ---------------------------------------------------------------------------


def test_i_evaluated_only_population_both_proven():
    ep_a, ep_b = _episode("EV_A"), _episode("EV_B")
    ctx = _context()
    result = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[
            _evaluated_net(ep_a.identity.evaluation_record_id, 1.0, 100),
            _evaluated_net(ep_b.identity.evaluation_record_id, -0.5, 200),
        ])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    details = compute_witness_coverage([result.witness], [ep_a, ep_b], family_by_record_id={})
    assert details[0].exact_population_member_identity_proven is True
    assert details[0].exact_evaluated_episode_membership_proven is True


# ---------------------------------------------------------------------------
# J. Evaluated + Missing population: evaluated TRUE, total population FALSE
# ---------------------------------------------------------------------------


def test_j_evaluated_plus_missing_population_split_proof():
    ep_a = _episode("EV_A")
    ctx = _context()
    result = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[
            _evaluated_net(ep_a.identity.evaluation_record_id, 1.0, 100), _MISSING,
        ])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    details = compute_witness_coverage([result.witness], [ep_a], family_by_record_id={})
    assert details[0].exact_evaluated_episode_membership_proven is True  # the one EVALUATED member matched
    assert details[0].exact_population_member_identity_proven is False  # MISSING member has no stable identity


# ---------------------------------------------------------------------------
# K. Duplicate member occurrence historical fixture
# ---------------------------------------------------------------------------


def test_k_duplicate_member_occurrence_historical_scan():
    ctx = _context()
    result = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[
            _evaluated_net("REC_A", 1.0, 100), _evaluated_net("REC_A", 1.0, 101), _evaluated_net("REC_B", -0.5, 200),
        ])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    scan = scan_duplicate_members([result.witness])
    assert scan["aggregates_with_duplicate_member_ids"] == 1
    assert scan["duplicate_member_identity_count_total"] == 1
    assert scan["duplicate_member_excess_count_total"] == 1
    assert scan["per_aggregate_detail"][0]["duplicate_member_ids"] == ["REC_A"]


# ---------------------------------------------------------------------------
# L. Cross-aggregate same evaluated record
# ---------------------------------------------------------------------------


def test_l_cross_aggregate_same_evaluated_record_reused():
    ctx1 = _context(source_id="agg-1", horizon_label="+5m")
    ctx2 = _context(source_id="agg-2", horizon_label="+30m")
    r1 = aggregate_canonical_samples_with_lineage(
        context=ctx1, batches=[CanonicalSampleBatch(context=ctx1, members=[_evaluated_net("REC_SHARED", 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    r2 = aggregate_canonical_samples_with_lineage(
        context=ctx2, batches=[CanonicalSampleBatch(context=ctx2, members=[_evaluated_net("REC_SHARED", 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    reuse = find_cross_aggregate_record_reuse([r1.witness, r2.witness])
    assert len(reuse) == 1
    assert reuse[0]["evaluation_record_id"] == "REC_SHARED"
    assert set(reuse[0]["aggregate_ids"]) == {r1.witness.canonical_aggregate_id, r2.witness.canonical_aggregate_id}


# ---------------------------------------------------------------------------
# M. Cross-aggregate same physical event / different evaluation record
# ---------------------------------------------------------------------------


def test_m_cross_aggregate_same_physical_event_different_record():
    ep = _episode("SHARED_PHYSICAL_EVENT")
    # Two DIFFERENT evaluation subjects (different hypothesis) over the
    # SAME physical event -- exactly UEF-6A's own LEGITIMATE_MULTI_HYPOTHESIS shape.
    from libs.reporting.evaluation.canonical.record import build_episode_record as _build

    ep2 = _build(
        source_namespace="uef6c_test_episode", hypothesis_id="different_hypothesis", observation_type=ObservationType.CANDIDATE,
        execution_mode=ExecutionMode.OBSERVATION_ONLY, trading_date="2026-01-01", symbol="005930",
        event_ref=ep.identity.event,  # SAME physical event
    )
    assert ep.identity.event.canonical_event_id == ep2.identity.event.canonical_event_id
    assert ep.identity.evaluation_record_id != ep2.identity.evaluation_record_id

    ctx1 = _context(source_id="agg-p1")
    ctx2 = _context(source_id="agg-p2")
    r1 = aggregate_canonical_samples_with_lineage(
        context=ctx1, batches=[CanonicalSampleBatch(context=ctx1, members=[_evaluated_net(ep.identity.evaluation_record_id, 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    r2 = aggregate_canonical_samples_with_lineage(
        context=ctx2, batches=[CanonicalSampleBatch(context=ctx2, members=[_evaluated_net(ep2.identity.evaluation_record_id, 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    episode_index = {ep.identity.evaluation_record_id: ep, ep2.identity.evaluation_record_id: ep2}
    record_reuse = find_cross_aggregate_record_reuse([r1.witness, r2.witness])
    event_reuse = find_cross_aggregate_physical_event_reuse([r1.witness, r2.witness], episode_index)

    assert record_reuse == []  # different evaluation_record_ids -- NOT record reuse
    assert len(event_reuse) == 1  # SAME physical event -- IS event reuse
    assert event_reuse[0]["canonical_event_id"] == ep.identity.event.canonical_event_id


# ---------------------------------------------------------------------------
# N. Frozen-output-only: no witness -> NOT_PROVABLE
# ---------------------------------------------------------------------------


def test_n_frozen_output_only_not_provable():
    assert lineage_status_without_direct_witness() == DIRECT_AGGREGATION_WITNESS_NOT_AVAILABLE


# ---------------------------------------------------------------------------
# O. Replay parity failure -> witness NOT linked to frozen result
# ---------------------------------------------------------------------------


def test_o_replay_parity_failure_not_linked():
    class _StubRun:
        def __init__(self, run_id):
            self.run_id = run_id
            self.status = "COMPLETE"
            self.summary = {}
            self.episodes = []
            self.aggregates = []
            self.input_manifest = {}
            self.run_manifest = {}

    parity_ok = compare_recompute_runs(_StubRun("UEF5RUN_A"), _StubRun("UEF5RUN_A"))
    parity_bad = compare_recompute_runs(_StubRun("UEF5RUN_A"), _StubRun("UEF5RUN_B"))

    assert parity_ok.identical is True
    assert link_witnesses_to_frozen_result(parity_ok) == LINKED_TO_FROZEN_HISTORICAL_RESULT
    assert parity_bad.identical is False
    assert link_witnesses_to_frozen_result(parity_bad) == NOT_LINKED_TO_FROZEN_HISTORICAL_RESULT


# ---------------------------------------------------------------------------
# P. Deterministic validation run identity
# ---------------------------------------------------------------------------


def test_p_validation_run_id_deterministic():
    kwargs = dict(
        target_uef52_run_id="UEF5RUN_X", target_episodes_digest="ep_digest", target_aggregates_digest="agg_digest",
        uef6a_impl_digest="a", uef6b_impl_digest="b", uef6c_impl_digest="c", effective_replay_config_digest="cfg",
    )
    assert compute_uef6c_run_id(**kwargs) == compute_uef6c_run_id(**kwargs)


# ---------------------------------------------------------------------------
# Q. Input/output mutation changes validation run id
# ---------------------------------------------------------------------------


def test_q_mutation_changes_validation_run_id():
    base = dict(
        target_uef52_run_id="UEF5RUN_X", target_episodes_digest="ep_digest", target_aggregates_digest="agg_digest",
        uef6a_impl_digest="a", uef6b_impl_digest="b", uef6c_impl_digest="c", effective_replay_config_digest="cfg",
    )
    mutated = dict(base, target_episodes_digest="DIFFERENT_DIGEST")
    assert compute_uef6c_run_id(**base) != compute_uef6c_run_id(**mutated)

    mutated_impl = dict(base, uef6c_impl_digest="DIFFERENT_IMPL")
    assert compute_uef6c_run_id(**base) != compute_uef6c_run_id(**mutated_impl)


# ---------------------------------------------------------------------------
# Final Audit item A/1-8: order-independent, multiplicity-sensitive,
# content-mutation-sensitive semantic digests -- the concrete defect Codex
# found (sorting by evaluation_record_id alone leaves ties in original
# input order).
# ---------------------------------------------------------------------------


def _episode_with_version(native_id, evaluator_version, hypothesis_id="q10_semi"):
    return build_episode_record(
        source_namespace="uef6c_test_episode", hypothesis_id=hypothesis_id, observation_type=ObservationType.CANDIDATE,
        execution_mode=ExecutionMode.OBSERVATION_ONLY, trading_date="2026-01-01", symbol="005930", native_id=native_id,
        evaluator_version=evaluator_version,
    )


def test_r_episode_digest_order_invariant_tied_record_id_evaluator_version():
    a = _episode_with_version("TIE_EVENT", "v1")
    b = _episode_with_version("TIE_EVENT", "v2")
    assert a.identity.evaluation_record_id == b.identity.evaluation_record_id
    assert a.identity.evaluator_version != b.identity.evaluator_version
    third = _episode("UNRELATED_EVENT_R")

    digest_ab = episode_population_semantic_digest([a, b, third])
    digest_ba = episode_population_semantic_digest([b, a, third])
    assert digest_ab == digest_ba

    kwargs_ab = dict(
        target_uef52_run_id="UEF5RUN_X", target_episodes_digest=digest_ab, target_aggregates_digest="agg",
        uef6a_impl_digest="a", uef6b_impl_digest="b", uef6c_impl_digest="c", effective_replay_config_digest="cfg",
    )
    kwargs_ba = dict(kwargs_ab, target_episodes_digest=digest_ba)
    assert compute_uef6c_run_id(**kwargs_ab) == compute_uef6c_run_id(**kwargs_ba)


def test_s_episode_digest_multiplicity_sensitive():
    a = _episode("MULTI_A")
    b = _episode("MULTI_B")
    digest_ab = episode_population_semantic_digest([a, b])
    digest_abb = episode_population_semantic_digest([a, b, b])
    assert digest_ab != digest_abb  # never set semantics


def test_t_episode_digest_content_mutation_sensitive():
    a = _episode("MUT_A", hypothesis_id="q10_semi")
    a_prime = _episode("MUT_A", hypothesis_id="different_hyp")
    digest_a = episode_population_semantic_digest([a])
    digest_a_prime = episode_population_semantic_digest([a_prime])
    assert digest_a != digest_a_prime


def test_u_aggregate_digest_order_invariant_and_multiset():
    ctx1 = _context(source_id="agg-order-1")
    r1 = _direct_call(ctx1, [_evaluated_net("REC_ORD1", 1.0, 100)])
    ctx2 = _context(source_id="agg-order-2")
    r2 = _direct_call(ctx2, [_evaluated_net("REC_ORD2", 1.0, 100)])

    aggs_ab = [(r1, {"family": "f1"}), (r2, {"family": "f2"})]
    aggs_ba = [(r2, {"family": "f2"}), (r1, {"family": "f1"})]
    assert aggregate_population_semantic_digest(aggs_ab) == aggregate_population_semantic_digest(aggs_ba)

    aggs_abb = [(r1, {"family": "f1"}), (r2, {"family": "f2"}), (r2, {"family": "f2"})]
    assert aggregate_population_semantic_digest(aggs_abb) != aggregate_population_semantic_digest(aggs_ab)


def test_v_implementation_digest_includes_lineage_coverage(monkeypatch):
    from libs.reporting.evaluation.uef6 import validation_replay as vr

    full_digest = vr.validation_implementation_digest()
    monkeypatch.setattr(vr, "_VALIDATION_IMPLEMENTATION_FILES", ("validation_replay.py",))
    reduced_digest = vr.validation_implementation_digest()
    assert full_digest != reduced_digest  # lineage_coverage.py's inclusion causally affects the digest


# ---------------------------------------------------------------------------
# Final Audit item C/11-16: full semantic witness<->aggregate match key
# (evaluation_record_id, canonical_aggregate_id, context_digest) -- never
# evaluation_record_id alone.
# ---------------------------------------------------------------------------


def test_w_context_different_same_record_id_not_double_covered():
    ctx1 = _context(source_id="agg-ctx-same", horizon_label="+5m")
    ctx2 = _context(source_id="agg-ctx-same", horizon_label="+30m")
    assert ctx1.aggregate_identity.evaluation_record_id == ctx2.aggregate_identity.evaluation_record_id

    result1 = aggregate_canonical_samples_with_lineage(
        context=ctx1, batches=[CanonicalSampleBatch(context=ctx1, members=[_evaluated_net("REC_CTXW1", 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    record2 = _direct_call(ctx2, [_evaluated_net("REC_CTXW2", 1.0, 100)])

    accounting = account_witnesses_against_aggregates(
        [result1.witness], persisted_aggregates=[(result1.aggregate_record, {}), (record2, {})]
    )
    assert accounting.matched_occurrence_count == 1
    assert accounting.missing_aggregate_occurrence_count == 1
    assert accounting.orphan_witness_occurrence_count == 0
    assert accounting.missing_aggregate_occurrences[0]["canonical_aggregate_id"] == record2.identity.canonical_aggregate_id


def test_x_same_full_key_multiplicity_both_directions():
    ctx = _context(source_id="agg-samekey")
    result = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=[_evaluated_net("REC_SK", 1.0, 100)])],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )

    two_aggregates_one_witness = account_witnesses_against_aggregates(
        [result.witness], persisted_aggregates=[(result.aggregate_record, {}), (result.aggregate_record, {})]
    )
    assert two_aggregates_one_witness.matched_occurrence_count == 1
    assert two_aggregates_one_witness.missing_aggregate_occurrence_count == 1
    assert two_aggregates_one_witness.orphan_witness_occurrence_count == 0

    one_aggregate_two_witnesses = account_witnesses_against_aggregates(
        [result.witness, result.witness], persisted_aggregates=[(result.aggregate_record, {})]
    )
    assert one_aggregate_two_witnesses.matched_occurrence_count == 1
    assert one_aggregate_two_witnesses.orphan_witness_occurrence_count == 1
    assert one_aggregate_two_witnesses.missing_aggregate_occurrence_count == 0


# ---------------------------------------------------------------------------
# Final Audit item D/17-19: duplicate member IDENTITY KIND count vs EXCESS
# occurrence count must never be conflated.
# ---------------------------------------------------------------------------


def _witness_with_members(rec_ids, source_id):
    ctx = _context(source_id=source_id)
    members = [_evaluated_net(rid, 1.0, 100 + i) for i, rid in enumerate(rec_ids)]
    result = aggregate_canonical_samples_with_lineage(
        context=ctx, batches=[CanonicalSampleBatch(context=ctx, members=members)],
        metric_policy=MetricPolicy(), input_return_unit=ReturnUnit.PERCENTAGE_POINTS, aggregation_window_start="2026-09-15",
    )
    return result.witness


@pytest.mark.parametrize(
    "rec_ids,expected_kinds,expected_excess",
    [
        (["A", "A", "B"], 1, 1),
        (["A", "A", "A", "B"], 1, 2),
        (["A", "A", "B", "B"], 2, 2),
        (["A", "A", "A", "B", "B"], 2, 3),
    ],
    ids=["case1_double_plus_single", "case2_triple_plus_single", "case3_two_doubles", "case4_triple_plus_double"],
)
def test_y_duplicate_kinds_vs_excess_cases(rec_ids, expected_kinds, expected_excess):
    witness = _witness_with_members(rec_ids, source_id=f"dup-{'-'.join(rec_ids)}-{expected_kinds}-{expected_excess}")
    scan = scan_duplicate_members([witness])
    assert scan["duplicate_member_identity_count_total"] == expected_kinds
    assert scan["duplicate_member_excess_count_total"] == expected_excess
    detail = scan["per_aggregate_detail"][0]
    assert detail["duplicate_member_identity_count"] == expected_kinds
    assert detail["duplicate_member_excess_count"] == expected_excess
