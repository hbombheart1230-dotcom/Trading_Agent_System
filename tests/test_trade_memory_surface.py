from __future__ import annotations

from libs.reporting.trade_memory_surface import build_trade_report_memory_surface
from libs.reporting.trade_report_ai import render_trade_report_markdown


def test_build_trade_report_memory_surface_summarizes_packets() -> None:
    story_input = {
        "symbol": "005380",
        "strategist_evidence": {
            "decision_frames": [
                {
                    "payload": {
                        "strategy_memory": {
                            "status": "ok",
                            "best_playbooks": ["defensive"],
                            "worst_playbooks": ["defensive"],
                            "recent_failures": ["playbook:defensive"],
                            "recent_success_patterns": [],
                        },
                        "reporter_feedback_packet": {
                            "available": False,
                            "status": "auto_ignored",
                            "consumed": False,
                            "feedback_gate_reason": "source_unavailable",
                            "confidence": "none",
                        },
                    }
                }
            ]
        },
        "reasoning_trace": {
            "strategist_summary": {
                "llm_parsed_output": {
                    "playbook": "defensive",
                    "monitor_guidance": "defensive_exit",
                    "scanner_bias": "leader",
                }
            }
        },
    }

    surface = build_trade_report_memory_surface(story_input)

    assert surface["status"]["strategy_memory_used"] is True
    assert surface["status"]["selected_symbol_memory_used"] is False
    assert surface["strategy_memory"]["scope"] == "aggregated_strategy_memory"
    assert surface["strategy_memory"]["best_playbooks"] == ["defensive"]
    assert surface["reporter_feedback_packet"]["status"] == "auto_ignored"
    assert surface["usage_trace"]["playbook"] == "defensive"
    assert any("집계형 strategy_memory" in note for note in surface["usage_trace"]["notes"])
    assert any("005380 종목 메모리는 비어 있었고" in note for note in surface["usage_trace"]["notes"])


def test_render_trade_report_markdown_surfaces_memory_usage_section() -> None:
    report = {
        "trade_id": "TRD_20260421_005380_01",
        "action": "SELL",
        "symbol": "005380",
        "status": "closed",
        "story_type": "simulation trade report",
        "execution_mode_label": "simulation (mock broker)",
        "generation": {"status": "ok", "mode": "local_debug", "model": "minimax/minimax-m2.5"},
        "executive_summary": {"summary": "summary"},
        "market_context_at_entry": {"summary": "context", "bullets": []},
        "strategist_summary": {"summary": "strategist", "bullets": []},
        "why_this_symbol_was_chosen": {"summary": "why", "bullets": []},
        "entry_decision": {"summary": "entry", "bullets": []},
        "holding_monitoring_story": {"summary": "holding", "bullets": []},
        "exit_decision": {"summary": "exit", "bullets": []},
        "scanner_filters": {"summary": "scanner", "bullets": []},
        "guard_approval_result": {"summary": "guard", "bullets": []},
        "execution_quality": {"summary": "execution", "bullets": []},
        "reporter_evaluation": {"summary": "reporter", "bullets": []},
        "errors_weaknesses_improvement_points": {"summary": "weakness", "bullets": []},
        "full_timeline": [],
        "final_operator_conclusion": {"summary": "final", "current_action": "SELL", "watch_next": [], "thesis_invalidation": []},
        "shared_facts": {
            "symbol": "005380",
            "trade_id": "TRD_20260421_005380_01",
            "action": "SELL",
            "status": "closed",
            "pnl": -4813.0,
            "pnl_pct": -0.009,
            "broker_buy_price": 537000.0,
            "broker_fill_price": 537000.0,
            "broker_fee": 3740,
            "broker_tax": 1073,
            "price_truth_source": "broker_fill",
            "pnl_truth_source": "kiwoom.ka10077",
        },
        "truth_surface": {
            "status": {},
            "price": {
                "broker_buy_price": 537000.0,
                "broker_fill_price": 537000.0,
                "price_truth_source": "broker_fill",
            },
            "pnl": {
                "value": -4813.0,
                "pct": -0.009,
                "broker_fee": 3740,
                "broker_tax": 1073,
                "pnl_truth_source": "kiwoom.ka10077",
            },
            "availability": {
                "broker_fill_present": True,
                "account_mark_present": False,
                "monitor_mark_present": False,
                "broker_pnl_present": True,
            },
        },
        "memory_surface": {
            "status": {
                "strategy_memory_used": True,
                "selected_symbol_memory_used": False,
                "reporter_feedback_used": False,
                "read_model_facts_used": False,
            },
            "strategy_memory": {
                "present": True,
                "scope": "aggregated_strategy_memory",
                "status": "ok",
                "requested_day": "2026-04-21",
                "resolved_day": "2026-04-17",
                "best_playbooks": ["defensive"],
                "worst_playbooks": ["defensive"],
                "recent_failures": ["playbook:defensive"],
            },
            "selected_symbol_memory": {
                "present": False,
                "symbol": "005380",
                "trade_count": 0,
            },
            "reporter_feedback_packet": {
                "present": True,
                "available": False,
                "consumed": False,
                "status": "auto_ignored",
                "feedback_gate_reason": "source_unavailable",
                "confidence": "none",
            },
            "read_model_facts": {
                "present": False,
                "recent_trade_count": 0,
                "symbol_pattern_count": 0,
                "symbols": [],
                "daily_summary_present": False,
            },
            "usage_trace": {
                "playbook": "defensive",
                "monitor_guidance": "defensive_exit",
                "scanner_bias": "leader",
                "notes": [
                    "전략 메모리는 일·주·월 분리 패킷이 아니라 누적 집계형 strategy_memory로 전략가에 전달됐습니다.",
                    "005380 종목 메모리는 비어 있었고, 종목별 과거 이력 제약은 직접 반영되지 않았습니다.",
                ],
            },
        },
    }

    markdown = render_trade_report_markdown(report)

    assert "## 메모리 사용" in markdown
    assert "전략 메모리=사용, 종목 메모리=미사용, 리포터 피드백=미사용, 읽기 모델 팩트=미사용입니다." in markdown
    assert "전략 메모리는 집계형 strategy_memory로 전달됐고, status는 ok입니다." in markdown
    assert "전략 메모리 요청일/해석일은 2026-04-21 / 2026-04-17입니다." in markdown
    assert "005380 종목 메모리는 비어 있었고, 종목별 과거 이력 제약은 직접 반영되지 않았습니다." in markdown
    assert "same-day reporter feedback은 auto_ignored 상태였고, gate 사유는 source_unavailable이었습니다." in markdown
    assert "전략가 출력에는 playbook=defensive, monitor_guidance=defensive_exit, scanner_bias=leader가 남았습니다." in markdown
