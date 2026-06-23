from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.operator_visibility import _build_trading_health_status
from libs.reporting.operator_period_summary import (
    generate_operator_daily_summary_artifact,
    generate_operator_period_summary,
    generate_operator_symbol_summary_artifact,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_trading_health_status_turns_red_on_weak_intraday_performance(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "performance" / "2026-05-18" / "summary.json",
        {
            "total_trades": 15,
            "return_sample_count": 13,
            "win_rate": 0.1538,
            "avg_return": -0.0107,
            "profit_factor": 0.05,
        },
    )

    status = _build_trading_health_status(reports, "2026-05-18")

    assert status["trading_health_level"] == "RED"
    assert status["avg_return"] == -0.0107


def test_operator_weekly_and_monthly_summary_reports_use_operator_symbol_history(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260428_005930_01",
                "date": "2026-04-28",
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "result_pct": -0.5,
                "hold_seconds": 300,
            },
            {
                "trade_id": "TRD_20260429_005930_01",
                "date": "2026-04-29",
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "pullback_rebound",
                "exit_reason": "SELL was triggered because take_profit.",
                "entry_pattern_type": "pullback",
                "exit_pattern_type": "take_profit",
                "result_pct": 1.0,
                "hold_seconds": 600,
            },
        ],
    )
    _write_json(
        reports / "operator_summary" / "symbols" / "000660" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260504_000660_01",
                "date": "2026-05-04",
                "symbol": "000660",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because hard_stop.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "hard_stop",
                "result_pct": -1.0,
                "hold_seconds": 200,
            }
        ],
    )

    weekly_md, weekly_json, weekly = generate_operator_period_summary(
        reports_root=reports,
        period_type="weekly",
        period_key="2026-W18",
    )
    monthly_md, monthly_json, monthly = generate_operator_period_summary(
        reports_root=reports,
        period_type="monthly",
        period_key="2026-04",
    )

    assert weekly_json == reports / "operator_summary" / "weekly" / "2026-W18" / "weekly_summary.json"
    assert weekly_md == reports / "operator_summary" / "weekly" / "2026-W18" / "weekly_summary.md"
    assert weekly["metrics"]["trade_count"] == 2
    assert weekly["metrics"]["win_count"] == 1
    assert weekly["metrics"]["loss_count"] == 1
    assert weekly["patterns"]["top_exit_pattern_types"][0]["name"] == "고점 대비 하락폭"
    assert monthly_json == reports / "operator_summary" / "monthly" / "2026-04" / "monthly_summary.json"
    assert monthly_md == reports / "operator_summary" / "monthly" / "2026-04" / "monthly_summary.md"
    assert monthly["metrics"]["trade_count"] == 2
    assert "Weekly Summary (2026-W18)" in weekly_md.read_text(encoding="utf-8")
    assert "Monthly Summary (2026-04)" in monthly_md.read_text(encoding="utf-8")


def test_operator_daily_and_symbol_summary_artifacts_are_saved(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade_rows = [
        {
            "trade_id": "TRD_20260428_005930_01",
            "date": "2026-04-28",
            "symbol": "005930",
            "status": "closed",
            "entry_reason": "breakout_above_recent_high",
            "exit_reason": "SELL was triggered because peak_drawdown.",
            "entry_pattern_type": "breakout",
            "exit_pattern_type": "peak_drawdown",
            "result_pct": -0.5,
            "hold_seconds": 300,
        }
    ]
    _write_json(reports / "operator_summary" / "symbols" / "005930" / "trade_history.json", trade_rows)
    daily_md, daily_json, daily = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day="2026-04-28",
        daily_report_payload={"events": 12, "approvals": 1, "blocks": 2, "symbols_observed": ["005930"]},
    )
    symbol_md, symbol_json, symbol = generate_operator_symbol_summary_artifact(
        reports_root=reports,
        symbol="005930",
        symbol_trade_report_payload={"symbol": "005930", "history_index": trade_rows},
        symbol_memory_payload={"trade_stats": {"trade_count": 1}},
    )

    assert daily_json == reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.json"
    assert daily_md == reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.md"
    assert daily["metrics"]["trade_count"] == 1
    assert daily["runtime_activity"]["events"] == 12
    assert symbol_json == reports / "operator_summary" / "symbols" / "005930" / "symbol_summary.json"
    assert symbol_md == reports / "operator_summary" / "symbols" / "005930" / "symbol_summary.md"
    assert symbol["metrics"]["loss_count"] == 1


