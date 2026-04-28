from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.trade_memory_application_surface import build_trade_memory_application_surface
from libs.reporting.trade_report_ai import render_trade_report_markdown


def test_build_trade_memory_application_surface_reads_canonical_bias_artifacts(tmp_path: Path) -> None:
    scanner_path = tmp_path / "scanner.json"
    monitor_path = tmp_path / "monitor.json"
    scanner_path.write_text(
        json.dumps(
            {
                "candidate_selection_reason": {
                    "scanner_memory_bias_applied": True,
                    "scanner_memory_bias_summary": {
                        "enabled": True,
                        "active_layers": ["daily"],
                        "source_delta_keys": ["top_value"],
                        "symbol_adjustment_count": 1,
                        "reason": ["daily failures dominate today"],
                        "bias_source": "commander_memory_bias.v1",
                    },
                    "scanner_memory_bias": {
                        "enabled": True,
                        "active_layers": ["daily"],
                        "source_weight_delta": {"top_value": 0.1},
                        "symbol_adjustments": {"005380": {"delta": 0.006}},
                        "reason": ["daily failures dominate today"],
                    },
                    "candidate_memory_bias_adjustments": [
                        {
                            "symbol": "005380",
                            "memory_bias_adjustment": 0.006,
                            "memory_bias_adjustments": [{"kind": "symbol", "symbol": "005380", "delta": 0.006}],
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monitor_path.write_text(
        json.dumps(
            {
                "threshold_snapshot": {
                    "monitor_memory_bias_applied": True,
                    "monitor_memory_bias_summary": {
                        "enabled": True,
                        "active_layers": ["daily"],
                        "entry_delta_keys": ["volume_ratio_min"],
                        "risk_posture": "defensive",
                        "reason": ["daily breakout chase failed"],
                        "bias_source": "commander_memory_bias.v1",
                    },
                    "monitor_memory_bias": {
                        "enabled": True,
                        "active_layers": ["daily"],
                        "entry_policy_delta": {"volume_ratio_min": 0.05},
                        "risk_posture": "defensive",
                        "reason": ["daily breakout chase failed"],
                    },
                    "monitor_memory_bias_deltas": [
                        {"field": "volume_ratio_min", "delta": 0.05, "from": 0.68, "to": 0.73}
                    ],
                    "effective_policy_source": "monitor_memory_bias_adjusted",
                },
                "monitor_memory_bias_hold_applied": True,
                "monitor_memory_bias_hold_deltas": [
                    {"field": "confirm_ticks", "delta": -1, "from": 2, "to": 1}
                ],
                "monitor_memory_bias_exit_applied": True,
                "monitor_memory_bias_exit_deltas": [
                    {"field": "stop_loss_pct", "delta": -0.005, "from": 0.02, "to": 0.015}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    surface = build_trade_memory_application_surface(
        {
            "symbol": "005380",
            "artifacts": {
                "canonical_scanner_json": str(scanner_path),
                "canonical_monitor_json": str(monitor_path),
            },
        }
    )

    assert surface["status"]["any_captured"] is True
    assert surface["scanner_memory_bias"]["captured"] is True
    assert surface["scanner_memory_bias"]["applied"] is True
    assert surface["scanner_memory_bias"]["source_weight_delta"] == {"top_value": 0.1}
    assert surface["scanner_memory_bias"]["selected_bias_adjustment"] == 0.006
    assert surface["monitor_memory_bias"]["captured"] is True
    assert surface["monitor_memory_bias"]["applied"] is True
    assert surface["monitor_memory_bias"]["applied_deltas"][0]["field"] == "volume_ratio_min"
    assert surface["monitor_memory_bias"]["hold_applied"] is True
    assert surface["monitor_memory_bias"]["hold_deltas"][0]["field"] == "confirm_ticks"
    assert surface["monitor_memory_bias"]["exit_applied"] is True
    assert surface["monitor_memory_bias"]["exit_deltas"][0]["field"] == "stop_loss_pct"
    assert surface["monitor_memory_bias"]["effective_policy_source"] == "monitor_memory_bias_adjusted"


def test_build_trade_memory_application_surface_prefers_applied_nested_monitor_trace(tmp_path: Path) -> None:
    monitor_path = tmp_path / "monitor.json"
    monitor_path.write_text(
        json.dumps(
            {
                "threshold_snapshot": {
                    "monitor_memory_bias_applied": False,
                    "monitor_memory_bias_summary": {
                        "enabled": False,
                        "active_layers": [],
                        "risk_posture": "neutral",
                    },
                    "commander_memory_application_trace": {
                        "schema_version": "commander_memory_application_trace.v1",
                        "agent": "monitor",
                        "enabled": False,
                        "applied": False,
                        "entry_applied": False,
                        "hold_applied": False,
                        "exit_applied": False,
                        "not_applied_reason": "bias_disabled",
                        "active_layers": [],
                    },
                },
                "entry_decision_details": [
                    {
                        "payload": {
                            "policy_ref": {
                                "commander_memory_application_trace": {
                                    "schema_version": "commander_memory_application_trace.v1",
                                    "agent": "monitor",
                                    "enabled": True,
                                    "applied": True,
                                    "entry_applied": True,
                                    "hold_applied": False,
                                    "exit_applied": True,
                                    "not_applied_reason": "",
                                    "active_layers": ["symbol"],
                                    "risk_posture": "defensive",
                                    "entry_deltas": [
                                        {"field": "breakout_buffer_pct", "delta": 0.001, "from": 0.0, "to": 0.001}
                                    ],
                                    "exit_deltas": [
                                        {"field": "peak_drawdown_exit_pct", "delta": -0.002, "from": 0.005, "to": 0.003}
                                    ],
                                }
                            }
                        }
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    surface = build_trade_memory_application_surface(
        {
            "symbol": "005930",
            "artifacts": {
                "canonical_monitor_json": str(monitor_path),
            },
        }
    )

    monitor = surface["monitor_memory_bias"]
    assert monitor["captured"] is True
    assert monitor["enabled"] is True
    assert monitor["applied"] is True
    assert monitor["exit_applied"] is True
    assert monitor["active_layers"] == ["symbol"]
    assert monitor["not_applied_reason"] == ""
    assert monitor["applied_deltas"][0]["field"] == "breakout_buffer_pct"
    assert monitor["exit_deltas"][0]["field"] == "peak_drawdown_exit_pct"


def test_render_trade_report_markdown_surfaces_memory_application_section() -> None:
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
        "shared_facts": {"symbol": "005380", "trade_id": "TRD_20260421_005380_01", "action": "SELL", "status": "closed"},
        "truth_surface": {"status": {}, "price": {}, "pnl": {}, "availability": {}},
        "memory_surface": {
            "status": {},
            "strategy_memory": {},
            "commander_memory_policy": {
                "present": True,
                "application_mode": "surface_only",
                "active_layers": ["daily"],
                "priority_order": ["daily", "weekly", "monthly", "symbol"],
                "scanner_bias_enabled": True,
                "monitor_bias_enabled": True,
                "symbol_memory_override_enabled": False,
            },
            "memory_packets": {},
            "selected_symbol_memory": {},
            "reporter_feedback_packet": {},
            "read_model_facts": {},
            "usage_trace": {},
            "prompt_proven": {
                "commander_memory_policy": {
                    "application_mode": "surface_only",
                    "active_layers": [],
                    "priority_order": ["daily", "weekly", "monthly", "symbol"],
                    "scanner_bias_enabled": False,
                    "monitor_bias_enabled": False,
                    "symbol_memory_override_enabled": False,
                }
            },
        },
        "memory_application_surface": {
            "status": {"scanner_captured": True, "monitor_captured": True, "any_captured": True},
            "scanner_memory_bias": {
                "captured": True,
                "enabled": True,
                "applied": True,
                "active_layers": ["daily"],
                "source_weight_delta": {"top_value": 0.1, "top_change_rate": -0.25},
                "selected_symbol": "005380",
                "selected_bias_adjustment": 0.006,
                "reason": ["daily failures dominate today"],
            },
            "monitor_memory_bias": {
                "captured": True,
                "enabled": True,
                "applied": True,
                "active_layers": ["daily"],
                "applied_deltas": [{"field": "volume_ratio_min", "delta": 0.05, "from": 0.68, "to": 0.73}],
                "risk_posture": "defensive",
                "effective_policy_source": "monitor_memory_bias_adjusted",
            },
        },
    }

    markdown = render_trade_report_markdown(report)

    assert "## 실제로 적용된 결정론적 메모리 bias" in markdown
    assert "[전략가 입력 시점] 활성 레이어=-; 우선순위=당일 -> 주간 -> 월간 -> 종목; scanner bias=꺼짐; monitor bias=꺼짐" in markdown
    assert "[스캐너 적용 시점] captured=켜짐; enabled=켜짐; applied=적용됨; active_layers=당일" in markdown
    assert "[모니터 적용 시점] captured=켜짐; enabled=켜짐; entry=적용됨; hold=미적용; exit=미적용; active_layers=당일" in markdown
    assert "[최신 커맨더 상태] 활성 레이어=당일; 우선순위=당일 -> 주간 -> 월간 -> 종목; scanner bias=켜짐; monitor bias=켜짐" in markdown
    assert "[시점 차이] 최신 커맨더 상태는 전략가 프롬프트 이후 실행/복원 기준이라 전략가 입력 시점과 다를 수 있습니다." in markdown
    assert "스캐너 메모리 가중치는 실제 후보 점수에 적용된 상태이며, 실제 반영 레이어는 당일입니다." in markdown
    assert "스캐너 소스 가중치 변화는 top_value +0.100, top_change_rate -0.250입니다." in markdown
    assert "이번 거래 후보 005380에는 메모리 기반 가감점 +0.006이 반영됐습니다." in markdown
    assert "모니터 메모리 조정은 진입 정책에 적용된 상태이며, 실제 반영 레이어는 당일입니다." in markdown
    assert "진입 정책 변화는 volume_ratio_min 0.680 -> 0.730 (+0.050)입니다." in markdown


def test_render_trade_report_markdown_marks_uncaptured_memory_application() -> None:
    report = {
        "trade_id": "TRD_20260421_OLD_01",
        "action": "SELL",
        "symbol": "005930",
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
        "shared_facts": {"symbol": "005930", "trade_id": "TRD_20260421_OLD_01", "action": "SELL", "status": "closed"},
        "truth_surface": {"status": {}, "price": {}, "pnl": {}, "availability": {}},
        "memory_surface": {"status": {}, "strategy_memory": {}, "commander_memory_policy": {}, "memory_packets": {}, "selected_symbol_memory": {}, "reporter_feedback_packet": {}, "read_model_facts": {}, "usage_trace": {}},
        "memory_application_surface": {
            "status": {"scanner_captured": False, "monitor_captured": False, "any_captured": False},
            "scanner_memory_bias": {"captured": False},
            "monitor_memory_bias": {"captured": False},
        },
    }

    markdown = render_trade_report_markdown(report)

    assert "스캐너 메모리 가중치의 실제 delta는 이 거래 artifact에 기록되지 않았습니다." in markdown
    assert "모니터 메모리 조정의 실제 delta는 이 거래 artifact에 기록되지 않았습니다." in markdown
