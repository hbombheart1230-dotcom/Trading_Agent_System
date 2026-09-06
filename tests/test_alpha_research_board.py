from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.alpha_research_board import (
    build_alpha_research_board,
    write_alpha_research_board,
)
from libs.reporting.alpha_research_board.contracts import (
    CANDIDATE_IDS,
    FEATURE_COLUMNS,
    ROW_COLUMNS,
)
from libs.reporting.alpha_research_board.sensitivity import evaluate_risk_high_sensitivity
from libs.reporting.alpha_research_board.remaining_reviews import evaluate_bounded_candidate
from libs.reporting.alpha_research_board.runtime_validation import (
    build_immediate_opening_runtime_validation,
)
from libs.reporting.alpha_research_board.canonical import canonicalize_board


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture_reports(tmp_path: Path) -> Path:
    root = tmp_path / "reports"
    feature = {
        "schema_version": "fixture",
        "prospective_shadow_candidates": [
            {
                "feature": "scanner.risk_band",
                "category": "HIGH",
                "target": "+30m",
                "train": {"day_symbol_count": 24, "win_rate": 0.58, "avg_net_return_pct": 1.4},
                "validation": {"day_symbol_count": 18, "win_rate": 0.5, "avg_net_return_pct": 1.2},
            },
            {
                "feature": "chart.daily_ma5_20_cross_state",
                "category": "POST_CROSS_EXTENDED",
                "target": "+15m",
                "train": {"day_symbol_count": 10, "win_rate": 0.8, "avg_net_return_pct": 3.5},
                "validation": {"day_symbol_count": 7, "win_rate": 0.71, "avg_net_return_pct": 0.88},
            },
        ],
    }
    prospective = {
        "schema_version": "fixture",
        "candidate_summaries": [
            {
                "candidate": {
                    "candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1",
                    "feature_path": "scanner.risk_band",
                    "expected_value": "HIGH",
                },
                "branch": {"day_symbol_count": 21, "win_rate": 0.48, "avg_net_return_pct": 0.92},
                "decision": {"status": "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE"},
            },
            {
                "candidate": {
                    "candidate_id": "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
                    "feature_path": "chart.daily_ma5_20_cross_state",
                    "expected_value": "POST_CROSS_EXTENDED",
                },
                "branch": {"day_symbol_count": 8, "win_rate": 0.25, "avg_net_return_pct": -1.62},
                "decision": {"status": "RETAIN_SHADOW_INSUFFICIENT_BRANCH_SAMPLE"},
            },
        ],
    }
    prospective_contract = {
        "schema_version": "fixture",
        "first_eligible_day": "2026-08-12",
    }
    opening = {
        "schema_version": "fixture",
        "summary": {
            "conditional_lane_summaries": {
                lane: {
                    "horizons": {
                        horizon: {
                            "live_net": {
                                "count": count,
                                "win_rate": 0.6,
                                "average_return_pct": 1.0,
                                "profit_factor": 2.0,
                            }
                        }
                    }
                }
                for lane, horizon, count in [
                    ("IMMEDIATE_OPENING_PROBE", "+5m", 12),
                    ("CONFIRMED_RECURRENT_RANK", "+30m", 2),
                    ("DISLOCATION_REBOUND", "+60m", 7),
                ]
            }
        },
        "promotion_decision": {
            "status": "REJECTED",
            "values": {
                "observed_count": 61,
                "win_rate": 0.51,
                "average_net_return_pct": 1.15,
                "profit_factor": 2.28,
                "coverage": 1.0,
                "largest_day_share": 0.13,
                "largest_symbol_share": 0.36,
            },
        },
    }
    fresh = {
        "schema_version": "fixture",
        "historical_reference": {"branch": {"horizons": {"+30m": {"observed_count": 7, "avg_net_return_pct": 4.5}}}},
        "branch": {"horizons": {"+30m": {"observed_count": 9, "avg_net_return_pct": -1.9}}},
        "decision": {"status": "MANUAL_SINGLE_PATCH_REVIEW_READY"},
    }
    latent = {
        "schema_version": "fixture",
        "summary": {
            "status": "REJECTED",
            "largest_day_share": 0.29,
            "largest_symbol_share": 0.43,
            "positive_day_ratio": 0.5,
            "horizons": {"+30m": {"live_net": {"count": 14, "win_rate": 0.64, "average_return_pct": 1.0, "profit_factor": 1.93}}},
        },
    }
    btc = {
        "schema_version": "fixture",
        "conclusion": "PROMISING_SUBSET_PROSPECTIVE_SHADOW_REQUIRED",
        "episode_horizons": [{"horizon": "+30m", "real_net": {"trade_count": 19, "win_rate": 0.68, "avg_return_pct": 0.53, "profit_factor": 3.12}}],
    }
    large = {
        "schema_version": "fixture",
        "summary": {"horizons": [{"horizon": "+180m", "top1_gross": {"count": 36, "win_rate": 0.72, "average_return_pct": 0.94, "profit_factor": 7.4}}]},
    }
    prospective_day_1 = {
        "schema_version": "fixture",
        "observations": [
            {"candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1", "day": "2026-08-12", "symbol": "005930", "matched": True},
            {"candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1", "day": "2026-08-12", "symbol": "000660", "matched": True},
        ],
    }
    prospective_day_2 = {
        "schema_version": "fixture",
        "observations": [
            {"candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1", "day": "2026-08-13", "symbol": "005930", "matched": True},
        ],
    }
    files = {
        "evaluation/feature_mart/opening_rank1/candidate_selection.json": feature,
        "evaluation/feature_mart/opening_rank1/prospective/rank1_candidate_shadow_cumulative.json": prospective,
        "evaluation/feature_mart/opening_rank1/prospective/frozen_candidate_contract.json": prospective_contract,
        "evaluation/feature_mart/opening_rank1/fresh_change_activation/fresh_change_activation_cumulative.json": fresh,
        "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json": opening,
        "evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json": latent,
        "evaluation/baseline_btc_woori_tech/historical/q12_v1_v2_historical_review.json": btc,
        "evaluation/baseline_samsung_hynix/2026-08-21/baseline_samsung_hynix_forward_returns.json": large,
        "evaluation/feature_mart/opening_rank1/prospective/2026-08-12/rank1_candidate_shadow_daily.json": prospective_day_1,
        "evaluation/feature_mart/opening_rank1/prospective/2026-08-13/rank1_candidate_shadow_daily.json": prospective_day_2,
    }
    for relative, payload in files.items():
        _write(root / relative, payload)
    return root