def test_operator_daily_summary_prefers_truth_surface_net_result(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-04"
    trade_id = "TRD_20260504_005930_01"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "last_status": "closed",
                "result_pct": 0.5,
                "hold_seconds": 60,
            }
        ],
    )
    _write_json(
        reports / "trades" / day / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": -1000,
                "pnl_pct": -0.01,
                "cost_analysis": {"price_move_pct": 0.005, "cost_drag_pct": 0.015},
            }
        },
    )

    _md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    metrics = daily["metrics"]
    assert metrics["return_basis"] == "truth_surface_net"
    assert metrics["win_count"] == 0
    assert metrics["loss_count"] == 1
    assert metrics["win_rate"] == 0.0
    assert metrics["avg_return_pct"] == -1.0
    assert metrics["price_move_win_count"] == 1
    assert metrics["cost_drag_loss_count"] == 1


def test_operator_daily_summary_aggregates_quant_tactic_diagnostics(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-20"
    trade_id = "TRD_20260520_005930_01"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "last_status": "closed",
                "last_action": "SELL",
                "entry_reason": "pullback_rebound",
                "exit_reason": "SELL was triggered because intraday_low_break.",
                "entry_pattern_type": "pullback",
                "exit_pattern_type": "intraday_low_break",
                "result_pct": -0.4,
                "hold_seconds": 35,
            }
        ],
    )
    _write_json(
        reports / "trades" / day / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "quant_tactic": {
                "tactic_id": "vwap_reclaim_pullback",
                "tactic_id_source": "entry_quant_decision",
                "tactic_id_mismatches": [
                    {"source": "exit_quant_decision", "tactic_id": "breakout_continuation"},
                ],
            },
        },
    )
    _write_json(
        reports / "trades" / day / trade_id / "reports" / "ai_trade_report.json",
        {
            "why_this_symbol_was_chosen": {
                "tactic_suitability": {"score": 0.42, "tier": "weak"},
            },
            "monitor_snapshot": {
                "quant_factor_snapshot": {
                    "tactic_id": "vwap_reclaim_pullback",
                    "factors": {"cost_floor_state": "not_met"},
                },
                "entry_quant_decision": {
                    "tactic_id": "vwap_reclaim_pullback",
                    "decision": "block_recommended",
                    "blockers": ["cost_edge_fail", "volume_confirmation_missing"],
                    "warnings": ["weak_tactic_suitability"],
                    "cost_edge": {
                        "cost_floor_state": "not_met",
                        "cost_adjusted_edge_pct": -0.001,
                    },
                },
                "exit_quant_decision": {
                    "tactic_id": "vwap_reclaim_pullback",
                    "decision": "confirm_before_exit_recommended",
                    "hard_exit": False,
                    "confirmation_pending": True,
                    "blockers": ["exit_confirmation_pending"],
                    "warnings": ["early_exit_before_expected_min_hold"],
                    "hold_window_mismatch": True,
                    "actual_hold_sec": 35,
                },
            },
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)
    perf = daily["pattern_performance"]

    assert perf["quant"]["by_tactic_id"][0]["name"] == "vwap_reclaim_pullback"
    assert perf["quant"]["by_tactic_suitability_tier"][0]["name"] == "weak"
    assert perf["quant"]["by_entry_primary_blocker"][0]["name"] == "cost_edge_fail"
    assert perf["quant"]["by_entry_cost_floor_state"][0]["name"] == "not_met"
    assert perf["quant"]["by_exit_decision"][0]["name"] == "confirm_before_exit_recommended"
    assert perf["quant"]["by_exit_confirmation_state"][0]["name"] == "pending"
    assert perf["quant"]["by_exit_hold_window_state"][0]["name"] == "mismatch"
    assert daily["quant_tactic_evaluation"]["status"] == "hold_sample_insufficient"
    assert daily["quant_tactic_evaluation"]["tactic_id_mismatch_trade_count"] == 0
    assert daily["quant_tactic_evaluation"]["exit_tactic_drift_trade_count"] == 0
    markdown = md.read_text(encoding="utf-8")
    assert "Quant tactic" in markdown
    assert "Quant entry blockers" in markdown
    assert "Quant Q8 readiness" in markdown
    assert "mismatch trades 0" in markdown


def test_operator_daily_summary_surfaces_quant_shadow_candidates(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-24"
    _write_json(
        tmp_path / "data" / "logs" / "quant_shadow_candidates" / day / "sample.json",
        {
            "schema_version": "quant_shadow_candidates.v1",
            "behavior_effect": "observation_only",
            "day": day,
            "candidates": [
                {
                    "symbol": "005930",
                    "shadow_role": "top_pick",
                    "evaluated": True,
                    "would_enter": False,
                    "guard_blocked": True,
                    "reason": "volume_confirmation_missing",
                    "quant_tactic_id": "vwap_reclaim_pullback",
                    "tactic_suitability_tier": "weak",
                    "entry_quant_cost_floor_state": "not_met",
                    "primary_failure_axis": "volume",
                },
                {
                    "symbol": "000660",
                    "shadow_role": "runner_up_evaluated",
                    "evaluated": True,
                    "would_enter": True,
                    "reason": "ready",
                    "quant_tactic_id": "breakout_continuation",
                    "tactic_suitability_tier": "strong",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "data" / "logs" / "macro_indicators" / day / "latest.json",
        {
            "schema_version": "global_sentiment_macro_snapshot.v1",
            "generated_at": "2026-05-24T06:00:00+00:00",
            "index_moves": {
                "nasdaq_pct": 0.4,
                "sp500_pct": 0.2,
                "kospi_pct": -0.3,
                "kosdaq_pct": -1.5,
            },
            "korea_indices": {"breadth": -0.5},
            "macro_moves": {"dxy_pct": 0.0, "vix_level": 16.0, "vix_pct": 1.0},
            "macro_indicators": {
                "indicators": {
                    "usdkrw": {"change_pct": 0.1},
                    "us_10y_yield": {"delta": 0.01},
                }
            },
            "global_sentiment": {"score": 0.0},
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    shadow = daily["quant_shadow_candidate_evaluation"]
    assert shadow["candidate_count"] == 2
    assert shadow["would_enter_count"] == 1
    assert {"name": "volume_confirmation_missing", "count": 1} in shadow["by_reason"]
    assert shadow["promotion_candidate"]["candidate"] == "cost_edge"
    assert daily["market_regime_rail_review"]["rail_id"] == "us_tech_risk_on_korea_weak"
    assert daily["q8_shadow_blocker_review"]["market_regime_rail"]["rail_id"] == "us_tech_risk_on_korea_weak"
    markdown = md.read_text(encoding="utf-8")
    assert "Quant Shadow Candidates" in markdown
    assert "would-enter 1" in markdown
    assert "Q8 promotion candidate" in markdown
    assert "Market Regime Rail" in markdown
    assert "Q8 Shadow Blocker Forward Review" in markdown


def test_operator_daily_summary_surfaces_strategist_llm_evaluation(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-27"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": f"TRD_20260527_005930_{idx:02d}",
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "last_status": "closed",
                "last_action": "SELL",
                "tactical_strategy": "vwap_reclaim_pullback",
                "quant_tactic_id": "vwap_reclaim_pullback",
                "result_pct": -1.0,
            }
            for idx in range(1, 4)
        ],
    )
    _write_json(
        tmp_path / "data" / "logs" / "quant_shadow_candidates" / day / "sample.json",
        {
            "candidates": [
                {
                    "symbol": "000660",
                    "reason": "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
                    "primary_failure_axis": "confirmed_entry",
                    "would_enter": True,
                    "opening_largecap_surge_would_enter": True,
                }
            ]
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    evaluation = daily["strategist_llm_evaluation"]
    assert evaluation["selected_primary_tactic"] == "vwap_reclaim_pullback"
    assert evaluation["lane_selection_quality"] == "poor_lane_selection"
    assert evaluation["overused_lane_or_tactic"] == "vwap_reclaim_pullback"
    markdown = md.read_text(encoding="utf-8")
    assert "Strategist LLM Evaluation" in markdown
    assert "poor_lane_selection" in markdown


def test_operator_daily_summary_finds_truth_surface_under_time_bucket(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-07"
    trade_id = "TRD_20260507_010170_01"
    _write_json(
        reports / "operator_summary" / "symbols" / "010170" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "010170",
                "status": "closed",
                "last_status": "closed",
                "result_pct": 0.7,
                "exit_reason": "SELL was triggered because stop_loss.",
            }
        ],
    )
    _write_json(
        reports / "trades" / day / "1200" / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": -13481,
                "pnl_pct": -0.009,
                "cost_analysis": {"price_move_pct": 0.0, "cost_drag_pct": 0.009},
            }
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    metrics = daily["metrics"]
    assert metrics["return_basis"] == "truth_surface_net"
    assert metrics["avg_return_pct"] == -0.9
    assert daily["patterns"]["top_exit_reasons"][0]["name"] == "고정 손절 기준"
    assert "고정 손절 기준 (1)" in md.read_text(encoding="utf-8")


def test_operator_daily_summary_normalizes_reason_and_derives_exit_pattern(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-07"
    _write_json(
        reports / "operator_summary" / "symbols" / "010170" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260507_010170_01",
                "date": day,
                "symbol": "010170",
                "status": "closed",
                "last_status": "closed",
                "last_action": "SELL",
                "entry_reason": "VWAP 위 눌림목 구조와 거래량 확인",
                "exit_reason": "SELL was triggered because stop_loss.",
                "entry_pattern_type": "unknown",
                "exit_pattern_type": "unknown",
                "result_pct": -0.5,
            },
            {
                "trade_id": "TRD_20260507_033790_01",
                "date": day,
                "symbol": "033790",
                "status": "closed",
                "last_status": "closed",
                "last_action": "SELL",
                "entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                "exit_reason": "SELL was triggered because intraday_low_break.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "unknown",
                "result_pct": -0.7,
            },
        ],
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    patterns = daily["patterns"]
    assert patterns["top_entry_reasons"][0]["name"] == "VWAP 위 눌림목 + 거래량 확인"
    assert patterns["top_exit_reasons"][0]["name"] == "고정 손절 기준"
    assert patterns["top_entry_pattern_types"][0]["name"] == "눌림목"
    assert patterns["top_exit_pattern_types"][0]["name"] == "손절"
    text = md.read_text(encoding="utf-8")
    assert "SELL was triggered" not in text
    assert "Scanner selected" not in text
    assert "unknown" not in text


def test_operator_period_summary_filters_non_exit_noise_and_normalizes_extra_reason_codes(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260504_005930_01",
                "date": "2026-05-04",
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "pullback_rebound_above_vwap_with_volume_confirmation",
                "exit_reason": "SELL was triggered because trailing_stop.",
                "entry_pattern_type": "Entry context was recovered from the preserved strategist frame.",
                "exit_pattern_type": "unknown",
                "result_pct": -0.3,
            },
            {
                "trade_id": "TRD_20260504_005930_02",
                "date": "2026-05-04",
                "symbol": "005930",
                "status": "open",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "포지션은 아직 열려 있으며 청산 신호를 계속 감시 중입니다.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "unknown",
            },
            {
                "trade_id": "TRD_20260504_005930_03",
                "date": "2026-05-04",
                "symbol": "005930",
                "status": "partial",
                "entry_reason": "Entry evidence was not captured for this day.",
                "exit_reason": "생애주기 기록이 partial 상태이며 청산 근거가 누락됐습니다.",
                "entry_pattern_type": "unknown",
                "exit_pattern_type": "unknown",
            },
        ],
    )

    md, _json, weekly = generate_operator_period_summary(
        reports_root=reports,
        period_type="weekly",
        period_key="2026-W19",
    )

    assert weekly["patterns"]["top_entry_reasons"][0]["name"] == "눌림목 반등 + VWAP + 거래량 확인"
    assert weekly["patterns"]["top_exit_reasons"] == [{"name": "추적 손절 기준", "count": 1}]
    assert weekly["patterns"]["top_exit_pattern_types"] == [{"name": "추적 손절 기준", "count": 1}]
    text = md.read_text(encoding="utf-8")
    assert "SELL was triggered" not in text
    assert "unknown" not in text
    assert "청산 근거가 누락" not in text
    assert "아직 열려" not in text


def test_operator_daily_summary_prefers_trade_summary_entry_path_over_scanner_sentence(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-07"
    trade_id = "TRD_20260507_010170_01"
    _write_json(
        reports / "trades" / day / "0900" / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "decision_flow": {
                "entry_reason": "진입 사유는 Scanner selected 010170 as rank #1 out of 6 candidates with score 0.842 because it led on sentiment support.입니다",
                "entry_confidence": "010170이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다. 실제 엔트리 경로는 눌림목·거래량 경로였습니다.",
                "exit_trigger": "고정 손절 기준",
            },
            "truth_surface": {
                "pnl": -1000,
                "pnl_pct": -0.01,
                "cost_analysis": {"price_move_pct": -0.001, "cost_drag_pct": 0.009},
            },
        },
    )
    _write_json(
        reports / "operator_summary" / "daily" / day / "daily_report.json",
        {
            "events": 1,
            "approvals": 1,
            "blocks": 0,
            "trade_index": [
                {
                    "trade_id": trade_id,
                    "date": day,
                    "symbol": "010170",
                    "status": "closed",
                    "entry_reason": "Scanner selected 010170 as rank #1 out of 6 candidates with score 0.842 because it led on sentiment support.",
                    "exit_reason": "SELL was triggered because stop_loss.",
                }
            ],
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    assert daily["patterns"]["top_entry_reasons"][0]["name"] == "눌림목 + 거래량 경로"
    assert daily["patterns"]["top_entry_pattern_types"][0]["name"] == "눌림목"
    text = md.read_text(encoding="utf-8")
    assert "Scanner selected" not in text


def test_operator_daily_summary_counts_recovered_partial_sell_as_realized_exit(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-06"
    trade_id = "TRD_20260506_036540_01"
    _write_json(
        reports / "operator_summary" / "symbols" / "036540" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "036540",
                "status": "partial",
                "last_status": "partial",
                "last_action": "SELL",
                "entry_reason": "Entry evidence was not captured for this day.",
                "exit_reason": "SELL was triggered because stop_loss.",
                "entry_pattern_type": "unknown",
                "exit_pattern_type": "unknown",
                "trade_origin": "recovered_partial",
                "lifecycle_completeness": "partial",
                "evidence_recovery_used": True,
            }
        ],
    )
    _write_json(
        reports / "trades" / day / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": 2711,
                "pnl_pct": 0.0315,
                "cost_analysis": {"price_move_pct": 0.0406, "cost_drag_pct": 0.0092},
            }
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    metrics = daily["metrics"]
    assert metrics["closed_trade_count"] == 0
    assert metrics["return_sample_count"] == 0
    assert metrics["realized_exit_count"] == 1
    assert metrics["recovered_partial_exit_count"] == 1
    assert metrics["carryover_exit_count"] == 0
    assert metrics["realized_exit_return_sample_count"] == 1
    assert metrics["realized_exit_win_count"] == 1
    assert metrics["realized_exit_loss_count"] == 0
    assert metrics["realized_exit_avg_return_pct"] == 3.15
    assert daily["symbol_summary"][0]["realized_exit_count"] == 1
    assert daily["patterns"]["top_entry_reasons"] == []
    text = md.read_text(encoding="utf-8")
    assert "완료 외 실현 청산(회수/partial 포함): 1건 / 승패 1/0 / 평균 3.15%" in text
    assert "회수청산 1건 1/0 평균 3.15%" in text


def test_operator_daily_summary_excludes_closed_partial_lifecycle_from_closed_win_rate(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-11"
    trade_id = "TRD_20260511_115160_01"
    _write_json(
        reports / "operator_summary" / "symbols" / "115160" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "115160",
                "status": "closed",
                "last_status": "closed",
                "last_action": "SELL",
                "result_pct": 0.13,
                "trade_origin": "recovered_partial",
                "lifecycle_completeness": "partial",
                "evidence_recovery_used": True,
            }
        ],
    )
    _write_json(
        reports / "trades" / day / "1100" / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": "unavailable",
                "pnl_pct": None,
                "cost_analysis": {},
            }
        },
    )

    _md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    metrics = daily["metrics"]
    assert metrics["closed_trade_count"] == 0
    assert metrics["return_sample_count"] == 0
    assert metrics["realized_exit_count"] == 1
    assert metrics["realized_exit_unavailable_return_count"] == 1
    symbol = daily["symbol_summary"][0]
    assert symbol["closed_trade_count"] == 0
    assert symbol["realized_exit_count"] == 1
    assert symbol["realized_exit_unavailable_return_count"] == 1


def test_operator_daily_summary_reads_partial_marker_from_daily_trade_lifecycle(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-11"
    trade_id = "TRD_20260511_115160_01"
    trade_root = reports / "trades" / day / "1100" / trade_id
    _write_json(
        trade_root / "lifecycle_bundle.json",
        {
            "trade_id": trade_id,
            "symbol": "115160",
            "lifecycle_completeness": "partial",
            "evidence_recovery_used": True,
            "trade_origin": "recovered_partial",
        },
    )
    _write_json(
        trade_root / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": "unavailable",
                "pnl_pct": None,
                "cost_analysis": {},
            }
        },
    )

    _md, _json, daily = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day=day,
        daily_report_payload={
            "events": 1,
            "approvals": 1,
            "blocks": 0,
            "trade_index": [
                {
                    "trade_id": trade_id,
                    "date": day,
                    "symbol": "115160",
                    "status": "closed",
                    "last_action": "SELL",
                }
            ],
        },
    )

    metrics = daily["metrics"]
    assert metrics["closed_trade_count"] == 0
    assert metrics["return_sample_count"] == 0
    assert metrics["realized_exit_count"] == 1
    assert metrics["realized_exit_unavailable_return_count"] == 1


