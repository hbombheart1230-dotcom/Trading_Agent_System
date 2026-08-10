from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.agent_effectiveness_scorecard import (
    build_agent_effectiveness_scorecard,
)
from libs.runtime.q9_decision_snapshots import (
    capture_pre_refresh_scanner_snapshot,
    capture_scanner_decision_snapshot,
)
from libs.runtime.quant.shadow_candidates import _q9_decision_candidate_rows


def _candidate(symbol: str, score: float) -> dict:
    return {
        "symbol": symbol,
        "rank": 1,
        "score_total": score,
        "confidence": 0.7,
        "risk_score": 0.2,
    }


def test_post_scanner_refresh_preserves_before_and_after_rankings(tmp_path: Path) -> None:
    state = {
        "reports_root": str(tmp_path / "reports"),
        "run_id": "RUN1",
        "ts": "2026-08-07T00:05:00+00:00",
        "scanner_output": {"ranked_candidates": [_candidate("005930", 0.8)]},
        "scanner_candidate_ranking_table": {
            "scanner_intrinsic_control_top20": [_candidate("005930", 0.7)],
            "post_strategist_top10": [_candidate("005930", 0.8)],
        },
        "strategist_output": {"run_id": "S1", "playbook": "pullback"},
        "selected": {"symbol": "005930"},
    }
    capture_scanner_decision_snapshot(state)
    capture_pre_refresh_scanner_snapshot(state)

    state["scanner_output"] = {"ranked_candidates": [_candidate("000660", 0.9)]}
    state["scanner_candidate_ranking_table"] = {
        "scanner_intrinsic_control_top20": [_candidate("005930", 0.7)],
        "post_strategist_top10": [_candidate("000660", 0.9)],
    }
    state["strategist_output"] = {"run_id": "S2", "playbook": "breakout"}
    state["selected"] = {"symbol": "000660"}
    state["runtime_fast_path"] = {
        "reason": "post_scanner_selected_symbol_refresh",
        "strategist_refresh_reason": "selected_symbol_tactical_refresh",
    }
    capture_scanner_decision_snapshot(state)

    payload = json.loads(
        (
            tmp_path
            / "reports"
            / "operator_summary"
            / "daily"
            / "2026-08-07"
            / "q9_decision_windows.json"
        ).read_text(encoding="utf-8")
    )
    refresh = payload["windows"][0]["post_scanner_strategist_refresh"]
    assert refresh["status"] == "OBSERVED"
    assert refresh["before_selected_symbol"] == "005930"
    assert refresh["after_selected_symbol"] == "000660"
    assert refresh["changed_top1"] is True


def test_q9_roles_expose_semantic_scope_without_renaming_legacy_ids() -> None:
    state = {
        "q9_decision_snapshot": {
            "decision_id": "D1",
            "scanner_control": {"top10": [_candidate("005930", 0.7)]},
            "strategist_selection": {
                "strategy_weighted_top10": [_candidate("000660", 0.8)],
                "selected_symbol": "000660",
            },
            "post_scanner_strategist_refresh": {
                "status": "OBSERVED",
                "before_top10": [_candidate("000660", 0.8)],
                "after_top10": [_candidate("005930", 0.9)],
            },
            "commander_final": {},
        }
    }
    rows = _q9_decision_candidate_rows(state, now_epoch=1, opening_minutes=1)
    roles = {row["q9_decision_role"]: row for row in rows}

    assert roles["A_SCANNER_CONTROL"]["q9_semantic_role"] == "SCANNER_INTRINSIC_SAME_UNIVERSE"
    assert roles["A_SCANNER_CONTROL"]["q9_full_strategist_control_available"] is False
    assert roles["B_STRATEGIST_RANKED"]["q9_semantic_role"] == "STRATEGY_WEIGHTED_SCANNER_RANKING"
    assert "R1_PRE_REFRESH_SCANNER" in roles
    assert "R2_POST_REFRESH_SCANNER" in roles


def test_agent_scorecard_separates_full_strategist_overlay_and_refresh() -> None:
    review = {
        "range": {"start": "2026-06-01", "end": "2026-08-07"},
        "evidence": {
            "total_trade_model_count": 100,
            "excluded_trade_model_count": 2,
            "decision_window_attribution": {
                "by_horizon": [
                    {
                        "horizon": "+30m",
                        "strategy_ranking_overlay_comparison_count": 30,
                        "strategy_ranking_overlay_day_count": 3,
                        "average_strategy_ranking_overlay_delta_pct": -0.4,
                        "strategy_ranking_overlay_positive_delta_rate": 0.4,
                        "post_scanner_refresh_comparison_count": 25,
                        "post_scanner_refresh_day_count": 3,
                        "average_post_scanner_refresh_delta_pct": 0.5,
                        "post_scanner_refresh_positive_delta_rate": 0.6,
                        "commander_comparison_count": 0,
                        "commander_day_count": 0,
                    }
                ]
            },
        },
        "component_decisions": {
            "scanner": {
                "decision": "ADJUST_AND_RETEST",
                "relative_ranking_effect_positive": True,
                "absolute_cost_adjusted_edge_positive": False,
            },
            "monitor_entry": {"decision": "RETAIN", "finding": "measurable"},
            "monitor_exit": {"decision": "INSUFFICIENT_EVIDENCE"},
            "full_system": {"decision": "REJECT"},
        },
    }

    result = build_agent_effectiveness_scorecard(review)
    strategist = result["components"]["strategist"]

    assert strategist["full_contribution"]["state"] == "NOT_MEASURABLE"
    assert strategist["ranking_overlay"]["state"] == "DEGRADING"
    assert strategist["post_scanner_refresh"]["state"] == "VALUE_ADD"
    assert result["components"]["scanner"]["relative_ranking_state"] == "VALUE_ADD"
    assert result["components"]["scanner"]["absolute_edge_state"] == "DEGRADING"
    assert result["components"]["commander"]["state"] == "NOT_MEASURABLE"


def test_agent_scorecard_does_not_penalize_missing_evidence() -> None:
    result = build_agent_effectiveness_scorecard(
        {
            "range": {"start": "2026-08-07", "end": "2026-08-07"},
            "evidence": {"decision_window_attribution": {"by_horizon": []}},
            "component_decisions": {},
        }
    )

    strategist = result["components"]["strategist"]
    assert strategist["ranking_overlay"]["state"] == "NOT_MEASURABLE"
    assert strategist["post_scanner_refresh"]["state"] == "NOT_MEASURABLE"
    assert result["components"]["commander"]["state"] == "NOT_MEASURABLE"
