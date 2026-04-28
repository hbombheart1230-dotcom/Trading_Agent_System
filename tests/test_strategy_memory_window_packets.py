from __future__ import annotations

import json
from pathlib import Path

from libs.runtime.monthly_strategy_memory_packet import build_monthly_strategy_memory_packet
from libs.runtime.weekly_strategy_memory_packet import build_weekly_strategy_memory_packet


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_weekly_strategy_memory_packet_aggregates_recent_days(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _write_json(
        reports_root / "performance" / "2026-04-17" / "strategy_memory.json",
        {
            "schema_version": "strategy_memory.v1",
            "day": "2026-04-17",
            "best_playbooks": ["defensive", "pullback"],
            "worst_playbooks": ["breakout"],
            "recent_failures": ["playbook:breakout"],
                "recent_success_patterns": ["playbook:defensive"],
                "playbook_performance_snapshot": {
                    "defensive": {"usage_count": 2, "win_rate": 0.5, "avg_return": 0.01, "stability_score": 0.7},
                    "breakout": {"usage_count": 1, "win_rate": 0.0, "avg_return": -0.003, "stability_score": 0.2},
                },
            "pattern_performance_snapshot": {
                "entry_exit_combos": {
                    "breakout -> peak_drawdown": {
                        "trade_count": 1,
                        "win_count": 0,
                        "loss_count": 1,
                        "win_rate": 0.0,
                        "avg_return": -0.003,
                        "symbols": ["005930"],
                    }
                },
                "problem_patterns": ["entry_exit:breakout->peak_drawdown"],
                "working_patterns": [],
                "advisory_only": True,
            },
            "market_condition_bias": {
                "regime_bias": {
                    "neutral": {"win_rate": 0.4, "avg_return": -0.002, "trade_count": 3}
                }
            },
            "reporter_analysis_digest": {
                "system_health": "RED",
                "top_scanner_sources": ["top_value"],
                "top_monitor_reasons": ["volume_insufficient", "breakout_not_ready"],
                "top_supervisor_blockers": ["noop_intent_skipped"],
                "dominant_risks": ["scanner_fit"],
                "route_mix": {
                    "monitor_only_ratio": 0.7,
                    "cached_strategist_ratio": 0.1,
                    "full_cycle_ratio": 0.1,
                },
                "incident_total": 1,
            },
        },
    )
    _write_json(
        reports_root / "performance" / "2026-04-21" / "strategy_memory.json",
        {
            "schema_version": "strategy_memory.v1",
            "day": "2026-04-21",
            "best_playbooks": ["defensive"],
            "worst_playbooks": ["breakout", "chase"],
            "recent_failures": ["playbook:breakout", "playbook:chase"],
                "recent_success_patterns": ["playbook:defensive"],
                "playbook_performance_snapshot": {
                    "defensive": {"usage_count": 3, "win_rate": 0.67, "avg_return": 0.012, "stability_score": 0.8},
                    "chase": {"usage_count": 1, "win_rate": 0.0, "avg_return": -0.002, "stability_score": 0.1},
                },
            "pattern_performance_snapshot": {
                "entry_exit_combos": {
                    "breakout -> peak_drawdown": {
                        "trade_count": 2,
                        "win_count": 0,
                        "loss_count": 2,
                        "win_rate": 0.0,
                        "avg_return": -0.005,
                        "symbols": ["000660"],
                    }
                },
                "problem_patterns": ["entry_exit:breakout->peak_drawdown"],
                "working_patterns": [],
                "advisory_only": True,
            },
            "market_condition_bias": {
                "regime_bias": {
                    "neutral": {"win_rate": 0.5, "avg_return": 0.001, "trade_count": 4}
                }
            },
            "reporter_analysis_digest": {
                "system_health": "RED",
                "top_scanner_sources": ["top_value", "top_change_rate"],
                "top_monitor_reasons": ["too_extended_from_vwap", "volume_insufficient"],
                "top_supervisor_blockers": ["noop_intent_skipped"],
                "dominant_risks": ["guard_blocks"],
                "route_mix": {
                    "monitor_only_ratio": 0.8,
                    "cached_strategist_ratio": 0.08,
                    "full_cycle_ratio": 0.07,
                },
                "incident_total": 0,
            },
        },
    )
    _write_json(
        reports_root / "metrics" / "metrics_2026-04-21.json",
        {
            "day": "2026-04-21",
            "route_source": "canonical_commander_preferred",
            "route_selected_total": {"monitor_only": 8, "cached_strategist": 1, "full_cycle": 2},
            "strategist_mode_total": {"fallback": 4, "cached": 1, "live_llm": 1},
            "scanner_monitor_alignment_total": {"aligned": 2, "guard_block": 6},
            "no_trade_reason_total": {"too_extended_from_vwap": 5, "volume_insufficient": 3},
            "intents_blocked_by_reason": {"noop_intent_skipped": 4},
        },
    )
    _write_json(
        reports_root / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-04-21.json",
        {
            "day": "2026-04-21",
            "report_focus_targets": ["exit_quality", "guard_blocks"],
            "scanner_evaluation": {
                "candidate_source_top": {"kiwoom_market_data": 11},
                "avg_top_score": 0.91,
                "avg_candidate_pool_after_filter": 3.7,
                "selection_status": "appropriate",
                "scanner_selection_status": "appropriate",
            },
            "monitor_evaluation": {
                "monitor_status": "stable",
                "monitor_reason_top": {"too_extended_from_vwap": 6, "volume_insufficient": 3},
            },
            "supervisor_activity": {"blocked_reason_top": {"noop_intent_skipped": 4}},
            "operator_facing_summary": {"system_health": "RED"},
            "decision_chains": {
                "chains": [
                    {"strategist_frame": {"market_regime": "neutral"}},
                    {"strategist_frame": {"market_regime": "neutral"}},
                    {"strategist_frame": {"market_regime": "risk_off"}},
                ]
            },
        },
    )

    packet = build_weekly_strategy_memory_packet(
        state={"reports_root": str(reports_root), "day": "2026-04-21"}
    )

    assert packet["status"] == "ok"
    assert packet["active"] is True
    assert packet["sample_day_count"] == 2
    assert packet["sample_quality"]["usable"] is True
    assert packet["contributing_days"] == ["2026-04-17", "2026-04-21"]
    assert packet["best_playbooks"][0] == "defensive"
    assert "breakout" in packet["worst_playbooks"]
    assert "playbook:breakout" in packet["recent_failures"]
    assert packet["playbook_performance_snapshot"]["defensive"]["sample_days"] == 2
    assert packet["pattern_performance_snapshot"]["entry_exit_combos"]["breakout -> peak_drawdown"]["trade_count"] == 3
    assert packet["pattern_performance_snapshot"]["problem_patterns"] == ["entry_exit:breakout->peak_drawdown"]
    assert packet["memory_type"] == "weekly"
    assert packet["window"]["label"] == "last_5_trading_days"
    assert packet["sample_quality"]["trade_count"] == 7
    assert packet["source_performance"]["top_value"]["sample_days"] == 2
    assert packet["source_performance"]["kiwoom_market_data"]["source_selection_total"] == 11
    assert packet["source_performance"]["kiwoom_market_data"]["avg_top_score"] == 0.91
    assert packet["source_performance"]["kiwoom_market_data"]["selection_status"] == "appropriate"
    assert packet["failure_patterns"]["dominant_monitor_reasons"][0] == "too_extended_from_vwap"
    assert packet["execution_risk"]["preferred_risk_posture"] == "defensive"
    assert packet["execution_risk"]["route_source"] == "canonical_commander_preferred"
    assert packet["execution_risk"]["scanner_status"] == "appropriate"
    assert packet["execution_risk"]["monitor_status"] == "stable"
    assert packet["source_context"]["route_selected_total"]["monitor_only"] == 8
    assert packet["source_context"]["report_focus_targets"] == ["exit_quality", "guard_blocks"]
    assert packet["regime_stats"]["neutral"]["observation_count"] == 2
    assert packet["recommended_bias_inputs"]["scanner"]["source_weight_delta"]["top_value"] > 0.0
    assert packet["recommended_bias_inputs"]["monitor"]["volume_ratio_min_delta"] > 0.0
    assert packet["recommended_bias_inputs"]["commander"]["report_focus_targets"] == ["exit_quality", "guard_blocks"]
    assert packet["summary_detail"]["headline"]
    assert packet["summary_detail"]["bullets"]


def test_monthly_strategy_memory_packet_unavailable_without_artifacts(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    packet = build_monthly_strategy_memory_packet(
        state={"reports_root": str(reports_root), "day": "2026-04-21"}
    )

    assert packet["status"] == "unavailable"
    assert packet["active"] is False
    assert packet["sample_day_count"] == 0
    assert packet["sample_quality"]["usable"] is False
    assert packet["contributing_days"] == []
    assert packet["memory_type"] == "monthly"
    assert packet["sample_quality"]["trade_count"] == 0
    assert packet["recommended_bias_inputs"]["scanner"]["source_weight_delta"] == {}