def test_operator_daily_summary_uses_latest_live_summary_when_daily_report_payload_missing(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "live_summary" / "live_summary_20260506_025507.json",
        {
            "lookback_min": 10,
            "events": {"scanned_total": 1000, "window_total": 325},
            "execution": {
                "allowed_total": 1,
                "blocked_total": 3,
                "executed_total": 1,
                "executed_broker_fail_total": 0,
            },
        },
    )

    _md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day="2026-05-06")

    runtime = daily["runtime_activity"]
    assert runtime["source"] == "live_summary_fallback"
    assert runtime["lookback_min"] == 10
    assert runtime["events"] == 325
    assert runtime["events_scanned_total"] == 1000
    assert runtime["approvals"] == 1
    assert runtime["blocks"] == 3
    assert runtime["executed_total"] == 1


def test_operator_daily_summary_marks_runtime_activity_unavailable(tmp_path: Path) -> None:
    reports = tmp_path / "reports"

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day="2026-05-07")

    assert daily["runtime_activity"]["source"] == "not_available"
    text = md.read_text(encoding="utf-8")
    assert "런타임 이벤트: 미집계" in text
    assert "승인/차단: 미집계" in text
    assert "런타임 이벤트: 0건" not in text
    assert "승인/차단: 0 / 0" not in text


