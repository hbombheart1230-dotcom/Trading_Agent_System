from __future__ import annotations

from libs.reporting.strategist_quant_context_report import (
    extract_strategist_quant_context_usage,
    render_strategist_quant_context_usage_lines,
)
from libs.reporting.trade_report_ai import _compact_strategy_refresh_trace, render_trade_report_markdown


def _quant_context() -> dict:
    return {
        "schema_version": "strategist_quant_context.v1",
        "call_kind": "selected_symbol_tactical_refresh",
        "quant_market_context": {
            "scorecard": {
                "available": True,
                "period_key": "2026-W21",
                "quant_memory_feedback": {
                    "feedback_tags": ["entry_blocker:cost_edge_fail", "hold_window:mismatch"]
                },
            }
        },
        "selected_symbol_quant_snapshot": {
            "source": "quant_candidate_factor_snapshot.v1",
            "tactic_id": "vwap_reclaim_pullback",
        },
        "behavior_effect": "observation_only",
    }


def test_strategist_quant_context_usage_lines_from_stage_trace():
    report = {
        "strategist_refresh_trace": {
            "stages": [
                {
                    "stage": "post_scanner_refresh",
                    "label": "2차 후보 확정 후 refresh",
                    "quant_context": _quant_context(),
                }
            ]
        }
    }

    rows = extract_strategist_quant_context_usage(report)
    lines = render_strategist_quant_context_usage_lines(report)

    assert rows[0]["call_kind"] == "selected_symbol_tactical_refresh"
    assert rows[0]["selected_symbol_snapshot_present"] is True
    assert "entry_blocker:cost_edge_fail" in rows[0]["scorecard_summary"]
    assert any("selected_snapshot=quant_candidate_factor_snapshot.v1" in line for line in lines)


def test_compact_strategy_refresh_trace_preserves_quant_context_summary():
    compact = _compact_strategy_refresh_trace(
        {
            "stages": [
                {
                    "stage": "post_scanner_refresh",
                    "label": "2차 후보 확정 후 refresh",
                    "summary": "refresh",
                    "quant_context": _quant_context(),
                }
            ]
        }
    )

    stage = compact["stages"][0]
    assert stage["quant_context_call_kind"] == "selected_symbol_tactical_refresh"
    assert stage["quant_scorecard_available"] is True
    assert stage["quant_feedback_tags"] == ["entry_blocker:cost_edge_fail", "hold_window:mismatch"]
    assert stage["selected_symbol_quant_snapshot_present"] is True


def test_trade_report_markdown_surfaces_strategist_quant_context_usage():
    report = {
        "trade_id": "TRD_Q7_REMAIN",
        "symbol": "005930",
        "action": "SELL",
        "status": "closed",
        "story_type": "trade_closed",
        "execution_mode_label": "mock",
        "shared_facts": {"action": "SELL"},
        "truth_surface": {
            "status": {"status": "closed"},
            "price": {"broker_buy_price": 70000, "broker_fill_price": 69900},
            "pnl": {"value": -1000, "pct": -0.0014},
        },
        "strategist_summary": {"summary": "strategy", "bullets": []},
        "strategist_refresh_trace": {
            "summary": "refresh summary",
            "stages": [
                {
                    "stage": "post_scanner_refresh",
                    "label": "2차 후보 확정 후 refresh",
                    "summary": "refresh",
                    "quant_context": _quant_context(),
                }
            ],
        },
        "strategist_output": {
            "strategy_thesis": {
                "one_line": "VWAP reclaim pullback tactical frame",
                "selected_playbook": "vwap_reclaim_pullback",
            }
        },
        "why_this_symbol_was_chosen": {"summary": "selected", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL"},
    }

    markdown = render_trade_report_markdown(report)

    assert "## 전략가 Quant Context 사용" in markdown
    assert "2차 후보 확정 후 refresh" in markdown
    assert "entry_blocker:cost_edge_fail" in markdown
    assert markdown.find("## 전략가 Refresh Trace") < markdown.find("## 전략가 Quant Context 사용") < markdown.find("## 전략가 출력 근거")
