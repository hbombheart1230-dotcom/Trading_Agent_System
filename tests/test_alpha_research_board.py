from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.alpha_research_board import (
    build_alpha_research_board,
    write_alpha_research_board,
)
from libs.reporting.alpha_research_board.sensitivity import evaluate_risk_high_sensitivity
from libs.reporting.alpha_research_board.remaining_reviews import evaluate_bounded_candidate
from libs.reporting.alpha_research_board.runtime_validation import (
    build_immediate_opening_runtime_validation,
)


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
    assert by_id["OPEN_0_20_RANK1_30M"]["board_bucket"] == "CLOSED"
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["source_status"] == "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE"
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["board_bucket"] == "CLOSED_AFTER_SENSITIVITY_REVIEW"
    assert by_id["R1_FRESH_CHANGE_ACTIVATION_V1"]["board_bucket"] == "CLOSED_NEGATIVE_PROSPECTIVE"


def test_board_uses_day_symbol_sample_and_live_cost_basis(tmp_path: Path) -> None:
    payload = build_alpha_research_board(
        reports_root=_fixture_reports(tmp_path), through_day="2026-08-21"
    )
    by_id = {row["candidate_id"]: row for row in payload["candidates"]}
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["prospective"]["sample_count"] == 21
    assert by_id["R1_SCANNER_RISK_HIGH_30M_V1"]["concentration"]["largest_symbol_share"] == 0.6667
    assert by_id["SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1"]["prospective"]["avg_net_return_pct"] == 0.66
    assert payload["cost_authority"]["live_equity_round_trip_pct"] == 0.28


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
    assert "한눈에 보는 결론" in markdown
    assert "승패 구분자 근거" in markdown
    assert "끝난 결론" in markdown
    assert Path(result["sensitivity_markdown_path"]).exists()
    assert Path(result["remaining_markdown_path"]).exists()
    assert Path(result["runtime_markdown_path"]).exists()


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