def test_board_keeps_closed_and_review_candidates_separate(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    by_id = {row["candidate_id"]: row for row in payload["candidates"]}
    assert payload["behavior_change_authorized"] is False
    assert [row["question_id"] for row in payload["questions"]] == ["A", "B", "C"]
    assert tuple(payload["candidate_ids"]) == CANDIDATE_IDS
    assert by_id["OPEN_0_20_RANK1_30M"]["status"] == "CLOSED"
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["status"] == "CLOSED"
    assert by_id["R1_FRESH_CHANGE_ACTIVATION_V1"]["status"] == "CLOSED"
    assert by_id["BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION"]["status"] == "CLOSED"
    assert by_id["BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1"]["status"] == "PROSPECTIVE"


def test_board_reads_q12_five_variable_prospective_metric(tmp_path: Path) -> None:
    reports_root = _fixture_reports(tmp_path)
    _write(
        reports_root
        / "evaluation"
        / "baseline_btc_woori_tech"
        / "hypothesis_validation"
        / "q12_btc_woori_hypothesis_cumulative.json",
        {
            "schema_version": "q12_btc_woori_hypothesis_cumulative.v1",
            "rows": [
                {
                    "evidence_phase": "PROSPECTIVE",
                    "axis": "hypothesis_path",
                    "value": "FAST_BUY_ALL_PASS",
                    "entry_method": "09:05",
                    "horizon": "+30m",
                    "metrics": {
                        "sample_count": 3,
                        "win_rate": 0.6667,
                        "avg_return_pct": 0.42,
                        "profit_factor": 2.1,
                        "max_drawdown_pct": -0.3,
                        "avg_mfe_pct": 0.9,
                        "avg_mae_pct": -0.2,
                    },
                }
            ],
        },
    )

    payload = build_alpha_research_board(
        reports_root=reports_root, through_day="2026-08-28"
    )
    row = next(
        value
        for value in payload["candidates"]
        if value["candidate_id"] == "BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1"
    )

    assert row["prospective_evidence"]["sample_count"] == 3
    assert row["prospective_evidence"]["avg_net_return_pct"] == 0.42
    assert any(
        source["source_key"] == "btc_woori_hypothesis"
        for source in row["source_artifacts"]
    )


def test_board_uses_day_symbol_sample_and_live_cost_basis(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    by_id = {row["candidate_id"]: row for row in payload["candidates"]}
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["prospective_evidence"]["sample_count"] == 21
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["concentration"]["largest_symbol_share"] == 0.6667
    assert by_id["SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1"]["prospective_evidence"]["avg_net_return_pct"] == 0.66
    assert payload["cost_authority"]["live_equity_round_trip_pct"] == 0.28


def test_large_cap_baseline_accumulates_independent_days(tmp_path: Path) -> None:
    reports_root = _fixture_reports(tmp_path)
    _write(
        reports_root
        / "evaluation"
        / "baseline_samsung_hynix"
        / "2026-08-24"
        / "baseline_samsung_hynix_forward_returns.json",
        {
            "schema_version": "fixture",
            "summary": {
                "horizons": [
                    {
                        "horizon": "+180m",
                        "top1_gross": {
                            "count": 40,
                            "average_return_pct": -2.2727,
                        },
                    }
                ]
            },
        },
    )
    payload = build_alpha_research_board(
        reports_root=reports_root, through_day="2026-08-24"
    )
    by_id = {row["candidate_id"]: row for row in payload["candidates"]}
    large = by_id["SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1"]

    assert large["prospective_evidence"]["sample_count"] == 2
    assert large["prospective_evidence"]["window_count"] == 76
    assert large["prospective_evidence"]["avg_net_return_pct"] == -0.9464


def test_board_reports_missing_sources_without_guessing(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=tmp_path / "missing", through_day="2026-08-21"
    )
    assert payload["integrity"]["status"] == "PASS_WITH_MISSING_SOURCES"
    assert payload["integrity"]["missing_or_invalid_sources"]


def test_board_writes_json_and_readable_markdown(tmp_path: Path) -> None:
    reports_root = _fixture_reports(tmp_path)
    result = write_alpha_research_board(
        reports_root=reports_root,
        through_day="2026-08-21",
        output_dir=tmp_path / "out",
    )
    markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
    assert "Top-Level Questions" in markdown
    assert "Candidate Board" in markdown
    assert "Closeout Summary" in markdown
    assert Path(result["sensitivity_markdown_path"]).exists()
    assert Path(result["remaining_markdown_path"]).exists()
    assert Path(result["runtime_markdown_path"]).exists()
    runtime = json.loads(Path(result["runtime_json_path"]).read_text(encoding="utf-8"))
    assert runtime
    assert runtime["schema_version"] == "immediate_opening_runtime_validation.v1"
    assert Path(result["latest_json_path"]).exists()
    assert Path(result["latest_markdown_path"]).exists()


def test_board_contract_columns_and_feature_surface_are_frozen(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    assert tuple(payload["row_columns"]) == ROW_COLUMNS
    assert tuple(payload["feature_columns"]) == FEATURE_COLUMNS
    for row in payload["candidates"]:
        assert tuple(row) == ROW_COLUMNS
        assert tuple(row["feature_evidence"]) == FEATURE_COLUMNS


def test_board_keeps_historical_and_prospective_separate(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    row = next(
        value
        for value in payload["candidates"]
        if value["candidate_id"] == "R1_SCANNER_RISK_HIGH_30M_V1"
    )
    assert row["historical_evidence"]["sample_count"] == 24
    assert row["prospective_evidence"]["sample_count"] == 21
    assert row["net_metrics"]["cohort"] == "prospective"


def test_board_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    reports_root = _fixture_reports(tmp_path)
    first = build_alpha_research_board(
        reports_root=reports_root, through_day="2026-08-21"
    )
    second = build_alpha_research_board(
        reports_root=reports_root, through_day="2026-08-21"
    )
    assert first == second


def test_sensitivity_rejects_single_symbol_profit_dependence() -> None:
    rows = []
    epoch = 1
    for day, value in [("2026-08-12", 10.0), ("2026-08-13", 10.0)]:
        rows.append({"day": day, "symbol": "003010", "decision_epoch": epoch, "net_return_pct": value})
        epoch += 1
    for index in range(5):
        rows.append({"day": f"2026-08-{14 + index:02d}", "symbol": f"W{index}", "decision_epoch": epoch, "net_return_pct": 1.0})
        epoch += 1
    for index in range(5):
        rows.append({"day": f"2026-08-{14 + index:02d}", "symbol": f"L{index}", "decision_epoch": epoch, "net_return_pct": -1.0})
        epoch += 1
    result = evaluate_risk_high_sensitivity(rows)
    assert result["base"]["avg_net_return_pct"] > 0
    assert result["decision"] == "REJECT_CONTRIBUTOR_DEPENDENCE"
    assert result["sensitivity"]["worst_symbol_leave_one_out"]["excluded_symbol"] == "003010"


def test_bounded_candidate_requires_robust_leave_one_out() -> None:
    robust = [
        {
            "day": f"2026-08-{index + 1:02d}",
            "symbol": f"S{index}",
            "decision_epoch": index,
            "net_return_pct": value,
        }
        for index, value in enumerate([1.0, 0.8, 0.7, 0.6, 0.5, 1.2, 0.9, 0.4, -0.2, -0.1, 0.8, 0.6])
    ]
    result = evaluate_bounded_candidate(robust, minimum_sample=10)
    assert result["decision"] == "READY_FOR_FIXED_RUNTIME_VALIDATION"

    concentrated = [dict(row) for row in robust]
    concentrated[0]["net_return_pct"] = 12.0
    for row in concentrated[1:]:
        row["net_return_pct"] = -0.2
    result = evaluate_bounded_candidate(concentrated, minimum_sample=10)
    assert result["decision"] in {
        "REJECT_SYMBOL_CONTRIBUTOR_DEPENDENCE",
        "REJECT_DAY_CONTRIBUTOR_DEPENDENCE",
        "REJECT_SINGLE_OBSERVATION_DEPENDENCE",
    }


def test_runtime_validation_closes_after_five_fixed_sessions(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    days = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
    for day in days:
        _write(
            root / "evaluation" / "opening_rank1_shadow" / day / "opening_rank1_shadow_daily.json",
            {"schema_version": "fixture", "day_status": "VALID"},
        )
    episodes = []
    for index, (day, value) in enumerate(zip(days, [1.0, 0.8, 0.7, 0.6, 0.5])):
        episodes.append(
            {
                "day": day,
                "symbol": f"S{index}",
                "decision_epoch": index,
                "opening_observability": {
                    "conditional_lanes": {"IMMEDIATE_OPENING_PROBE": {"eligible": True}},
                    "asset_observation": {"asset_class": "common_stock"},
                    "market_snapshot": {"kospi_pct": 0.5},
                },
                "checkpoints": {"+5m": {"live_net_return_pct": value}},
            }
        )
    _write(
        root / "evaluation" / "opening_rank1_shadow" / "opening_rank1_shadow_cumulative.json",
        {"schema_version": "fixture", "episodes": episodes},
    )
    result = build_immediate_opening_runtime_validation(
        reports_root=root, through_day="2026-08-28"
    )
    assert result["window_complete"] is True
    assert result["decision"] == "PASS_RUNTIME_VALIDATION"

    invalid_path = (
        root
        / "evaluation"
        / "opening_rank1_shadow"
        / "2026-08-26"
        / "opening_rank1_shadow_daily.json"
    )
    _write(invalid_path, {"schema_version": "fixture", "day_status": "FORWARD_INCOMPLETE"})
    result = build_immediate_opening_runtime_validation(
        reports_root=root, through_day="2026-08-28"
    )
    assert result["decision"] == "FAIL_RUNTIME_INTEGRITY"


# --- 2026-09-05 PRE-STEP5C cleanup (Codex audit item 4): operation vs.
# fixed-validation vs. production-promotion status separation -----------
#
# Root cause: `remaining_reviews.py::_bounded_review()` derives its
# decision (e.g. "READY_FOR_FIXED_RUNTIME_VALIDATION") purely from
# HISTORICAL sensitivity checks and never learns whether
# `runtime_validation.py`'s own fixed 5-session window has since run and
# reached its own, independent verdict -- so the board could keep
# implying promotion-readiness for a candidate whose fixed validation had
# already FAILED (2026-09-04: IMMEDIATE_OPENING_PROBE, N=5/WR20%/PF1.01,
# decision FAIL_RUNTIME_EFFECT). These tests exercise `canonicalize_board`
# directly, with a hand-built `legacy` payload that reproduces exactly
# that stale-decision shape.


def _minimal_legacy_board(*, final_offline_decision: str, board_bucket: str, runtime_validation: dict) -> dict:
    return {
        "candidates": [
            {
                "candidate_id": "IMMEDIATE_OPENING_PROBE",
                "operation_authority": {"enabled": True, "mode": "controlled_mock"},
                "board_bucket": board_bucket,
                "final_offline_review": {
                    "decision": final_offline_decision,
                    "rationale": "기본 성과와 종목·일자·최대 수익 제거 민감도를 모두 통과함.",
                },
                "historical": {"sample_count": 22, "win_rate": 0.636, "profit_factor": 3.60},
                "next_action": "기존 observer로 고정된 5거래일 prospective 런 검증 수행.",
                "source_keys": [],
            }
        ],
        "settled_findings": [],
        "runtime_validation": runtime_validation,
    }


def _row_for(payload: dict, candidate_id: str) -> dict:
    return next(row for row in payload["candidates"] if row["candidate_id"] == candidate_id)


def test_fixed_validation_failed_does_not_stop_controlled_mock_operation(tmp_path: Path) -> None:
    """T1/T2: a FAILED fixed-window validation must be reported honestly,
    but must NOT, by itself, be read as "the controlled-mock experiment
    must stop" -- those are different decisions (validation failed !=
    experiment must stop)."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={
            "candidate_id": "IMMEDIATE_OPENING_PROBE",
            "window_complete": True,
            "decision": "FAIL_RUNTIME_EFFECT",
        },
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_FAILED"
    assert row["operation_status"] == "CONTROLLED_MOCK_CONTINUES"


def test_fixed_validation_failed_blocks_production_promotion(tmp_path: Path) -> None:
    """A FAILED fixed validation must always block production promotion,
    regardless of a stale historical-readiness decision string."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={
            "candidate_id": "IMMEDIATE_OPENING_PROBE",
            "window_complete": True,
            "decision": "FAIL_RUNTIME_EFFECT",
        },
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["production_promotion_status"] == "PRODUCTION_PROMOTION_NOT_ALLOWED"
    # The legacy status/decision fields are untouched by this fix.
    assert row["decision"] == "READY_FOR_FIXED_RUNTIME_VALIDATION"


def test_fixed_validation_pending_before_window_completes(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={
            "candidate_id": "IMMEDIATE_OPENING_PROBE",
            "window_complete": False,
            "decision": "COLLECTING",
        },
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_PENDING"
    assert row["production_promotion_status"] == "PRODUCTION_PROMOTION_NOT_ALLOWED"
    assert row["operation_status"] == "CONTROLLED_MOCK_CONTINUES"


def test_fixed_validation_not_yet_run_for_candidate_with_no_runtime_report(tmp_path: Path) -> None:
    """A candidate with no runtime_validation report at all (the common
    case -- today only IMMEDIATE_OPENING_PROBE has one) must be reported
    as NOT_YET_RUN, never silently defaulted to PASSED or FAILED."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_NOT_YET_RUN"
    assert row["production_promotion_status"] == "PRODUCTION_PROMOTION_NOT_ALLOWED"


def test_fixed_validation_passed_case_still_requires_promoted_status_for_promotion(tmp_path: Path) -> None:
    """A PASSED fixed validation alone does not grant production
    promotion -- an explicit PROMOTED board decision is also required."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={
            "candidate_id": "IMMEDIATE_OPENING_PROBE",
            "window_complete": True,
            "decision": "PASS_RUNTIME_VALIDATION",
        },
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_PASSED"
    assert row["status"] != "PROMOTED"
    assert row["production_promotion_status"] == "PRODUCTION_PROMOTION_NOT_ALLOWED"


def test_closed_candidate_reports_operation_stopped(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="REJECT_BASE_EFFECT",
        board_bucket="CLOSED_AFTER_SENSITIVITY_REVIEW",
        runtime_validation={},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["status"] == "CLOSED"
    # 2026-09-05 FIX 2 (item 8): renamed from CONTROLLED_MOCK_STOPPED --
    # "stopped" implied it was once a controlled-mock execution, which is
    # not knowable/true for most candidates; NOT_RUNNING is honest for any
    # closed candidate regardless of what it was before closing.
    assert row["operation_status"] == "NOT_RUNNING"
    assert row["production_promotion_status"] == "PRODUCTION_PROMOTION_NOT_ALLOWED"


def test_board_backward_compatibility_existing_columns_and_status_unchanged(tmp_path: Path) -> None:
    """T5: the pre-existing `status`/`board_bucket`/`decision` semantics
    and the frozen ROW_COLUMNS/candidate-registry contract must survive
    unchanged -- the three new fields are purely additive."""
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    assert tuple(payload["row_columns"]) == ROW_COLUMNS
    for row in payload["candidates"]:
        assert tuple(row) == ROW_COLUMNS
        assert row["operation_status"] in {
            "CONTROLLED_MOCK_CONTINUES", "SHADOW_CONTINUES", "NOT_RUNNING", "UNKNOWN_OPERATION_STATUS",
        }
        assert row["production_promotion_status"] in {
            "PRODUCTION_PROMOTION_ALLOWED",
            "PRODUCTION_PROMOTION_NOT_ALLOWED",
        }
    assert payload["integrity"]["candidate_registry_matches"] is True


# ===========================================================================
# 2026-09-05 PRE-STEP5C CLEANUP FIX 2, item 8 -- Alpha Board operation
# truth and evidence truth (Codex independent re-audit)
# ===========================================================================


def test_item8_t1_controlled_mock_active_candidate(tmp_path: Path) -> None:
    """T1: a genuine controlled-mock-probe-backed candidate (board_bucket
    not SHADOW/observation-flavored) reports CONTROLLED_MOCK_CONTINUES."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "CONTROLLED_MOCK_CONTINUES"


def test_item8_t2_shadow_only_candidate(tmp_path: Path) -> None:
    """T2: a SHADOW-only candidate (source_status carrying "SHADOW", the
    real shape builder.py assigns to e.g. BTC_STRONG_BULL_LOCAL_
    CONFIRMATION_V1 / HIGH_COMMON_SHORT_ALPHA_V1) must never claim
    CONTROLLED_MOCK_CONTINUES."""
    legacy = {
        "candidates": [
            {
                "candidate_id": "IMMEDIATE_OPENING_PROBE",
                "board_bucket": "BACKGROUND_RUNTIME_REQUIRED",
                "source_status": "PROSPECTIVE_SHADOW_FROM_2026_08_25",
                "source_keys": [],
            }
        ],
        "settled_findings": [],
        "runtime_validation": {},
    }
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "SHADOW_CONTINUES"
    assert row["operation_status"] != "CONTROLLED_MOCK_CONTINUES"


def test_item8_t3_disabled_closed_candidate(tmp_path: Path) -> None:
    """T3: a CLOSED candidate reports NOT_RUNNING, never CONTINUES of any
    flavor."""
    legacy = _minimal_legacy_board(
        final_offline_decision="REJECT_BASE_EFFECT",
        board_bucket="CLOSED_AFTER_SENSITIVITY_REVIEW",
        runtime_validation={},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "NOT_RUNNING"


def test_item8_t4_fail_runtime_effect_is_a_genuine_failed_verdict(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": True, "decision": "FAIL_RUNTIME_EFFECT"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_FAILED"


def test_item8_t5_insufficient_evidence_is_not_conflated_with_failed(tmp_path: Path) -> None:
    """T5: INSUFFICIENT_RUNTIME_SAMPLE (a measurement problem, not a
    performance verdict) must never be reported as FIXED_VALIDATION_FAILED."""
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": True, "decision": "INSUFFICIENT_RUNTIME_SAMPLE"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_INSUFFICIENT_EVIDENCE"
    assert row["fixed_validation_status"] != "FIXED_VALIDATION_FAILED"


def test_item8_t5b_fail_runtime_integrity_is_insufficient_evidence_not_failed(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": True, "decision": "FAIL_RUNTIME_INTEGRITY"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_INSUFFICIENT_EVIDENCE"


def test_item8_t6_pending_before_window_completes(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": False, "decision": "COLLECTING"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_PENDING"


def test_item8_t7_pass_runtime_validation(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": True, "decision": "PASS_RUNTIME_VALIDATION"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_PASSED"


def test_item8_t8_validation_fail_does_not_stop_controlled_mock(tmp_path: Path) -> None:
    legacy = _minimal_legacy_board(
        final_offline_decision="READY_FOR_FIXED_RUNTIME_VALIDATION",
        board_bucket="RUNTIME_VALIDATION_NEXT",
        runtime_validation={"candidate_id": "IMMEDIATE_OPENING_PROBE", "window_complete": True, "decision": "FAIL_RUNTIME_EFFECT"},
    )
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["fixed_validation_status"] == "FIXED_VALIDATION_FAILED"
    assert row["operation_status"] == "CONTROLLED_MOCK_CONTINUES"


def test_item8_t9_shadow_candidate_never_claims_controlled_mock_running(tmp_path: Path) -> None:
    """T9: a SHADOW-classified candidate must not claim
    CONTROLLED_MOCK_CONTINUES even when its (legacy, pre-existing) status
    field is not CLOSED."""
    legacy = {
        "candidates": [
            {
                "candidate_id": "IMMEDIATE_OPENING_PROBE",
                "board_bucket": "OBSERVE_FIXED",
                "source_status": "OBSERVATION_ONLY",
                "source_keys": [],
            }
        ],
        "settled_findings": [],
        "runtime_validation": {},
    }
    payload = canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04")
    row = _row_for(payload, "IMMEDIATE_OPENING_PROBE")

    assert row["status"] != "CLOSED"
    assert row["operation_status"] == "SHADOW_CONTINUES"
    assert row["operation_status"] != "CONTROLLED_MOCK_CONTINUES"


# ===========================================================================
# 2026-09-05 PRE-STEP5C CLEANUP FIX 3 (item 8, second independent Codex
# re-audit): Codex's exact reproduction -- source_status="DISABLED" or any
# genuinely unrecognized value fell through to CONTROLLED_MOCK_CONTINUES
# (the previous design's DEFAULT branch). Rebuilt around a positive
# allowlist of candidate IDs actually backed by opening_rank1_controlled_
# probe.py -- unrecognized values now resolve to UNKNOWN_OPERATION_STATUS,
# never promoted to "active".
# ===========================================================================


def _board_with(candidate_id: str, **fields) -> dict:
    return {
        "candidates": [{"candidate_id": candidate_id, "source_keys": [], **fields}],
        "settled_findings": [],
        "runtime_validation": {},
    }


def test_fix3_item8_t1_controlled(tmp_path: Path) -> None:
    legacy = _board_with("IMMEDIATE_OPENING_PROBE", board_bucket="RUNTIME_VALIDATION_NEXT", source_status="COLLECTING")
    legacy['candidates'][0]['operation_authority'] = {'enabled': True, 'mode': 'controlled_mock'}
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "CONTROLLED_MOCK_CONTINUES"


def test_fix3_item8_t2_shadow(tmp_path: Path) -> None:
    legacy = _board_with("IMMEDIATE_OPENING_PROBE", board_bucket="BACKGROUND_RUNTIME_REQUIRED", source_status="PROSPECTIVE_SHADOW_FROM_2026_08_25")
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "SHADOW_CONTINUES"


def test_fix3_item8_t3_disabled_is_not_running(tmp_path: Path) -> None:
    """Codex's exact reproduction: source_status="DISABLED" must resolve
    to NOT_RUNNING, never CONTROLLED_MOCK_CONTINUES."""
    legacy = _board_with("IMMEDIATE_OPENING_PROBE", board_bucket="RUNTIME_VALIDATION_NEXT", source_status="DISABLED")
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "IMMEDIATE_OPENING_PROBE")

    assert row["operation_status"] == "NOT_RUNNING"
    assert row["operation_status"] != "CONTROLLED_MOCK_CONTINUES"


def test_fix3_item8_t4_closed(tmp_path: Path) -> None:
    legacy = _board_with(
        "IMMEDIATE_OPENING_PROBE",
        board_bucket="CLOSED_AFTER_SENSITIVITY_REVIEW",
        final_offline_review={"decision": "REJECT_BASE_EFFECT", "rationale": "x"},
    )
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "IMMEDIATE_OPENING_PROBE")

    assert row["status"] == "CLOSED"
    assert row["operation_status"] == "NOT_RUNNING"


def test_fix3_item8_t5_unknown_value_is_unknown_not_controlled(tmp_path: Path) -> None:
    """Codex's exact reproduction: an unrecognized source_status value on
    a candidate NOT positively identified as a controlled-mock-probe lane
    must resolve to UNKNOWN_OPERATION_STATUS, never CONTROLLED_MOCK_
    CONTINUES (the previous design's fall-through default)."""
    legacy = _board_with(
        "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1",
        board_bucket="SOME_NEW_UNRECOGNIZED_BUCKET", source_status="SOME_NEW_UNRECOGNIZED_STATUS",
    )
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1")

    assert row["operation_status"] == "UNKNOWN_OPERATION_STATUS"
    assert row["operation_status"] != "CONTROLLED_MOCK_CONTINUES"


def test_fix3_item8_t6_missing_fields_is_unknown(tmp_path: Path) -> None:
    legacy = _board_with("SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1")
    row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1")

    assert row["operation_status"] == "UNKNOWN_OPERATION_STATUS"


def test_fix3_item8_t7_no_candidate_ever_falsely_claims_controlled_mock(tmp_path: Path) -> None:
    """Sweep every candidate NOT on the controlled-mock-probe allowlist
    with a variety of unrecognized/empty inputs -- none may ever resolve
    to CONTROLLED_MOCK_CONTINUES."""
    unrecognized_inputs = [
        {},
        {"source_status": "WHATEVER"},
        {"board_bucket": "WHATEVER"},
        {"source_status": "", "board_bucket": ""},
    ]
    for candidate_id in ("SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1", "R1_SCANNER_RISK_HIGH_30M_V1"):
        for fields in unrecognized_inputs:
            legacy = _board_with(candidate_id, **fields)
            row = _row_for(canonicalize_board(legacy, reports_root=tmp_path, through_day="2026-09-04"), candidate_id)
            assert row["operation_status"] != "CONTROLLED_MOCK_CONTINUES", (candidate_id, fields, row["operation_status"])
