"""Focused contracts for UEF-9 formal authority binding."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest
from libs.reporting.evaluation.uef8.fair_comparison import analyze_fair_comparisons
from libs.reporting.evaluation.uef8.run_identity import (
    compute_uef8_run_id,
    uef7_normalized_rows_semantic_digest,
    uef8_implementation_digest,
)
from libs.reporting.evaluation.uef9.authority import verify_formal_evaluation_authority
from libs.reporting.evaluation.uef9.model import UEF9AuthorityError, VALID


ROOT = Path(__file__).resolve().parents[1]
IMPL = "uef9-test-implementation"


def _base_inputs():
    board = build_alpha_research_board(reports_root=ROOT / "reports", through_day="2026-09-25")
    uef7 = normalize_alpha_board(board, normalizer_implementation_digest_value=normalizer_implementation_digest()).to_dict()
    uef8 = analyze_fair_comparisons(uef7, uef8_implementation_digest_value=uef8_implementation_digest()).to_dict()
    return uef7, uef8


@pytest.fixture()
def inputs():
    return _base_inputs()


def _verify(uef7, uef8, *, impl=IMPL):
    return verify_formal_evaluation_authority(uef7, uef8=uef8, uef9_implementation_digest_value=impl)


def _refresh_uef8_binding(uef7, uef8):
    digest = uef7_normalized_rows_semantic_digest(uef7["normalized_rows"])
    uef8["source_uef7_run_id"] = uef7["uef7_run_id"]
    uef8["source_uef7_through_day"] = uef7["through_day"]
    uef8["uef7_normalized_semantic_digest"] = digest
    uef8["uef8_run_id"] = compute_uef8_run_id(
        source_uef7_run_id=uef8["source_uef7_run_id"],
        uef7_normalized_semantic_digest=digest,
        uef8_implementation_digest_value=uef8["uef8_implementation_digest"],
        schema_version=uef8["schema_version"],
        fair_comparison_policy_version=uef8["fair_comparison_policy_version"],
    )


def test_a_valid_current_authority(inputs):
    authority = _verify(*inputs)
    assert authority.authority_status == VALID
    assert authority.candidate_count == 14
    assert authority.pair_count == 91
    assert authority.comparison_status_counts == {"COMPARABLE": 0, "CONDITIONAL": 7, "NOT_COMPARABLE": 84}


@pytest.mark.parametrize("mutator", [
    lambda u7, u8: u8.__setitem__("source_uef7_run_id", "UEF7RUN_wrong"),
    lambda u7, u8: u8.__setitem__("uef7_normalized_semantic_digest", "wrong"),
    lambda u7, u8: u8.__setitem__("candidate_count", 99),
    lambda u7, u8: u8.__setitem__("candidate_ids", u8["candidate_ids"][1:]),
    lambda u7, u8: u7["normalized_rows"].append(copy.deepcopy(u7["normalized_rows"][0])),
    lambda u7, u8: u8.__setitem__("pairs", u8["pairs"][:-1]),
    lambda u7, u8: u8["pairs"][0].__setitem__("left_candidate_id", "UNKNOWN"),
    lambda u7, u8: u8["pairs"][0].__setitem__("right_candidate_id", u8["pairs"][0]["left_candidate_id"]),
    lambda u7, u8: u8["pairs"].__setitem__(1, copy.deepcopy(u8["pairs"][0])),
    lambda u7, u8: u8["pairs"][1].__setitem__("comparison_pair_id", u8["pairs"][0]["comparison_pair_id"]),
    lambda u7, u8: u8["summary"].__setitem__("conditional_count", 99),
    lambda u7, u8: u8["pairs"][0].__setitem__("comparison_status", "UNKNOWN"),
    lambda u7, u8: u8["pairs"][0].__setitem__("comparison_status", "COMPARABLE"),
])
def test_b_structural_contradictions_fail_closed(inputs, mutator):
    uef7, uef8 = copy.deepcopy(inputs)
    mutator(uef7, uef8)
    with pytest.raises(UEF9AuthorityError):
        _verify(uef7, uef8)


def test_b2_capability_contradiction_isolated_from_summary_mismatch(inputs):
    # Item N's exact scenario, isolated from the more general "summary
    # count mismatch" guard: an otherwise INTERNALLY SELF-CONSISTENT UEF-8
    # payload (pair status AND summary counts agree with each other) that
    # claims one COMPARABLE pair. The per-status summary cross-check alone
    # would NOT catch this (summary and pairs agree), so this isolates
    # the dedicated "current UEF-7 schema declares COMPARABLE unreachable"
    # capability-contradiction guard as the actual reason for failure.
    uef7, uef8 = copy.deepcopy(inputs)
    original_status = uef8["pairs"][0]["comparison_status"]
    assert original_status in ("CONDITIONAL", "NOT_COMPARABLE")
    uef8["pairs"][0]["comparison_status"] = "COMPARABLE"
    uef8["pairs"][0]["comparison_reasons"] = []
    uef8["summary"]["comparable_count"] += 1
    uef8["summary"][f"{original_status.lower()}_count"] -= 1
    with pytest.raises(UEF9AuthorityError, match="COMPARABLE unreachable"):
        _verify(uef7, uef8)


def test_c_candidate_and_pair_order_are_nonsemantic(inputs):
    uef7, uef8 = inputs
    baseline = _verify(uef7, uef8)
    reordered_uef7, reordered_uef8 = copy.deepcopy((uef7, uef8))
    reordered_uef7["normalized_rows"].reverse()
    reordered_uef7["candidate_ids"].reverse()
    reordered_uef8["candidate_ids"].reverse()
    reordered_uef8["pairs"].reverse()
    reordered = _verify(reordered_uef7, reordered_uef8)
    assert reordered.candidate_ids_digest == baseline.candidate_ids_digest
    assert reordered.comparison_pair_ids_digest == baseline.comparison_pair_ids_digest
    assert reordered.uef9_run_id == baseline.uef9_run_id


def test_d_semantic_upstream_mutations_change_run_identity(inputs):
    uef7, uef8 = inputs
    baseline = _verify(uef7, uef8)
    changed_uef7, changed_uef8 = copy.deepcopy((uef7, uef8))
    changed_uef7["normalized_rows"][0]["win_rate"] = 0.123456
    _refresh_uef8_binding(changed_uef7, changed_uef8)
    assert _verify(changed_uef7, changed_uef8).uef9_run_id != baseline.uef9_run_id

    changed_uef8 = copy.deepcopy(uef8)
    changed_uef8["pairs"][0]["comparison_reasons"] = ["SYNTHETIC_AUDIT_MUTATION"]
    assert _verify(uef7, changed_uef8).uef9_run_id != baseline.uef9_run_id


def test_e_implementation_digest_changes_run_identity(inputs):
    assert _verify(*inputs, impl="implementation-a").uef9_run_id != _verify(*inputs, impl="implementation-b").uef9_run_id


def test_f_no_ranking_or_execution_authority(inputs):
    payload = _verify(*inputs).to_dict()
    assert payload["prohibitions"] == {
        "ranking_authority": "NONE",
        "promotion_authority": "NONE",
        "trading_execution_authority": "NONE",
    }
    forbidden = {"score", "rank", "winner", "loser", "promotion_recommendation", "strategy_recommendation", "return_delta", "pf_delta"}

    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key.lower() not in forbidden
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(payload)


def test_g_uef8_native_digest_is_explicitly_unavailable(inputs):
    authority = _verify(*inputs)
    assert authority.source_uef8_native_semantic_digest_available is False
    assert authority.uef9_derived_uef8_authority_digest
