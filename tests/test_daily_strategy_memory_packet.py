from __future__ import annotations

import json
from pathlib import Path

from libs.runtime.daily_strategy_memory_packet import build_daily_strategy_memory_packet


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_daily_strategy_memory_packet_exposes_common_shape(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _write_json(
        reports_root / "performance" / "2026-04-21" / "strategy_memory.json",
        {
            "schema_version": "strategy_memory.v1",
            "day": "2026-04-21",
            "best_playbooks": ["defensive"],
            "worst_playbooks": ["breakout"],
            "recent_failures": ["playbook:breakout", "too_extended_from_vwap"],
            "recent_success_patterns": ["playbook:defensive"],
            "playbook_performance_snapshot": {
                "defensive": {"usage_count": 3, "win_rate": 0.67, "avg_return": 0.012, "stability_score": 0.8},
                "breakout": {"usage_count": 1, "win_rate": 0.0, "avg_return": -0.006, "stability_score": 0.1},
            },
            "market_condition_bias": {
                "regime_bias": {
                    "neutral": {"win_rate": 0.5, "avg_return": 0.003, "trade_count": 4}
                },
                "preferred_regimes": ["neutral"],
                "avoid_regimes": [],
            },
            "reporter_analysis_digest": {
                "system_health": "RED",
                "top_scanner_sources": ["top_value"],
                "top_monitor_reasons": ["volume_insufficient", "too_extended_from_vwap"],
                "top_supervisor_blockers": ["noop_intent_skipped"],
                "dominant_risks": ["guard_blocks"],
                "route_mix": {
                    "monitor_only_ratio": 0.75,
                    "cached_strategist_ratio": 0.08,
                    "full_cycle_ratio": 0.07,
                },
                "incident_total": 1,
            },
            "advisory_only": True,
        },
    )
    _write_json(
        reports_root / "metrics" / "metrics_2026-04-21.json",
        {
            "day": "2026-04-21",
            "route_source": "canonical_commander_preferred",
            "route_selected_total": {"monitor_only": 9, "cached_strategist": 1, "full_cycle": 2},
            "strategist_mode_total": {"fallback": 4, "cached": 1},
            "scanner_monitor_alignment_total": {"guard_block": 7, "aligned": 2},
            "no_trade_reason_total": {"too_extended_from_vwap": 5, "volume_insufficient": 3},
            "intents_blocked_by_reason": {"noop_intent_skipped": 4},
        },
    )
    _write_json(
        reports_root / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-04-21.json",
        {
            "day": "2026-04-21",
            "report_focus_targets": ["exit_quality", "guard_blocks"],
            "monitor_evaluation": {
                "monitor_status": "stable",
                "monitor_reason_top": {"too_extended_from_vwap": 6, "volume_insufficient": 3},
            },
            "scanner_evaluation": {"scanner_selection_status": "appropriate"},
            "supervisor_activity": {"blocked_reason_top": {"noop_intent_skipped": 4}},
            "operator_facing_summary": {"system_health": "RED"},
            "decision_chains": {
                "chains": [
                    {"strategist_frame": {"market_regime": "neutral"}},
                    {"strategist_frame": {"market_regime": "neutral"}},
                ]
            },
        },
    )

    packet = build_daily_strategy_memory_packet(
        state={"reports_root": str(reports_root), "day": "2026-04-21"}
    )

    assert packet["status"] == "ok"
    assert packet["active"] is True
    assert packet["memory_type"] == "daily"
    assert packet["window"]["label"] == "same_day"
    assert packet["sample_quality"]["trade_count"] == 4
    assert packet["source_performance"]["top_value"]["sample_days"] == 1
    assert packet["failure_patterns"]["dominant_failures"][0] == "playbook:breakout"
    assert packet["execution_risk"]["preferred_risk_posture"] == "defensive"
    assert packet["execution_risk"]["route_source"] == "canonical_commander_preferred"
    assert packet["source_context"]["report_focus_targets"] == ["exit_quality", "guard_blocks"]
    assert packet["regime_stats"]["neutral"]["observation_count"] == 2
    assert packet["recommended_bias_inputs"]["monitor"]["volume_ratio_min_delta"] > 0.0
    assert packet["recommended_bias_inputs"]["commander"]["report_focus_targets"] == ["exit_quality", "guard_blocks"]
    assert packet["summary_detail"]["headline"]