def test_operator_daily_summary_surfaces_residual_positions_and_overnight_reason(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    state_path = tmp_path / "data" / "state.json"
    _write_json(
        state_path,
        {
            "mock_positions": [
                {
                    "symbol": "005930",
                    "qty": 5,
                    "avg_price": 264500.0,
                    "current_price": 269500.0,
                    "account_pnl_ratio": 0.0098,
                },
                {"symbol": "078890", "qty": 338, "avg_price": 8770.0, "current_price": 8700.0},
            ],
            "overnight_decision_by_symbol": {
                "005930": {
                    "approved": True,
                    "action": "carry_overnight",
                    "reason": "carry_overnight_approved",
                    "decided_at_epoch": 1778221320,
                    "positive_signals": ["pnl_ok:0.0098", "trend_strength_ok:0.8473"],
                    "blockers": [],
                }
            },
            "closeout_backup_liquidation": {
                "mode": "broker_truth_unresolved_positions_retained",
                "reason": "closeout_broker_truth_unresolved_positions_retained",
                "carry_forward_symbols": ["005930"],
                "unresolved_flatten_symbols": ["078890"],
            },
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day="2026-05-08")

    residual = daily["residual_positions"]
    assert residual["position_count"] == 2
    assert residual["positions"][0]["status"] == "주말 오버나이트 승인(주의)"
    assert residual["positions"][0]["weekend_carry"] is True
    assert residual["positions"][1]["status"] == "정리 필요"
    text = md.read_text(encoding="utf-8")
    assert "## 장마감 잔여 보유 종목" in text
    assert "005930: 주말 오버나이트 승인(주의)" in text
    assert "주말보유 3일" in text
    assert "사유 carry_overnight_approved" in text
    assert "승인 근거: pnl_ok:0.0098, trend_strength_ok:0.8473" in text
    assert "078890: 정리 필요" in text


def test_operator_daily_summary_reconciles_flattened_position_from_lifecycle(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-11"
    state_path = tmp_path / "data" / "state.json"
    _write_json(
        state_path,
        {
            "mock_positions": [
                {
                    "symbol": "000660",
                    "qty": 1,
                    "avg_price": 1890000.0,
                    "current_price": 1878000.0,
                    "position_entry_epoch": 1778479439,
                },
                {"symbol": "005930", "qty": 10, "avg_price": 284500.0, "current_price": 284500.0},
            ],
            "monitor_last_state_by_symbol": {
                "000660": {
                    "posture": "HOLD",
                    "reason": "hold",
                    "updated_at_epoch": 1778480359,
                    "entry_state": {"current_blocking_axis": "pullback_structure"},
                }
            },
            "overnight_decision_by_symbol": {
                "005930": {
                    "approved": False,
                    "action": "flatten_before_close",
                    "reason": "pnl_below_carry_floor:-0.0090",
                    "blockers": ["pnl_below_carry_floor:-0.0090"],
                }
            },
            "closeout_backup_liquidation": {
                "mode": "broker_truth_unresolved_positions_cleared",
                "reason": "closeout_unresolved_positions_cleared_after_sell",
                "carry_forward_symbols": ["005930"],
            },
        },
    )
    _write_json(
        reports / "trades" / day / "1500" / "TRD_20260511_005930_04" / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": day,
            "trade_id": "TRD_20260511_005930_04",
            "symbol": "005930",
            "entry": {"action": "BUY", "price": 284500.0, "qty": 10},
            "exit": {
                "action": "SELL",
                "price": 284500.0,
                "qty": 10,
                "reason_human": "SELL was triggered because eod_flat.",
                "ts": "2026-05-11T06:20:21+00:00",
            },
        },
    )
    _write_json(
        reports / "operator_summary" / "symbols" / "000660" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260511_000660_02",
                "date": day,
                "symbol": "000660",
                "status": "open",
                "last_status": "open",
            }
        ],
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    residual = daily["residual_positions"]
    assert residual["position_count"] == 1
    assert [row["symbol"] for row in residual["positions"]] == ["000660"]
    assert residual["positions"][0]["overnight_reason"] == "오버나이트 판단 기록 없음"
    assert residual["positions"][0]["overnight_decision_missing"] is True
    assert residual["positions"][0]["overnight_missing_reason_code"] == "last_monitor_before_eod_window_no_later_review"
    assert "2026-05-11 15:19:19 KST" in residual["positions"][0]["overnight_missing_detail"]
    assert residual["positions"][0]["position_entry_at_kst"] == "2026-05-11 15:03:59 KST"
    assert residual["closeout_state"]["carry_forward_symbols"] == []
    assert residual["reconciled_closed_positions"][0]["symbol"] == "005930"
    text = md.read_text(encoding="utf-8")
    assert "005930: 잔여 보유" not in text
    assert "장중 청산 확인: 005930은 당일 전량 매도 기록으로 잔여 보유에서 제외했습니다." in text
    assert "000660: 잔여 보유" in text
    assert "000660: 거래 1건 / 완료 0건" in text


def test_operator_daily_summary_reconciles_residuals_from_fresh_account_snapshot(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-29"
    _write_json(
        tmp_path / "data" / "state.json",
        {
            "mock_positions": [
                {"symbol": "005930", "qty": 9, "avg_price": 314000.0, "current_price": 317000.0},
                {"symbol": "122630", "qty": 14, "avg_price": 200252.0, "current_price": 202580.0},
            ],
            "monitor_last_state_by_symbol": {},
            "overnight_decision_by_symbol": {},
            "closeout_backup_liquidation": {},
        },
    )
    _write_json(
        tmp_path / "data" / "logs" / "kiwoom_account_snapshots" / day / "latest.json",
        {
            "schema_version": "kiwoom_account_snapshot.v1",
            "day": day,
            "generated_at": "2026-05-29T07:04:53+00:00",
            "summary": {"api_call_count": 19, "ok_count": 19, "error_count": 0},
            "path": str(tmp_path / "data" / "logs" / "kiwoom_account_snapshots" / day / "snapshot.json"),
            "calls": [
                {
                    "api_id": "kt00018",
                    "status": "ok",
                    "payload": {"acnt_evlt_remn_indv_tot": [], "return_code": 0},
                },
                {
                    "api_id": "kt00004",
                    "status": "ok",
                    "payload": {"stk_acnt_evlt_prst": [], "return_code": 0},
                },
            ],
        },
    )

    md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    residual = daily["residual_positions"]
    assert residual["position_count"] == 0
    assert residual["account_snapshot_reconciliation"]["fresh_after_closeout_window"] is True
    assert residual["account_snapshot_reconciliation"]["position_count"] == 0
    assert [row["symbol"] for row in residual["reconciled_closed_positions"]] == ["005930", "122630"]
    assert {
        row["reason"] for row in residual["reconciled_closed_positions"]
    } == {"fresh_account_snapshot_position_absent_after_closeout"}
    text = md.read_text(encoding="utf-8")
    assert "account snapshot: fresh_after_1520 / positions 0 / 2026-05-29 16:04:53 KST" in text
    assert "005930: ?붿뿬 蹂댁쑀" not in text
    assert "122630: ?붿뿬 蹂댁쑀" not in text


def test_operator_daily_summary_keeps_unavailable_truth_as_observation_only(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-05-04"
    trade_id = "TRD_20260504_005930_02"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "last_status": "closed",
                "result_pct": 0.8,
                "hold_seconds": 60,
            }
        ],
    )
    _write_json(
        reports / "trades" / day / trade_id / "reports" / "ai_trade_summary_input.json",
        {
            "truth_surface": {
                "pnl": "unavailable",
                "pnl_pct": -0.009,
                "cost_analysis": {"price_move_pct": 0.008},
            }
        },
    )

    _md, _json, daily = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    metrics = daily["metrics"]
    assert metrics["return_sample_count"] == 0
    assert metrics["unavailable_return_count"] == 1
    assert metrics["observed_return_sample_count"] == 1
    assert metrics["observed_loss_count"] == 1
    assert metrics["win_count"] == 0
    assert metrics["loss_count"] == 0


