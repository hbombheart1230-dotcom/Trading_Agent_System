from __future__ import annotations

from typing import Any, Dict

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
                        "memory_packets": {
                            "daily_strategy_memory": {
                                "status": "ok",
                                "resolved_day": "2026-04-21",
                                "best_playbooks": ["defensive"],
                            },
                            "weekly_strategy_memory": {
                                "status": "ok",
                                "active": True,
                                "resolved_day": "2026-04-21",
                                "sample_day_count": 3,
                            },
                            "monthly_strategy_memory": {
                                "status": "ok",
                                "active": False,
                                "resolved_day": "2026-04-17",
                                "sample_day_count": 1,
                            },
                            "symbol_memory_packet": {
                                "status": "ok",
                                "symbol": "005380",
                                "trade_count": 4,
                            },
                        },
                        "commander_memory_policy": {
                            "application_mode": "surface_only",
                            "active_layers": ["daily", "symbol", "weekly"],
                            "priority_order": ["daily", "symbol", "weekly", "monthly"],
                            "symbol_memory_override_enabled": True,
                            "scanner_bias_enabled": True,
                            "monitor_bias_enabled": True,
                        },
                        "reporter_feedback_packet": {
                            "available": True,
                            "status": "ok",
                            "consumed": True,
                            "feedback_gate_reason": "auto_accepted",
                            "confidence": "high",
                            "source_reports": {
                                "trade_reports": True,
                                "metrics": False,
                                "reporter_analysis": False,
                            },
                            "insight_summary": "Same-day closed trade reports show 3 trades with 1 wins, 2 losses.",
                            "dominant_patterns": [
                                {"name": "same_price_cost_loss_ratio", "detail": "same-price cost-loss trades 2/3", "value": 0.66},
                            ],
                            "recommendation": [
                                "Same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.",
                            ],
                            "trade_report_analysis": {
                                "closed_trade_count": 3,
                                "win_count": 1,
                                "loss_count": 2,
                                "same_price_cost_loss_count": 2,
                                "broker_truth_count": 3,
                                "avg_pnl_pct": -0.003,
                            },
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
    assert surface["strategy_memory"]["scope"] == "aggregated_strategy_memory"
    assert surface["strategy_memory"]["separate_daily_weekly_monthly_packets"] is True
    assert surface["strategy_memory"]["best_playbooks"] == ["defensive"]
    assert surface["commander_memory_policy"]["present"] is True
    assert surface["commander_memory_policy"]["active_layers"] == ["daily", "symbol", "weekly"]
    assert surface["memory_packets"]["weekly"]["sample_day_count"] == 3
    assert surface["memory_packets"]["monthly"]["active"] is False
    assert surface["memory_packets"]["symbol"]["status"] == "ok"
    assert surface["reporter_feedback_packet"]["available"] is True
    assert surface["reporter_feedback_packet"]["consumed"] is True
    assert surface["reporter_feedback_packet"]["source_reports"]["trade_reports"] is True
    assert surface["reporter_feedback_packet"]["trade_report_analysis"]["closed_trade_count"] == 3
    assert surface["reporter_feedback_packet"]["recommendation"][0].startswith("Same-price round trips")
    assert surface["prompt_proven"]["status"]["strategy_memory_present"] is True
    assert surface["prompt_proven"]["status"]["selected_symbol_memory_present"] is False
    assert surface["prompt_proven"]["reporter_feedback_packet"]["available"] is True
    assert surface["reconstructed_trade_context"]["status"]["selected_symbol_memory_rebuilt"] is True
    assert surface["reconstructed_trade_context"]["status"]["reporter_feedback_rebuilt"] is False
    assert surface["usage_trace"]["playbook"] == "defensive"
    assert any("메모리 우선순위와 활성 layer 결정권은 commander가 가졌고" in note for note in surface["usage_trace"]["notes"])
    assert any("raw memory packet 상태는" in note for note in surface["usage_trace"]["notes"])


def test_build_trade_report_memory_surface_falls_back_to_runtime_packets() -> None:
    story_input = {
        "day": "2026-04-21",
        "symbol": "005380",
        "reasoning_trace": {
            "commander_summary": {
                "session_bias": "context_reuse",
            },
            "strategist_summary": {
                "llm_parsed_output": {
                    "playbook": "defensive",
                    "monitor_guidance": "defensive_exit",
                    "scanner_bias": "leader",
                }
            },
        },
    }

    surface = build_trade_report_memory_surface(story_input)

    assert surface["commander_memory_policy"]["present"] is True
    assert surface["commander_memory_policy"]["application_mode"] == "surface_only"
    assert surface["memory_packets"]["daily"]["status"] == "ok"
    assert surface["memory_packets"]["weekly"]["status"] == "ok"
    assert surface["memory_packets"]["monthly"]["status"] == "ok"
    assert surface["selected_symbol_memory"]["symbol"] == "005380"
    assert surface["selected_symbol_memory"]["trade_count"] >= 0
    assert surface["prompt_proven"]["status"]["memory_packets_present"] is False
    assert surface["reconstructed_trade_context"]["status"]["memory_packets_rebuilt"] is True
    assert surface["reconstructed_trade_context"]["status"]["commander_memory_policy_rebuilt"] is True


def test_build_trade_report_memory_surface_prefers_richer_same_day_reporter_feedback(monkeypatch) -> None:
    story_input = {
        "day": "2026-04-23",
        "symbol": "047040",
        "strategist_evidence": {
            "decision_frames": [
                {
                    "payload": {
                        "reporter_feedback_packet": {
                            "available": True,
                            "consumed": True,
                            "status": "ok",
                            "confidence": "high",
                            "source_reports": {
                                "trade_reports": False,
                                "metrics": False,
                                "reporter_analysis": False,
                            },
                            "insight_summary": "thin",
                            "recommendation": ["old"],
                            "trade_report_analysis": {"closed_trade_count": 0},
                        }
                    }
                }
            ]
        },
    }

    def _fake_build_feedback_packet(*, mode: str, payload: Dict[str, Any], reports_root: str, day: str) -> Dict[str, Any]:
        assert mode == "trade_report_fallback"
        assert day == "2026-04-23"
        return {
            "available": True,
            "consumed": True,
            "status": "ok",
            "confidence": "high",
            "source_reports": {
                "trade_reports": True,
                "metrics": False,
                "reporter_analysis": False,
            },
            "insight_summary": "Same-day closed trade reports show 3 trades with 0 wins, 3 losses.",
            "recommendation": ["same-day feedback"],
            "trade_report_analysis": {"closed_trade_count": 3},
        }

    monkeypatch.setattr("libs.reporting.trade_memory_surface.build_strategist_feedback_packet", _fake_build_feedback_packet)

    surface = build_trade_report_memory_surface(story_input)

    assert surface["reporter_feedback_packet"]["available"] is True
    assert surface["reporter_feedback_packet"]["source_reports"]["trade_reports"] is True
    assert surface["reporter_feedback_packet"]["trade_report_analysis"]["closed_trade_count"] == 3
    assert surface["reporter_feedback_packet"]["recommendation"] == ["same-day feedback"]
    assert surface["prompt_proven"]["reporter_feedback_packet"]["source_reports"]["trade_reports"] is False
    assert surface["reconstructed_trade_context"]["status"]["reporter_feedback_rebuilt"] is True


def test_render_trade_report_markdown_surfaces_memory_audit_sections() -> None:
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
                "separate_daily_weekly_monthly_packets": True,
                "status": "ok",
                "requested_day": "2026-04-21",
                "resolved_day": "2026-04-17",
                "best_playbooks": ["defensive"],
                "worst_playbooks": ["defensive"],
                "recent_failures": ["playbook:defensive"],
            },
            "commander_memory_policy": {
                "present": True,
                "application_mode": "surface_only",
                "active_layers": ["daily", "symbol"],
                "priority_order": ["daily", "symbol", "weekly", "monthly"],
                "symbol_memory_override_enabled": True,
                "scanner_bias_enabled": True,
                "monitor_bias_enabled": True,
            },
            "memory_packets": {
                "daily": {"status": "ok", "active": True, "resolved_day": "2026-04-21", "best_playbook_count": 1},
                "weekly": {"status": "ok", "active": False, "resolved_day": "2026-04-17", "sample_day_count": 1},
                "monthly": {"status": "ok", "active": False, "resolved_day": "2026-04-17", "sample_day_count": 1},
                "symbol": {"status": "확인되지 않음", "active": False, "symbol": "005380", "trade_count": 0},
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
                    "전략 메모리는 집계형 strategy_memory로 전략가에 전달됐습니다.",
                    "메모리 우선순위와 활성 layer 결정권은 commander가 가졌고, active layer / priority는 daily, symbol / daily, symbol, weekly, monthly입니다.",
                    "raw memory packet 상태는 daily=ok, weekly=ok(1days), monthly=ok(1days), symbol=확인되지 않음입니다.",
                ],
            },
        },
    }
    markdown = render_trade_report_markdown(report)

    assert "## 전략가 프롬프트에서 직접 확인된 메모리" in markdown
    assert "## 거래 설명용 사후 복원 메모리" in markdown
    assert "전략가 프롬프트에서는 전략 메모리 확인, 당일 리포터 피드백 확인, 읽기 모델 요약 미확인, 종목 메모리 미확인이 직접 확인됐습니다." in markdown
    assert "지휘관은 실제 반영 레이어를 당일, 종목으로 두고, 우선순위는 당일 -> 종목 -> 주간 -> 월간으로 정해 전략가에 직접 넘겼습니다." in markdown
    assert "프롬프트에 직접 남은 메모리 묶음 상태는 당일=정상 기록, 활성, 주간=정상 기록, 1days, 보조 참고, 월간=정상 기록, 1days, 보조 참고, 종목=확인되지 않음, 보조 참고입니다." in markdown
    assert "이 거래는 전략가 프롬프트만으로 대부분 설명돼, 사후 메모리 복원은 크지 않았습니다." in markdown
