from __future__ import annotations

from libs.reporting.quant_tactic_report import quant_tactic_surface, render_quant_tactic_report_lines
from libs.reporting.trade_report_ai import render_trade_report_markdown, render_trade_summary_markdown
from libs.reporting.trade_story_pipeline import build_monitor_reason_human


def _report() -> dict:
    return {
        "trade_id": "TRD_Q7",
        "symbol": "005930",
        "action": "SELL",
        "status": "closed",
        "story_type": "trade_closed",
        "execution_mode_label": "mock",
        "shared_facts": {"action": "SELL", "exit_reason": "intraday_low_break"},
        "truth_surface": {
            "status": {"status": "closed"},
            "price": {"broker_buy_price": 70000, "broker_fill_price": 69900},
            "pnl": {"value": -1000, "pct": -0.0014, "pnl_truth_source": "ka10077"},
        },
        "strategist_summary": {"summary": "strategy", "bullets": []},
        "why_this_symbol_was_chosen": {
            "summary": "selected",
            "bullets": [],
            "tactic_suitability": {"score": 0.42, "tier": "weak"},
        },
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "monitor_snapshot": {
            "posture": "SELL",
            "trigger_type": "intraday_low_break",
            "position_age_seconds": 35,
            "quant_factor_snapshot": {
                "source": "quant_monitor_entry_factor_snapshot.v1",
                "tactic_id": "vwap_reclaim_pullback",
                "factors": {
                    "vwap_distance_pct": -0.003,
                    "volume_ratio": 0.7,
                    "cost_floor_state": "not_met",
                },
                "missing": [],
            },
            "entry_quant_decision": {
                "schema_version": "quant_entry_decision.v1",
                "tactic_id": "vwap_reclaim_pullback",
                "playbook": "pullback",
                "decision": "block_recommended",
                "blockers": ["cost_edge_fail", "volume_confirmation_missing"],
                "warnings": ["weak_tactic_suitability"],
                "commander_override_required": True,
                "override_reason_required_for": ["cost_edge_fail"],
                "cost_edge": {
                    "ok": False,
                    "cost_adjusted_edge_pct": -0.001,
                    "cost_drag_pct": 0.002,
                },
                "tactic_suitability": {"score": 0.42, "tier": "weak"},
            },
            "exit_quant_decision": {
                "schema_version": "quant_exit_decision.v1",
                "tactic_id": "vwap_reclaim_pullback",
                "playbook": "pullback",
                "decision": "confirm_before_exit_recommended",
                "exit_reason": "intraday_low_break",
                "hard_exit": False,
                "confirmation_pending": True,
                "blockers": ["exit_confirmation_pending"],
                "warnings": ["early_exit_before_expected_min_hold"],
                "expected_hold_window": {"min_sec": 120, "target_sec": 600, "max_sec": 1800},
                "actual_hold_sec": 35,
                "early_exit_flag": True,
                "hold_window_mismatch": True,
            },
        },
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL"},
    }


def test_quant_tactic_report_surface_and_lines():
    surface = quant_tactic_surface(_report())
    lines = render_quant_tactic_report_lines(_report())

    assert surface["schema_version"] == "quant_tactic_report_surface.v1"
    assert surface["tactic_id"] == "vwap_reclaim_pullback"
    assert any("진입 quant 판단" in line and "진입 차단 권고" in line for line in lines)
    assert any("청산 quant 판단" in line and "청산 전 확인 권고" in line for line in lines)
    assert any("보유시간 비교" in line and "mismatch=예" in line for line in lines)


def test_trade_report_markdown_surfaces_quant_tactic_section():
    markdown = render_trade_report_markdown(_report())
    summary = render_trade_summary_markdown(_report())

    assert "## 전술/퀀트 진단" in markdown
    assert "전술 ID: `vwap_reclaim_pullback`" in markdown
    assert "commander override 필요 항목" in markdown
    assert "청산 전 확인 권고" in markdown
    assert "전술 진단: `vwap_reclaim_pullback`" in summary
    assert "진입 quant 판단" in summary


def test_monitor_reason_human_preserves_quant_decisions():
    monitor = {
        "entry_evaluated": True,
        "entry_triggered": False,
        "entry_quant_decision": {"decision": "block_recommended", "blockers": ["cost_edge_fail"]},
        "exit_quant_decision": {"decision": "hold_watch", "warnings": ["early_exit_before_expected_min_hold"]},
        "quant_factor_snapshot": {"tactic_id": "vwap_reclaim_pullback", "factors": {"cost_floor_state": "not_met"}},
    }
    out = build_monitor_reason_human(monitor, {"action": "WAIT"})

    assert out["entry_quant_decision"]["decision"] == "block_recommended"
    assert out["exit_quant_decision"]["decision"] == "hold_watch"
    assert out["quant_factor_snapshot"]["tactic_id"] == "vwap_reclaim_pullback"
    assert any("Entry quant decision" in line for line in out["bullets"])