def test_operator_daily_summary_syncs_strategy_memory_artifacts(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-04-28"
    trade_id = "TRD_20260428_005930_01"
    _write_json(
        reports / "trades" / day / trade_id / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": day,
            "trade_id": trade_id,
            "symbol": "005930",
            "lifecycle": {"entry": {"symbol": "005930"}, "exit": {"symbol": "005930"}},
            "strategist_summary": {"playbook": "defensive", "market_regime": "neutral"},
            "trade_outcome": {"return_pct": -0.4, "pnl": -400},
            "strategist_feedback_input": {
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
            },
        },
    )
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "result_pct": -0.4,
                "hold_seconds": 300,
            }
        ],
    )

    _md, _json, payload = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day=day,
        daily_report_payload={"events": 10, "approvals": 1, "blocks": 0},
    )

    sync = payload["performance_memory_sync"]
    assert sync["status"] == "ok"
    assert sync["total_trades"] == 1
    assert reports.joinpath("performance", day, "summary.json").exists()
    assert reports.joinpath("performance", day, "playbook_stats.json").exists()
    memory_path = reports / "performance" / day / "strategy_memory.json"
    assert memory_path.exists()
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    assert memory["day"] == day
    assert memory["status"] == "ok"
    assert memory["worst_playbooks"] == ["defensive"]
    assert "entry_exit:breakout->peak_drawdown" in (
        memory.get("pattern_performance_snapshot", {}).get("problem_patterns") or []
    )
