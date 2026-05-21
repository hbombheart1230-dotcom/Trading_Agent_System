from __future__ import annotations

import json
from pathlib import Path

from libs.runtime.quant.memory import load_quant_memory_packet
from libs.runtime.quant.scorecard import build_quant_scorecard, compact_scorecard_for_llm


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_quant_memory_packet_from_operator_weekly_summary(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "operator_summary" / "weekly" / "2026-W21" / "weekly_summary.json",
        {
            "period_type": "weekly",
            "period_key": "2026-W21",
            "metrics": {
                "trade_count": 3,
                "closed_trade_count": 3,
                "win_rate": 0.3333,
                "avg_return_pct": -0.5,
                "avg_hold_seconds": 120,
                "return_basis": "truth_surface_net",
            },
            "pattern_performance": {
                "strategist": {
                    "by_tactical_strategy": [
                        {
                            "name": "leader_vwap_reclaim_pullback",
                            "count": 3,
                            "closed_or_realized_count": 3,
                            "win_rate": 0.3333,
                            "avg_return_pct": -0.5,
                            "avg_hold_seconds": 120,
                        }
                    ]
                },
                "monitor_exit": {
                    "by_exit_reason": [
                        {
                            "name": "intraday_low_break",
                            "count": 3,
                            "closed_or_realized_count": 3,
                            "win_rate": 0.0,
                            "avg_return_pct": -1.1,
                        }
                    ],
                    "by_cost_floor_state": [
                        {"name": "not_met", "count": 2, "win_rate": 0.0, "avg_return_pct": -0.8}
                    ],
                },
                "scanner": {"by_scanner_rank_bucket": [{"name": "rank1", "count": 1}]},
                "combined": {"by_strategy_scanner_entry_exit": [{"name": "combo", "count": 2}]},
                "quant": {
                    "by_tactic_id": [
                        {"name": "vwap_reclaim_pullback", "count": 3, "closed_or_realized_count": 3, "win_rate": 0.0, "avg_return_pct": -0.9}
                    ],
                    "by_tactic_suitability_tier": [
                        {"name": "weak", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -1.0}
                    ],
                    "by_entry_primary_blocker": [
                        {"name": "cost_edge_fail", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -0.7}
                    ],
                    "by_exit_decision": [
                        {
                            "name": "confirm_before_exit_recommended",
                            "count": 2,
                            "closed_or_realized_count": 2,
                            "win_rate": 0.0,
                            "avg_return_pct": -1.2,
                        }
                    ],
                    "by_exit_confirmation_state": [
                        {"name": "pending", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -1.2}
                    ],
                    "by_exit_hold_window_state": [
                        {"name": "mismatch", "count": 2, "closed_or_realized_count": 2, "win_rate": 0.0, "avg_return_pct": -1.2}
                    ],
                },
            },
        },
    )

    packet = load_quant_memory_packet(reports_root=reports, period_type="weekly", period_key="2026-W21")
    scorecard = build_quant_scorecard(packet)
    compact = compact_scorecard_for_llm(scorecard)

    assert packet["available"] is True
    assert packet["metrics"]["trade_count"] == 3
    assert scorecard["behavior_effect"] == "observation_only"
    assert scorecard["tactic_scorecards"][0]["tactic_id"] == "vwap_reclaim_pullback"
    assert scorecard["tactic_scorecards"][0]["confidence"] == "low"
    assert "intraday_low_break" in scorecard["exit_loss_clusters"]
    assert packet["quant_entry_blocker_rows"][0]["name"] == "cost_edge_fail"
    assert scorecard["quant_memory_feedback"]["feedback_tags"][:3] == [
        "entry_blocker:cost_edge_fail",
        "exit_decision:confirm_before_exit_recommended",
        "hold_window:mismatch",
    ]
    assert compact["quant_memory_feedback"]["behavior_effect"] == "observation_only"
    assert compact["tactic_scorecards"][0]["avg_return_pct"] == -0.5
