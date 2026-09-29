"""UEF-8 Fair Comparison Validation tests.

Pure-logic tests build small synthetic UEF-7-normalized-board-shaped
payloads (never a real board build, to keep them fast and isolated). The
single real-board regression (V) is the only test that calls the real
live Alpha Board through the real UEF-7 normalizer.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board
from libs.reporting.evaluation.uef7.model import POPULATION_DIRECT_PROVEN
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest as uef7_impl_digest
from libs.reporting.evaluation.uef8 import fair_comparison as uef8_fair_comparison
from libs.reporting.evaluation.uef8.fair_comparison import (
    UEF8InputContractError,
    UEF8PairIdentityCollisionError,
    _canonical_pair_id,
    _validate_pair_identity_uniqueness,
    analyze_fair_comparisons,
)
from libs.reporting.evaluation.uef8.model import COMPARABLE, CONDITIONAL, NOT_COMPARABLE, ComparisonPair
from libs.reporting.evaluation.uef8.run_identity import compute_uef8_run_id, uef8_implementation_digest

_IMPL_DIGEST = uef8_implementation_digest()
_ROOT = Path(__file__).resolve().parents[1]


def _row(candidate_id, *, question_id="A", target_horizon="+30m", evidence_cohort="historical",
         sample_count=10, win_rate=0.5, avg_net_return_pct=0.1, profit_factor=1.2,
         max_drawdown_pct=-0.05, coverage=0.9, avg_mfe_pct=0.2, avg_mae_pct=-0.1,
         population_identity_status="NOT_PROVABLE_FROM_ALPHA_BOARD_V2",
         shared_source_group_ids=()):
    return {
        "question_id": question_id,
        "candidate_id": candidate_id,
        "target_horizon": target_horizon,
        "status": "DISCOVERY",
        "operation_status": "SHADOW_CONTINUES",
        "fixed_validation_status": "FIXED_VALIDATION_NOT_YET_RUN",
        "production_promotion_status": "PRODUCTION_PROMOTION_NOT_ALLOWED",
        "decision": "INSUFFICIENT_EVIDENCE",
        "evidence_cohort": evidence_cohort,
        "sample_count": sample_count,
        "window_count": sample_count,
        "win_rate": win_rate,
        "avg_net_return_pct": avg_net_return_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "coverage": coverage,
        "avg_mfe_pct": avg_mfe_pct,
        "avg_mae_pct": avg_mae_pct,
        "metric_authority": "ALPHA_BOARD_V2_DERIVED_VIEW",
        "canonical_metric_link_status": "NOT_PROVEN",
        "source_references": [],
        "source_anomalies": [],
        "source_bundle_id": f"bundle_{candidate_id}",
        "shared_source_group_ids": list(shared_source_group_ids),
        "shared_source_candidate_ids": [],
        "population_identity_status": population_identity_status,
        "evidence_independence_status": "INDEPENDENCE_NOT_PROVEN",
    }


def _board(rows, *, uef7_run_id="UEF7RUN_test", through_day="2026-09-25"):
    return {
        "schema_version": "uef7.alpha_board_normalization.v1",
        "source_board_schema_version": "alpha_research_board.v2",
        "source_board_contract_version": "abc_fixed_2026_08_27",
        "through_day": through_day,
        "candidate_row_count": len(rows),
        "candidate_ids": [r["candidate_id"] for r in rows],
        "normalized_rows": rows,
        "source_groups": [],
        "normalization_summary": {
            "candidate_row_count": len(rows), "shared_source_group_count": 0,
            "rows_with_shared_source_count": 0, "proven_population_group_count": 0,
            "unresolved_population_candidate_count": len(rows),
        },
        "authority": {
            "source_overlap_is_not_population_equivalence": True,
            "candidate_rows_are_not_independent_evidence_units": True,
            "population_identity_requires_direct_authority": True,
            "ranking_change_authorized": False,
            "strategy_change_authorized": False,
            "production_change_authorized": False,
        },
        "source_board_semantic_digest": "digest_x",
        "normalizer_implementation_digest": "impl_x",
        "uef7_run_id": uef7_run_id,
    }


def _analyze(board):
    return analyze_fair_comparisons(board, uef8_implementation_digest_value=_IMPL_DIGEST)


# ---------------------------------------------------------------------------
# A. Pair universe
# ---------------------------------------------------------------------------


def test_a_four_candidates_exactly_six_pairs():
    board = _board([_row("A1"), _row("A2"), _row("A3"), _row("A4")])
    run = _analyze(board)
    assert run.summary.pair_count == 6
    assert len(run.pairs) == 6


# ---------------------------------------------------------------------------
# B. No self-pairs
# ---------------------------------------------------------------------------


def test_b_no_self_pairs():
    board = _board([_row("A1"), _row("A2")])
    run = _analyze(board)
    for pair in run.pairs:
        assert pair.left_candidate_id != pair.right_candidate_id


# ---------------------------------------------------------------------------
# C. No directional duplication
# ---------------------------------------------------------------------------


def test_c_no_directional_duplication():
    board = _board([_row("A1"), _row("A2")])
    run = _analyze(board)
    assert len(run.pairs) == 1
    pair = run.pairs[0]
    assert {pair.left_candidate_id, pair.right_candidate_id} == {"A1", "A2"}


# ---------------------------------------------------------------------------
# D. Candidate permutation invariance
# ---------------------------------------------------------------------------


def test_d_candidate_permutation_invariance():
    rows_forward = [_row("A1"), _row("A2"), _row("A3")]
    rows_reversed = list(reversed(rows_forward))
    run_forward = _analyze(_board(rows_forward))
    run_reversed = _analyze(_board(rows_reversed))
    assert run_forward.uef8_run_id == run_reversed.uef8_run_id
    assert [p.to_dict() for p in run_forward.pairs] == [p.to_dict() for p in run_reversed.pairs]


# ---------------------------------------------------------------------------
# E. Different question -> NOT_COMPARABLE
# ---------------------------------------------------------------------------


def test_e_different_question_not_comparable():
    board = _board([_row("A1", question_id="A"), _row("B1", question_id="B")])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "DIFFERENT_RESEARCH_QUESTION" in pair.comparison_reasons


# ---------------------------------------------------------------------------
# F. Different horizon -> NOT_COMPARABLE
# ---------------------------------------------------------------------------


def test_f_different_horizon_not_comparable():
    board = _board([_row("A1", target_horizon="+5m"), _row("A2", target_horizon="+30m")])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "DIFFERENT_TARGET_HORIZON" in pair.comparison_reasons


# ---------------------------------------------------------------------------
# G. Different cohort -> NOT_COMPARABLE
# ---------------------------------------------------------------------------


def test_g_different_cohort_not_comparable():
    board = _board([_row("A1", evidence_cohort="historical"), _row("A2", evidence_cohort="prospective")])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "DIFFERENT_EVIDENCE_COHORT" in pair.comparison_reasons


# ---------------------------------------------------------------------------
# H. Missing cohort -> NOT_COMPARABLE
# ---------------------------------------------------------------------------


def test_h_missing_cohort_not_comparable():
    board = _board([_row("A1", evidence_cohort=None), _row("A2", evidence_cohort="historical")])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "EVIDENCE_COHORT_NOT_AVAILABLE" in pair.comparison_reasons
    assert "DIFFERENT_EVIDENCE_COHORT" not in pair.comparison_reasons


# ---------------------------------------------------------------------------
# I. No shared metrics -> NOT_COMPARABLE
# ---------------------------------------------------------------------------


def test_i_no_shared_metrics_not_comparable():
    row_a = _row("A1", win_rate=0.5, avg_net_return_pct=None, profit_factor=None,
                 max_drawdown_pct=None, coverage=None, avg_mfe_pct=None, avg_mae_pct=None)
    row_b = _row("A2", win_rate=None, avg_net_return_pct=0.2, profit_factor=None,
                 max_drawdown_pct=None, coverage=None, avg_mfe_pct=None, avg_mae_pct=None)
    board = _board([row_a, row_b])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "NO_SHARED_OUTCOME_METRIC" in pair.comparison_reasons
    assert pair.shared_available_metrics == ()


# ---------------------------------------------------------------------------
# J. Metric availability mismatch -> CONDITIONAL (no harder blocker)
# ---------------------------------------------------------------------------


def test_j_metric_availability_mismatch_conditional():
    row_a = _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN,
                 win_rate=0.5, avg_net_return_pct=0.1, profit_factor=None,
                 max_drawdown_pct=-0.05, coverage=0.9, avg_mfe_pct=0.2, avg_mae_pct=-0.1)
    row_b = _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN,
                 win_rate=0.5, avg_net_return_pct=0.1, profit_factor=1.2,
                 max_drawdown_pct=-0.05, coverage=0.9, avg_mfe_pct=0.2, avg_mae_pct=-0.1)
    board = _board([row_a, row_b])
    pair = _analyze(board).pairs[0]
    assert "METRIC_AVAILABILITY_MISMATCH" in pair.comparison_reasons
    assert pair.comparison_status == CONDITIONAL


# ---------------------------------------------------------------------------
# K. sample_count missing/zero -> CONDITIONAL (no harder blocker)
# ---------------------------------------------------------------------------


def test_k_sample_count_zero_conditional():
    row_a = _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN, sample_count=0)
    row_b = _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN, sample_count=10)
    board = _board([row_a, row_b])
    pair = _analyze(board).pairs[0]
    assert "INSUFFICIENT_SAMPLE_ACCOUNTING" in pair.comparison_reasons
    assert pair.comparison_status == CONDITIONAL


def test_k2_sample_count_none_conditional():
    row_a = _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN, sample_count=None)
    row_b = _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN, sample_count=10)
    board = _board([row_a, row_b])
    pair = _analyze(board).pairs[0]
    assert "INSUFFICIENT_SAMPLE_ACCOUNTING" in pair.comparison_reasons
    assert pair.comparison_status == CONDITIONAL


# ---------------------------------------------------------------------------
# L. Population unproven -> CONDITIONAL if otherwise aligned
# ---------------------------------------------------------------------------


def test_l_population_unproven_conditional_when_otherwise_aligned():
    board = _board([_row("A1"), _row("A2")])  # both default NOT_PROVABLE_FROM_ALPHA_BOARD_V2
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == CONDITIONAL
    assert pair.comparison_reasons == ("POPULATION_RELATION_NOT_PROVEN",)


# ---------------------------------------------------------------------------
# M. Shared source -> CONDITIONAL reason added, never population equality
# ---------------------------------------------------------------------------


def test_m_shared_source_conditional_reason_never_population_equality():
    # Population Relation Authority Bounded Fix item 9/13-C: shared source
    # + individually-proven population statuses must still carry BOTH
    # POPULATION_RELATION_NOT_PROVEN and SHARED_SOURCE_PROVENANCE -- shared
    # source is never, by itself, treated as population equality/proof.
    board = _board([
        _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN, shared_source_group_ids=("SRCGRP_1",)),
        _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN, shared_source_group_ids=("SRCGRP_1",)),
    ])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_reasons == ("POPULATION_RELATION_NOT_PROVEN", "SHARED_SOURCE_PROVENANCE")
    assert pair.shared_source_group_ids == ("SRCGRP_1",)
    assert pair.comparison_status == CONDITIONAL


# ---------------------------------------------------------------------------
# N. Different source does not prove independence, and does not itself
# create pair population authority either (Population Relation Authority
# Bounded Fix item 8/13-B).
# ---------------------------------------------------------------------------


def test_n_different_source_does_not_prove_independence():
    board = _board([
        _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN, shared_source_group_ids=("SRCGRP_1",)),
        _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN, shared_source_group_ids=("SRCGRP_2",)),
    ])
    pair = _analyze(board).pairs[0]
    assert "SHARED_SOURCE_PROVENANCE" not in pair.comparison_reasons
    assert pair.shared_source_group_ids == ()
    # Different source provenance never upgrades to COMPARABLE, and never
    # fabricates a "PROVEN_INDEPENDENT" reason either -- population
    # relation authority remains controlling and is unconditionally
    # unproven under the current UEF-7 schema.
    assert pair.comparison_status == CONDITIONAL
    assert pair.comparison_reasons == ("POPULATION_RELATION_NOT_PROVEN",)
    assert not any("INDEPENDEN" in r for r in pair.comparison_reasons)


# ---------------------------------------------------------------------------
# O/A. Individual population proof != pair population relation proof
# (Population Relation Authority Bounded Fix item 2/7/13-A). Both rows
# individually DIRECT_POPULATION_IDENTITY_PROVEN, every OTHER dimension
# aligned, still CONDITIONAL -- COMPARABLE is unreachable because the
# frozen uef7.alpha_board_normalization.v1 schema exposes no field
# equivalent to a pairwise population relation, regardless of what either
# row's own individual status says. This fixture is built directly from
# the frozen UEF-7 dataclass-shaped dict contract (a value the schema
# itself can represent), never by modifying UEF-7.
# ---------------------------------------------------------------------------


def test_o_individual_population_proof_is_not_pair_relation_proof():
    board = _board([
        _row("A1", population_identity_status=POPULATION_DIRECT_PROVEN),
        _row("A2", population_identity_status=POPULATION_DIRECT_PROVEN),
    ])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_reasons == ("POPULATION_RELATION_NOT_PROVEN",)
    assert pair.comparison_status == CONDITIONAL


def test_d_comparable_unreachable_for_best_case_current_schema_valid_input():
    # Item D/13-D: even the BEST possible current-schema-valid fixture --
    # same question/horizon/cohort, fully shared metrics, valid non-zero
    # sample counts on both sides, both individual population statuses
    # DIRECT_POPULATION_IDENTITY_PROVEN, no source overlap at all -- can
    # never reach COMPARABLE, because no current UEF-7 field can ever
    # supply pairwise population-relation authority. COMPARABLE remains
    # reserved in the UEF-8 enum/schema for a future frozen UEF-7 schema
    # extension; this test proves it is unreachable today, not merely
    # unobserved.
    board = _board([
        _row("A1", question_id="A", target_horizon="+30m", evidence_cohort="historical",
             sample_count=50, population_identity_status=POPULATION_DIRECT_PROVEN),
        _row("A2", question_id="A", target_horizon="+30m", evidence_cohort="historical",
             sample_count=50, population_identity_status=POPULATION_DIRECT_PROVEN),
    ])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status != COMPARABLE
    assert pair.comparison_status == CONDITIONAL
    assert pair.comparison_reasons == ("POPULATION_RELATION_NOT_PROVEN",)


# ---------------------------------------------------------------------------
# P. Reason ordering deterministic
# ---------------------------------------------------------------------------


def test_p_reason_ordering_deterministic():
    board = _board([
        _row("A1", question_id="A", target_horizon="+5m", evidence_cohort="historical",
             shared_source_group_ids=("SRCGRP_1",)),
        _row("B1", question_id="B", target_horizon="+30m", evidence_cohort="prospective",
             shared_source_group_ids=("SRCGRP_1",)),
    ])
    pair = _analyze(board).pairs[0]
    idx = [pair.comparison_reasons.index(r) for r in pair.comparison_reasons]
    assert idx == sorted(idx)  # already in REASON_ORDER's fixed order
    assert pair.comparison_reasons[0] == "DIFFERENT_RESEARCH_QUESTION"


# ---------------------------------------------------------------------------
# Q. Multiple reasons preserved even though status is determined by the
# strongest (hard) reason.
# ---------------------------------------------------------------------------


def test_q_multiple_reasons_preserved_under_not_comparable():
    board = _board([
        _row("A1", question_id="A", target_horizon="+5m", evidence_cohort="historical",
             shared_source_group_ids=("SRCGRP_1",)),
        _row("B1", question_id="B", target_horizon="+30m", evidence_cohort="prospective",
             shared_source_group_ids=("SRCGRP_1",)),
    ])
    pair = _analyze(board).pairs[0]
    assert pair.comparison_status == NOT_COMPARABLE
    assert "DIFFERENT_RESEARCH_QUESTION" in pair.comparison_reasons
    assert "DIFFERENT_TARGET_HORIZON" in pair.comparison_reasons
    assert "DIFFERENT_EVIDENCE_COHORT" in pair.comparison_reasons
    assert "SHARED_SOURCE_PROVENANCE" in pair.comparison_reasons
    assert "POPULATION_RELATION_NOT_PROVEN" in pair.comparison_reasons


# ---------------------------------------------------------------------------
# R. Pair accounting conservation
# ---------------------------------------------------------------------------


def test_r_pair_accounting_conservation():
    rows = [_row(f"A{i}") for i in range(6)]
    run = _analyze(_board(rows))
    n = len(rows)
    assert run.summary.pair_count == n * (n - 1) // 2
    assert run.summary.pair_count == (
        run.summary.comparable_count + run.summary.conditional_count + run.summary.not_comparable_count
    )
    seen = set()
    for pair in run.pairs:
        key = frozenset((pair.left_candidate_id, pair.right_candidate_id))
        assert key not in seen
        seen.add(key)
    assert len(seen) == run.summary.pair_count


# ---------------------------------------------------------------------------
# S. Semantic mutation changes run ID
# ---------------------------------------------------------------------------


def test_s_semantic_mutation_changes_run_id():
    board_a = _board([_row("A1", win_rate=0.5), _row("A2")])
    board_b = _board([_row("A1", win_rate=0.51), _row("A2")])
    assert _analyze(board_a).uef8_run_id != _analyze(board_b).uef8_run_id


# ---------------------------------------------------------------------------
# T. Input ordering does not change run ID (duplicate of D, kept for 1:1
# mapping to the required item list)
# ---------------------------------------------------------------------------


def test_t_input_ordering_does_not_change_run_id():
    board_forward = _board([_row("A1"), _row("A2"), _row("A3")])
    board_reversed = _board(list(reversed(board_forward["normalized_rows"])))
    assert _analyze(board_forward).uef8_run_id == _analyze(board_reversed).uef8_run_id


# ---------------------------------------------------------------------------
# U. No ranking fields
# ---------------------------------------------------------------------------


def test_u_no_ranking_fields_present():
    board = _board([_row("A1"), _row("A2")])
    payload = _analyze(board).to_dict()
    forbidden = ("score", "rank", "tier", "winner", "loser", "best_candidate", "expected_winner", "promotion_recommendation", "strategy_recommendation")

    def _check(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert not any(name == k.lower() for name in forbidden), f"forbidden key {k!r}"
                _check(v)
        elif isinstance(obj, list):
            for item in obj:
                _check(item)

    _check(payload)


# ---------------------------------------------------------------------------
# Input contract validation
# ---------------------------------------------------------------------------


def test_wrong_uef7_schema_version_rejected():
    board = _board([_row("A1")])
    board["schema_version"] = "uef7.alpha_board_normalization.v0"
    with pytest.raises(UEF8InputContractError):
        _analyze(board)


def test_candidate_row_count_mismatch_rejected():
    board = _board([_row("A1"), _row("A2")])
    board["candidate_row_count"] = 99
    with pytest.raises(UEF8InputContractError):
        _analyze(board)


def test_duplicate_candidate_id_rejected():
    board = _board([_row("A1"), _row("A1")])
    with pytest.raises(UEF8InputContractError):
        _analyze(board)


def test_ranking_change_authorized_true_rejected():
    board = _board([_row("A1"), _row("A2")])
    board["authority"]["ranking_change_authorized"] = True
    with pytest.raises(UEF8InputContractError):
        _analyze(board)


def test_missing_authority_flag_rejected():
    board = _board([_row("A1"), _row("A2")])
    del board["authority"]["strategy_change_authorized"]
    with pytest.raises(UEF8InputContractError):
        _analyze(board)


# ---------------------------------------------------------------------------
# Pair Identity Collision Bounded Fix -- required tests A-G.
# ---------------------------------------------------------------------------


def test_pair_id_a_order_invariance():
    assert _canonical_pair_id("A", "B") == _canonical_pair_id("B", "A")
    assert _canonical_pair_id("Z_LAST", "A_FIRST") == _canonical_pair_id("A_FIRST", "Z_LAST")


def test_pair_id_b_delimiter_collision_regression():
    # The exact adversarial case: (A, B__C) vs (A__B, C) must never collide
    # at the pair-ID level.
    id1 = _canonical_pair_id("A", "B__C")
    id2 = _canonical_pair_id("A__B", "C")
    assert id1 != id2


def test_pair_id_b2_delimiter_collision_full_board_regression():
    board = _board([_row("A"), _row("B__C"), _row("A__B"), _row("C")])
    run = _analyze(board)
    pair_ids = [p.comparison_pair_id for p in run.pairs]
    pair_tuples = [(p.left_candidate_id, p.right_candidate_id) for p in run.pairs]
    assert len(pair_ids) == len(set(pair_ids)) == 6
    assert len(pair_tuples) == len(set(pair_tuples)) == 6
    # The specific adversarial pair (A, B__C) and (A__B, C) both exist and
    # remain semantically and id-distinct.
    assert ("A", "B__C") in pair_tuples
    assert ("A__B", "C") in pair_tuples
    idx_1 = pair_tuples.index(("A", "B__C"))
    idx_2 = pair_tuples.index(("A__B", "C"))
    assert pair_ids[idx_1] != pair_ids[idx_2]


@pytest.mark.parametrize(
    "candidate_ids",
    [
        ["cand:1", "cand/2", "cand\\3", "cand|4"],
        ["cand,1", "cand[2]", "cand{3}", 'cand"4"'],
        ["cafe_u_umlaut_ü", "日本語", "cand__underscored", "  spaced  "],
    ],
)
def test_pair_id_c_unusual_characters_distinct_ids(candidate_ids):
    board = _board([_row(cid) for cid in candidate_ids])
    run = _analyze(board)
    pair_ids = [p.comparison_pair_id for p in run.pairs]
    pair_tuples = [(p.left_candidate_id, p.right_candidate_id) for p in run.pairs]
    n = len(candidate_ids)
    assert len(pair_ids) == len(set(pair_ids)) == n * (n - 1) // 2
    assert len(pair_tuples) == len(set(pair_tuples)) == n * (n - 1) // 2


def test_pair_id_d_and_e_uniqueness_for_n_candidates():
    n = 8
    board = _board([_row(f"C{i}") for i in range(n)])
    run = _analyze(board)
    pair_ids = [p.comparison_pair_id for p in run.pairs]
    pair_tuples = [(p.left_candidate_id, p.right_candidate_id) for p in run.pairs]
    expected = n * (n - 1) // 2
    assert len(pair_ids) == expected
    assert len(set(pair_ids)) == expected  # D
    assert len(set(pair_tuples)) == expected  # E
    assert all(left != right for left, right in pair_tuples)  # no self-pairs


def test_pair_id_f_collision_fails_closed_direct_validator():
    def _fake_pair(left, right, pid):
        return ComparisonPair(
            comparison_pair_id=pid, left_candidate_id=left, right_candidate_id=right,
            question_id_left="A", question_id_right="A", target_horizon_left="+30m", target_horizon_right="+30m",
            evidence_cohort_left="historical", evidence_cohort_right="historical",
            sample_count_left=10, sample_count_right=10,
            metrics_available_left=(), metrics_available_right=(), shared_available_metrics=(),
            population_identity_status_left="x", population_identity_status_right="x",
            shared_source_group_ids=(), comparison_status=CONDITIONAL,
            comparison_reasons=("POPULATION_RELATION_NOT_PROVEN",),
        )

    colliding = [_fake_pair("A1", "A2", "SAME_ID"), _fake_pair("A1", "A3", "SAME_ID")]
    with pytest.raises(UEF8PairIdentityCollisionError):
        _validate_pair_identity_uniqueness(colliding, expected_pair_count=2)


def test_pair_id_f2_collision_fails_closed_via_monkeypatched_generator(monkeypatch):
    monkeypatch.setattr(uef8_fair_comparison, "_canonical_pair_id", lambda a, b: "UEF8PAIR_CONSTANT")
    board = _board([_row("A1"), _row("A2"), _row("A3")])
    with pytest.raises(UEF8PairIdentityCollisionError):
        uef8_fair_comparison.analyze_fair_comparisons(board, uef8_implementation_digest_value=_IMPL_DIGEST)


def test_pair_id_g_input_row_permutation_preserves_pair_ids_and_run_id():
    rows_forward = [_row("A1"), _row("A2"), _row("A3"), _row("A4")]
    rows_reversed = list(reversed(rows_forward))
    run_forward = _analyze(_board(rows_forward))
    run_reversed = _analyze(_board(rows_reversed))

    ids_forward = sorted(p.comparison_pair_id for p in run_forward.pairs)
    ids_reversed = sorted(p.comparison_pair_id for p in run_reversed.pairs)
    assert ids_forward == ids_reversed
    assert run_forward.uef8_run_id == run_reversed.uef8_run_id
    assert [p.to_dict() for p in run_forward.pairs] == [p.to_dict() for p in run_reversed.pairs]


def test_run_identity_implementation_digest_mutation_changes_run_id():
    kwargs = dict(
        source_uef7_run_id="UEF7RUN_x", uef7_normalized_semantic_digest="digest_x",
        schema_version="uef8.fair_comparison.v1", fair_comparison_policy_version="uef8_fair_comparison_policy.v1",
    )
    id_a = compute_uef8_run_id(uef8_implementation_digest_value="impl_a", **kwargs)
    id_b = compute_uef8_run_id(uef8_implementation_digest_value="impl_b", **kwargs)
    assert id_a != id_b


# ---------------------------------------------------------------------------
# V. Real frozen Board regression
# ---------------------------------------------------------------------------


def test_v_real_board_regression():
    real_board = build_alpha_research_board(reports_root=_ROOT / "reports", through_day="2026-09-25")
    normalized = normalize_alpha_board(real_board, normalizer_implementation_digest_value=uef7_impl_digest())
    run = _analyze(normalized.to_dict())

    assert run.candidate_count == 14
    assert run.summary.pair_count == 14 * 13 // 2 == 91
    assert run.summary.pair_count == run.summary.comparable_count + run.summary.conditional_count + run.summary.not_comparable_count

    # COMPARABLE is unconditionally 0 under the current UEF-7 schema (a
    # schema-contract property, not merely today's data) -- asserted
    # exactly, not just >= 0, per the Population Relation Authority
    # Bounded Fix.
    assert run.summary.comparable_count == 0

    # POPULATION_RELATION_NOT_PROVEN is unconditional under the current
    # schema, so it fires for every single pair (never a hardcoded
    # assumption -- derived from pair_count itself).
    assert run.summary.reason_counts["POPULATION_RELATION_NOT_PROVEN"] == run.summary.pair_count

    # Same-question same-horizon pairs are the only structurally-plausible
    # near-comparable candidates; confirm the real, dynamically-derived
    # reason still blocks every one of them.
    same_scope_pairs = [
        p for p in run.pairs
        if p.question_id_left == p.question_id_right and p.target_horizon_left == p.target_horizon_right
    ]
    assert same_scope_pairs  # sanity: the board actually has some same-scope pairs
    for p in same_scope_pairs:
        assert "POPULATION_RELATION_NOT_PROVEN" in p.comparison_reasons
        assert p.comparison_status != COMPARABLE


def test_comparable_reachable_with_current_uef7_schema_is_no_schema_contract():
    # Population Relation Authority Bounded Fix item 3-4: unreachability is
    # a SCHEMA CONTRACT property, not merely an observation about today's
    # real data. Confirmed two ways: (1) the real production normalizer's
    # actual output (every row NOT_PROVABLE_FROM_ALPHA_BOARD_V2), and (2)
    # the best-case synthetic schema-valid fixture (both sides individually
    # DIRECT_POPULATION_IDENTITY_PROVEN, everything else aligned) still
    # never reaches COMPARABLE -- see
    # test_d_comparable_unreachable_for_best_case_current_schema_valid_input.
    real_board = build_alpha_research_board(reports_root=_ROOT / "reports", through_day="2026-09-25")
    normalized = normalize_alpha_board(real_board, normalizer_implementation_digest_value=uef7_impl_digest())
    statuses = {row["population_identity_status"] for row in normalized.to_dict()["normalized_rows"]}
    assert statuses == {"NOT_PROVABLE_FROM_ALPHA_BOARD_V2"}
    real_run = _analyze(normalized.to_dict())
    assert real_run.summary.comparable_count == 0
