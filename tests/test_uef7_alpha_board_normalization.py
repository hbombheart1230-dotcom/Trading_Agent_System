"""UEF-7 Alpha Board Normalization tests.

Pure-logic tests build small synthetic Alpha Board v2-shaped payloads
(never a real ``build_alpha_research_board`` call, to keep them fast and
isolated -- see item 30/31). The single real-board regression (T) is the
only test that calls the real live board.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.alpha_research_board.contracts import ROW_COLUMNS
from libs.reporting.evaluation.uef7.alpha_board_normalization import (
    UEF7InputContractError,
    normalize_alpha_board,
)
from libs.reporting.evaluation.uef7.model import (
    INDEPENDENCE_NOT_PROVEN,
    POPULATION_NOT_PROVABLE,
)
from libs.reporting.evaluation.uef7.run_identity import (
    alpha_board_semantic_digest,
    compute_uef7_run_id,
    normalizer_implementation_digest,
)

_IMPL_DIGEST = normalizer_implementation_digest()

_ROOT = Path(__file__).resolve().parents[1]


def _row(candidate_id, *, question_id="A", target_horizon="+30m", status="DISCOVERY",
         operation_status="SHADOW_CONTINUES", fixed_validation_status="FIXED_VALIDATION_NOT_YET_RUN",
         production_promotion_status="PRODUCTION_PROMOTION_NOT_ALLOWED", decision="INSUFFICIENT_EVIDENCE",
         sample_count=10, win_rate=0.5, source_artifacts=None, cohort="historical"):
    return {
        "question_id": question_id,
        "candidate_id": candidate_id,
        "status": status,
        "hypothesis": "h",
        "feature_evidence": {},
        "target_horizon": target_horizon,
        "historical_evidence": {},
        "prospective_evidence": {},
        "sample_quality": {},
        "concentration": {},
        "net_metrics": {
            "cohort": cohort, "sample_count": sample_count, "window_count": sample_count,
            "win_rate": win_rate, "avg_net_return_pct": 0.1, "profit_factor": 1.2,
            "max_drawdown_pct": -0.05, "coverage": 0.9, "avg_mfe_pct": 0.2, "avg_mae_pct": -0.1,
        },
        "agent_attribution": {},
        "decision": decision,
        "rationale": "r",
        "next_action": "n",
        "source_artifacts": source_artifacts if source_artifacts is not None else [
            {"source_key": "src1", "path": "evaluation/foo.json", "available": True, "error": None}
        ],
        "updated_through_day": "2026-09-25",
        "operation_status": operation_status,
        "fixed_validation_status": fixed_validation_status,
        "production_promotion_status": production_promotion_status,
    }


def _board(rows, *, schema_version="alpha_research_board.v2", integrity_status="PASS", candidate_count=None,
           row_columns=None):
    candidate_ids = [r["candidate_id"] for r in rows]
    return {
        "schema_version": schema_version,
        "contract_version": "abc_fixed_2026_08_27",
        "through_day": "2026-09-25",
        "candidate_count": candidate_count if candidate_count is not None else len(rows),
        "candidate_ids": candidate_ids,
        "row_columns": list(row_columns) if row_columns is not None else list(ROW_COLUMNS),
        "candidates": rows,
        "integrity": {"status": integrity_status},
    }


def _normalize(board):
    return normalize_alpha_board(board, normalizer_implementation_digest_value=_IMPL_DIGEST)


# ---------------------------------------------------------------------------
# A. Row preservation
# ---------------------------------------------------------------------------


def test_a_row_count_preserved():
    board = _board([_row("X1"), _row("X2"), _row("X3")])
    normalized = _normalize(board)
    assert normalized.candidate_row_count == 3
    assert len(normalized.normalized_rows) == 3


# ---------------------------------------------------------------------------
# B. Candidate order preserved
# ---------------------------------------------------------------------------


def test_b_candidate_order_preserved_no_reordering():
    board = _board([_row("Z"), _row("A"), _row("M")])
    normalized = _normalize(board)
    assert normalized.candidate_ids == ("Z", "A", "M")


# ---------------------------------------------------------------------------
# C. Metric preservation
# ---------------------------------------------------------------------------


def test_c_metric_values_preserved_verbatim():
    board = _board([_row("X1", sample_count=42, win_rate=0.66, cohort="prospective")])
    row = _normalize(board).normalized_rows[0]
    assert row.evidence_cohort == "prospective"
    assert row.sample_count == 42
    assert row.win_rate == 0.66
    assert row.avg_net_return_pct == 0.1
    assert row.profit_factor == 1.2
    assert row.max_drawdown_pct == -0.05
    assert row.coverage == 0.9
    assert row.avg_mfe_pct == 0.2
    assert row.avg_mae_pct == -0.1


# ---------------------------------------------------------------------------
# D. None stays None -- never invented as 0
# ---------------------------------------------------------------------------


def test_d_missing_metric_stays_none_never_zero():
    row_dict = _row("X1")
    row_dict["net_metrics"] = {"cohort": None, "sample_count": 0, "window_count": 0, "win_rate": None,
                                "avg_net_return_pct": None, "profit_factor": None, "max_drawdown_pct": None,
                                "coverage": None, "avg_mfe_pct": None, "avg_mae_pct": None}
    board = _board([row_dict])
    row = _normalize(board).normalized_rows[0]
    assert row.win_rate is None
    assert row.profit_factor is None
    assert row.max_drawdown_pct is None
    assert row.evidence_cohort is None
    assert row.sample_count == 0  # 0 preserved as-is (not invented, not converted)


# ---------------------------------------------------------------------------
# E. Operation truth preservation
# ---------------------------------------------------------------------------


def test_e_operation_truth_fields_exact_equality():
    board = _board([_row(
        "X1", status="PROMOTED", operation_status="CONTROLLED_MOCK_CONTINUES",
        fixed_validation_status="FIXED_VALIDATION_PASSED",
        production_promotion_status="PRODUCTION_PROMOTION_ALLOWED", decision="PROMOTED",
    )])
    row = _normalize(board).normalized_rows[0]
    assert row.status == "PROMOTED"
    assert row.operation_status == "CONTROLLED_MOCK_CONTINUES"
    assert row.fixed_validation_status == "FIXED_VALIDATION_PASSED"
    assert row.production_promotion_status == "PRODUCTION_PROMOTION_ALLOWED"
    assert row.decision == "PROMOTED"


# ---------------------------------------------------------------------------
# F. Shared source group
# ---------------------------------------------------------------------------


def test_f_two_candidates_same_source_one_shared_group():
    same_src = [{"source_key": "shared", "path": "evaluation/shared.json", "available": True, "error": None}]
    board = _board([_row("X1", source_artifacts=same_src), _row("X2", source_artifacts=same_src), _row("X3")])
    normalized = _normalize(board)
    assert len(normalized.source_groups) == 1
    group = normalized.source_groups[0]
    assert group.candidate_count == 2
    assert set(group.candidate_ids) == {"X1", "X2"}


# ---------------------------------------------------------------------------
# G. Shared source != population equality
# ---------------------------------------------------------------------------


def test_g_shared_source_never_sets_proven_shared_population():
    same_src = [{"source_key": "shared", "path": "evaluation/shared.json", "available": True, "error": None}]
    board = _board([_row("X1", source_artifacts=same_src), _row("X2", source_artifacts=same_src)])
    normalized = _normalize(board)
    for row in normalized.normalized_rows:
        assert row.shared_source_group_ids  # confirmed shared
        assert row.evidence_independence_status == INDEPENDENCE_NOT_PROVEN
        assert row.evidence_independence_status != "PROVEN_SHARED_POPULATION"


# ---------------------------------------------------------------------------
# H. Different sources != proven independence
# ---------------------------------------------------------------------------


def test_h_different_sources_remain_independence_not_proven():
    board = _board([
        _row("X1", source_artifacts=[{"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None}]),
        _row("X2", source_artifacts=[{"source_key": "b", "path": "evaluation/b.json", "available": True, "error": None}]),
    ])
    normalized = _normalize(board)
    for row in normalized.normalized_rows:
        assert row.evidence_independence_status == INDEPENDENCE_NOT_PROVEN
        assert row.evidence_independence_status != "INDEPENDENT"


# ---------------------------------------------------------------------------
# I. Same source bundle, different order -> same source_bundle_id
# ---------------------------------------------------------------------------


def test_i_source_bundle_id_order_invariant():
    refs_ab = [
        {"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None},
        {"source_key": "b", "path": "evaluation/b.json", "available": True, "error": None},
    ]
    refs_ba = list(reversed(refs_ab))
    board = _board([_row("X1", source_artifacts=refs_ab), _row("X2", source_artifacts=refs_ba)])
    normalized = _normalize(board)
    rows = {r.candidate_id: r for r in normalized.normalized_rows}
    assert rows["X1"].source_bundle_id == rows["X2"].source_bundle_id


# ---------------------------------------------------------------------------
# J. Source bundle mutation -> different source_bundle_id
# ---------------------------------------------------------------------------


def test_j_source_bundle_id_mutation_sensitive():
    refs_a = [{"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None}]
    refs_a_changed = [{"source_key": "a", "path": "evaluation/a_v2.json", "available": True, "error": None}]
    board = _board([_row("X1", source_artifacts=refs_a), _row("X2", source_artifacts=refs_a_changed)])
    normalized = _normalize(board)
    rows = {r.candidate_id: r for r in normalized.normalized_rows}
    assert rows["X1"].source_bundle_id != rows["X2"].source_bundle_id


# ---------------------------------------------------------------------------
# K. Duplicate source occurrence -- multiplicity/anomaly retained
# ---------------------------------------------------------------------------


def test_k_duplicate_source_reference_retained_and_flagged():
    dup_refs = [
        {"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None},
        {"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None},
    ]
    board = _board([_row("X1", source_artifacts=dup_refs)])
    row = _normalize(board).normalized_rows[0]
    assert len(row.source_references) == 2  # never silently collapsed
    assert any(a.startswith("DUPLICATE_SOURCE_REFERENCE:") for a in row.source_anomalies)


# ---------------------------------------------------------------------------
# L. Missing source -- fail-honest normalization status, not a crash
# ---------------------------------------------------------------------------


def test_l_missing_source_reference_reported_honestly():
    board = _board([_row("X1", source_artifacts=[])])
    row = _normalize(board).normalized_rows[0]
    assert row.source_references == ()
    assert any(a.startswith("MISSING_SOURCE_REFERENCE:") for a in row.source_anomalies)


def test_l2_unavailable_and_error_sources_reported():
    board = _board([_row("X1", source_artifacts=[
        {"source_key": "a", "path": "evaluation/a.json", "available": False, "error": "MISSING_ARTIFACT"},
    ])])
    row = _normalize(board).normalized_rows[0]
    assert any(a.startswith("UNAVAILABLE_SOURCE:") for a in row.source_anomalies)
    assert any(a.startswith("SOURCE_ERROR:") for a in row.source_anomalies)


# ---------------------------------------------------------------------------
# M. Duplicate candidate ID -- reject
# ---------------------------------------------------------------------------


def test_m_duplicate_candidate_id_rejected():
    board = _board([_row("X1"), _row("X1")])
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


# ---------------------------------------------------------------------------
# N. Candidate count mismatch -- reject
# ---------------------------------------------------------------------------


def test_n_candidate_count_mismatch_rejected():
    board = _board([_row("X1"), _row("X2")], candidate_count=99)
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


# ---------------------------------------------------------------------------
# O. Frozen Board FAIL_CONTRACT input -- reject
# ---------------------------------------------------------------------------


def test_o_fail_contract_board_rejected():
    board = _board([_row("X1")], integrity_status="FAIL_CONTRACT")
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


def test_o2_wrong_schema_version_rejected():
    board = _board([_row("X1")], schema_version="alpha_research_board.v1")
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


# ---------------------------------------------------------------------------
# Codex Final Single-HIGH Correction: candidate rows must match the Board's
# own published row_columns contract EXACTLY (key set, not insertion
# order) -- neither a missing field nor a contract-external extra field is
# ever silently accepted into normalization or run identity.
# ---------------------------------------------------------------------------


def test_extra_candidate_field_rejected_before_digest_or_normalization():
    row = _row("X1")
    row["external_debug_field"] = "x"
    board = _board([row])

    digest_before = alpha_board_semantic_digest(_board([_row("X1")]))
    with pytest.raises(UEF7InputContractError):
        _normalize(board)
    # The invalid row must never reach digest/run-id/normalized-row
    # production -- re-computing the digest of a KNOWN-valid board must
    # still work and be unaffected by the rejected attempt above.
    assert alpha_board_semantic_digest(_board([_row("X1")])) == digest_before


def test_missing_candidate_field_rejected():
    row = _row("X1")
    del row["decision"]
    board = _board([row])
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


def test_adversarial_row_columns_and_row_extension_in_lockstep_rejected():
    # The exact Codex adversarial case: extend board["row_columns"] AND
    # every candidate row with the SAME external field, so a naive
    # "candidate keys == board.row_columns" check would wrongly accept it.
    # Only the FROZEN, imported ROW_COLUMNS is trusted -- this must still
    # reject, and reject before the field can ever reach the Board
    # semantic digest or run id.
    row = _row("X1")
    row["external_debug_field"] = "x"
    board = _board([row], row_columns=list(ROW_COLUMNS) + ["external_debug_field"])

    digest_before = alpha_board_semantic_digest(_board([_row("X1")]))
    with pytest.raises(UEF7InputContractError):
        _normalize(board)
    assert alpha_board_semantic_digest(_board([_row("X1")])) == digest_before


def test_board_row_columns_extra_field_rejected():
    board = _board([_row("X1")], row_columns=list(ROW_COLUMNS) + ["extra_column"])
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


def test_board_row_columns_missing_field_rejected():
    truncated = [c for c in ROW_COLUMNS if c != "decision"]
    board = _board([_row("X1")], row_columns=truncated)
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


def test_board_row_columns_reordered_rejected():
    reordered = list(reversed(ROW_COLUMNS))
    assert set(reordered) == set(ROW_COLUMNS)
    assert reordered != list(ROW_COLUMNS)
    board = _board([_row("X1")], row_columns=reordered)
    with pytest.raises(UEF7InputContractError):
        _normalize(board)


def test_candidate_row_key_insertion_order_invariant():
    row_in_order = _row("X1")
    row_reordered = dict(reversed(list(row_in_order.items())))
    assert set(row_reordered.keys()) == set(row_in_order.keys())
    assert list(row_reordered.keys()) != list(row_in_order.keys())  # genuinely different insertion order

    board_a = _board([row_in_order])
    board_b = _board([row_reordered])
    normalized_a = _normalize(board_a)
    normalized_b = _normalize(board_b)
    assert normalized_a.uef7_run_id == normalized_b.uef7_run_id
    assert normalized_a.to_dict() == normalized_b.to_dict()


# ---------------------------------------------------------------------------
# P. No ranking fields
# ---------------------------------------------------------------------------


def test_p_no_ranking_fields_present():
    board = _board([_row("X1"), _row("X2")])
    normalized = _normalize(board)
    payload = normalized.to_dict()
    forbidden = ("score", "rank", "tier", "winner", "best_candidate", "promotion_recommendation")
    top_level_keys = {k.lower() for k in payload.keys()}
    for name in forbidden:
        assert name not in top_level_keys
    for row in payload["normalized_rows"]:
        row_keys = {k.lower() for k in row.keys()}
        for name in forbidden:
            assert name not in row_keys


# ---------------------------------------------------------------------------
# Q. Run identity deterministic
# ---------------------------------------------------------------------------


def test_q_run_id_deterministic_same_board():
    board = _board([_row("X1"), _row("X2")])
    run_id_1 = _normalize(copy.deepcopy(board)).uef7_run_id
    run_id_2 = _normalize(copy.deepcopy(board)).uef7_run_id
    assert run_id_1 == run_id_2


# ---------------------------------------------------------------------------
# R. Board semantic mutation -> run id changes
# ---------------------------------------------------------------------------


def test_r_board_mutation_changes_run_id():
    board_a = _board([_row("X1", win_rate=0.5)])
    board_b = _board([_row("X1", win_rate=0.51)])
    assert _normalize(board_a).uef7_run_id != _normalize(board_b).uef7_run_id


# ---------------------------------------------------------------------------
# S. Implementation mutation -> run id changes
# ---------------------------------------------------------------------------


def test_s_implementation_digest_mutation_changes_run_id():
    board = _board([_row("X1")])
    digest = alpha_board_semantic_digest(board)
    run_id_a = compute_uef7_run_id(
        source_board_semantic_digest=digest, normalizer_implementation_digest_value="impl_a",
        normalization_schema_version="uef7.alpha_board_normalization.v1",
    )
    run_id_b = compute_uef7_run_id(
        source_board_semantic_digest=digest, normalizer_implementation_digest_value="impl_b",
        normalization_schema_version="uef7.alpha_board_normalization.v1",
    )
    assert run_id_a != run_id_b


# ---------------------------------------------------------------------------
# Codex Bounded Correction -- Defect A: full SourceReference identity
# (source_key + path + available + error together), never a partial
# (source_key, path) key, for grouping / bundle id / duplicate detection.
# ---------------------------------------------------------------------------


def test_9a_available_mutation_changes_group_and_bundle_identity():
    ref_available = [{"source_key": "X", "path": "P", "available": True, "error": None}]
    ref_unavailable = [{"source_key": "X", "path": "P", "available": False, "error": None}]
    board = _board([_row("X1", source_artifacts=ref_available), _row("X2", source_artifacts=ref_unavailable)])
    normalized = _normalize(board)

    # Same source_key/path but different `available` must NEVER be grouped together.
    assert normalized.source_groups == ()
    rows = {r.candidate_id: r for r in normalized.normalized_rows}
    assert rows["X1"].source_bundle_id != rows["X2"].source_bundle_id


def test_9b_error_mutation_changes_group_and_bundle_identity():
    ref_error_a = [{"source_key": "X", "path": "P", "available": False, "error": "A"}]
    ref_error_b = [{"source_key": "X", "path": "P", "available": False, "error": "B"}]
    board = _board([_row("X1", source_artifacts=ref_error_a), _row("X2", source_artifacts=ref_error_b)])
    normalized = _normalize(board)

    assert normalized.source_groups == ()
    rows = {r.candidate_id: r for r in normalized.normalized_rows}
    assert rows["X1"].source_bundle_id != rows["X2"].source_bundle_id


def test_9c_exact_full_duplicate_multiplicity_preserved():
    exact_dup = [
        {"source_key": "X", "path": "P", "available": True, "error": None},
        {"source_key": "X", "path": "P", "available": True, "error": None},
    ]
    board = _board([_row("X1", source_artifacts=exact_dup)])
    row = _normalize(board).normalized_rows[0]
    assert len(row.source_references) == 2
    assert any(a.startswith("DUPLICATE_SOURCE_REFERENCE:") for a in row.source_anomalies)


def test_9_same_full_reference_still_groups_together():
    # Positive control: two rows citing the IDENTICAL full reference (all
    # four fields equal) must still share one group -- Defect A only
    # requires the key to be FULL, not that grouping stops working.
    same_ref = [{"source_key": "X", "path": "P", "available": True, "error": None}]
    board = _board([_row("X1", source_artifacts=same_ref), _row("X2", source_artifacts=same_ref)])
    normalized = _normalize(board)
    assert len(normalized.source_groups) == 1
    assert normalized.source_groups[0].candidate_count == 2


# ---------------------------------------------------------------------------
# Codex Bounded Correction -- Defect B: Board semantic digest computed from
# the explicit Alpha Board v2 contract surface only, never the raw input
# mapping (a contract-external top-level field must never influence it).
# ---------------------------------------------------------------------------


def test_10d_generated_at_external_field_invariant():
    board_a = _board([_row("X1")])
    board_b = dict(board_a)
    board_b["generated_at"] = "2026-09-29T00:00:00Z"

    normalized_a = _normalize(board_a)
    normalized_b = _normalize(board_b)
    assert normalized_a.source_board_semantic_digest == normalized_b.source_board_semantic_digest
    assert normalized_a.uef7_run_id == normalized_b.uef7_run_id
    # Full semantic normalization result (minus nothing) is identical too --
    # the external field must never silently influence normalization while
    # being excluded from the digest (item 6).
    assert normalized_a.to_dict() == normalized_b.to_dict()


def test_10e_arbitrary_extra_field_invariant():
    board_a = _board([_row("X1")])
    board_b = dict(board_a)
    board_b["some_external_debug_field"] = {"nested": [1, 2, 3], "note": "not part of the contract"}

    normalized_a = _normalize(board_a)
    normalized_b = _normalize(board_b)
    assert normalized_a.source_board_semantic_digest == normalized_b.source_board_semantic_digest
    assert normalized_a.uef7_run_id == normalized_b.uef7_run_id
    assert normalized_a.to_dict() == normalized_b.to_dict()


def test_10f_semantic_candidate_decision_mutation_changes_digest():
    board_a = _board([_row("X1", decision="INSUFFICIENT_EVIDENCE")])
    board_b = _board([_row("X1", decision="PROMOTED")])
    assert alpha_board_semantic_digest(board_a) != alpha_board_semantic_digest(board_b)
    assert _normalize(board_a).uef7_run_id != _normalize(board_b).uef7_run_id


def test_10g_source_reference_semantic_mutation_changes_board_digest():
    board_a = _board([_row("X1", source_artifacts=[{"source_key": "a", "path": "evaluation/a.json", "available": True, "error": None}])])
    board_b = _board([_row("X1", source_artifacts=[{"source_key": "a", "path": "evaluation/a.json", "available": False, "error": "MISSING_ARTIFACT"}])])
    assert alpha_board_semantic_digest(board_a) != alpha_board_semantic_digest(board_b)
    assert _normalize(board_a).uef7_run_id != _normalize(board_b).uef7_run_id


def test_10h_through_day_mutation_changes_digest():
    board_a = _board([_row("X1")])
    board_a["through_day"] = "2026-09-25"
    board_b = _board([_row("X1")])
    board_b["through_day"] = "2026-09-26"
    assert alpha_board_semantic_digest(board_a) != alpha_board_semantic_digest(board_b)
    assert _normalize(board_a).uef7_run_id != _normalize(board_b).uef7_run_id


# ---------------------------------------------------------------------------
# T. Current real Board regression (dynamic shared-source groups)
# ---------------------------------------------------------------------------


def test_t_real_board_regression_dynamic_shared_source_groups():
    board = build_alpha_research_board(reports_root=_ROOT / "reports", through_day="2026-09-25")
    normalized = _normalize(board)

    assert normalized.candidate_row_count == board["candidate_count"] == 14
    assert normalized.candidate_ids == tuple(board["candidate_ids"])  # order preserved

    groups_by_key = {g.source_key: set(g.candidate_ids) for g in normalized.source_groups}
    assert normalized.normalization_summary.shared_source_group_count == len(normalized.source_groups)
    assert normalized.normalization_summary.candidate_row_count == 14

    # Dynamic (not hardcoded) real-board fact recorded per item 27/T: the
    # four opening candidates currently share opening_cumulative provenance.
    if "opening_cumulative" in groups_by_key:
        opening_group = groups_by_key["opening_cumulative"]
        assert {"IMMEDIATE_OPENING_PROBE", "CONFIRMED_RECURRENT_RANK", "DISLOCATION_REBOUND", "OPEN_0_20_RANK1_30M"} <= opening_group
        # R1_SCANNER_RISK_HIGH_30M_V1 currently comes from feature_candidates/
        # prospective_candidates, never opening_cumulative (item 11) -- no
        # hardcoded assumption otherwise.
        assert "R1_SCANNER_RISK_HIGH_30M_V1" not in opening_group

    for row in normalized.normalized_rows:
        assert row.population_identity_status == POPULATION_NOT_PROVABLE
        assert row.evidence_independence_status == INDEPENDENCE_NOT_PROVEN
