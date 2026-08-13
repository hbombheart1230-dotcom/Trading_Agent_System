from __future__ import annotations

from libs.runtime.commander_memory_policy import build_commander_memory_policy
from libs.runtime.symbol_memory_packet import build_symbol_memory_packet


def test_commander_memory_policy_surfaces_layer_quality_and_thin_window_rationale() -> None:
    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
            },
            "weekly_strategy_memory": {
                "status": "ok",
                "active": False,
                "sample_day_count": 1,
                "sample_quality": {
                    "usable": False,
                    "confidence": 0.31,
                    "trade_count": 1,
                    "max_age_days": 0,
                },
            },
            "monthly_strategy_memory": {
                "status": "ok",
                "active": False,
                "sample_day_count": 2,
                "sample_quality": {
                    "usable": False,
                    "confidence": 0.22,
                    "trade_count": 2,
                    "max_age_days": 0,
                },
            },
            "symbol_memory_packet": {
                "status": "ok",
                "override_eligible": False,
                "override_gate_reason": "insufficient_trade_count",
            },
        },
    )

    assert policy["active_layers"] == ["daily"]
    assert policy["layer_quality"]["weekly"]["confidence"] == 0.31
    assert policy["layer_quality"]["monthly"]["trade_count"] == 2
    assert "weekly_memory_sample_too_thin" in policy["rationale"]
    assert "monthly_memory_sample_too_thin" in policy["rationale"]
    assert "symbol_memory_gate:insufficient_trade_count" in policy["rationale"]


def test_commander_memory_policy_does_not_activate_stale_daily_memory() -> None:
    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {
                "status": "ok",
                "active": False,
                "sample_day_count": 1,
                "sample_quality": {
                    "usable": True,
                    "confidence": 0.62,
                    "trade_count": 1,
                    "max_age_days": 7,
                },
            },
            "weekly_strategy_memory": {},
            "monthly_strategy_memory": {},
            "symbol_memory_packet": {},
        },
    )

    assert policy["active_layers"] == []
    assert policy["scanner_bias_enabled"] is False
    assert policy["monitor_bias_enabled"] is False
    assert "daily_memory_available" in policy["rationale"]


def test_commander_memory_policy_uses_support_context_for_weekly_activation_and_signals() -> None:
    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
                "sample_quality": {"usable": True, "confidence": 0.71, "trade_count": 4, "max_age_days": 0},
                "execution_risk": {
                    "preferred_risk_posture": "defensive",
                    "route_source": "canonical_commander_preferred",
                    "report_focus_targets": ["exit_quality", "guard_blocks"],
                    "system_health": "RED",
                    "avg_monitor_only_ratio": 0.74,
                    "avg_full_cycle_ratio": 0.08,
                    "scanner_status": "appropriate",
                    "monitor_status": "stable",
                },
                "source_context": {
                    "route_source": "canonical_commander_preferred",
                    "report_focus_targets": ["exit_quality", "guard_blocks"],
                    "scanner_status": "appropriate",
                    "monitor_status": "stable",
                },
                "regime_stats": {
                    "neutral": {"avg_return_pct": 0.002, "observation_count": 8},
                },
            },
            "weekly_strategy_memory": {
                "status": "ok",
                "active": True,
                "sample_day_count": 4,
                "sample_quality": {
                    "usable": True,
                    "confidence": 0.68,
                    "trade_count": 12,
                    "max_age_days": 0,
                },
                "execution_risk": {
                    "preferred_risk_posture": "defensive",
                    "route_source": "canonical_commander_preferred",
                    "report_focus_targets": ["exit_quality", "scanner_fit"],
                    "system_health": "RED",
                    "avg_monitor_only_ratio": 0.72,
                    "avg_full_cycle_ratio": 0.09,
                    "scanner_status": "appropriate",
                    "monitor_status": "stable",
                },
                "source_context": {
                    "route_source": "canonical_commander_preferred",
                    "report_focus_targets": ["exit_quality", "scanner_fit"],
                    "scanner_status": "appropriate",
                    "monitor_status": "stable",
                },
                "regime_stats": {
                    "neutral": {"avg_return_pct": 0.001, "observation_count": 6},
                    "risk_off": {"avg_return_pct": -0.003, "observation_count": 2},
                },
            },
            "monthly_strategy_memory": {
                "status": "ok",
                "active": True,
                "sample_day_count": 5,
                "sample_quality": {
                    "usable": True,
                    "confidence": 0.51,
                    "trade_count": 18,
                    "max_age_days": 0,
                },
                "execution_risk": {
                    "preferred_risk_posture": "balanced",
                    "system_health": "AMBER",
                },
                "source_context": {},
                "regime_stats": {},
            },
            "symbol_memory_packet": {
                "status": "ok",
                "override_eligible": False,
                "override_gate_reason": "insufficient_trade_count",
            },
        },
    )

    assert policy["active_layers"] == ["daily", "weekly"]
    assert "weekly_memory_active" in policy["rationale"]
    assert "weekly_route_source:canonical_commander_preferred" in policy["rationale"]
    assert "weekly_risk_posture:defensive" in policy["rationale"]
    assert "monthly_memory_support_context_missing" in policy["rationale"]
    assert policy["layer_quality"]["weekly"]["route_source"] == "canonical_commander_preferred"
    assert policy["layer_quality"]["weekly"]["report_focus_targets"] == ["exit_quality", "scanner_fit"]
    assert policy["policy_signals"]["primary_layer"] == "daily"
    assert policy["policy_signals"]["preferred_risk_posture"] == "defensive"
    assert policy["policy_signals"]["route_source"] == "canonical_commander_preferred"
    assert policy["policy_signals"]["preferred_regimes"] == ["neutral"]


def test_symbol_memory_packet_requires_pattern_quality_for_override_gate() -> None:
    packet = build_symbol_memory_packet(
        state={
            "selected": {"symbol": "000660"},
            "selected_symbol_memory": {
                "symbol": "000660",
                "trade_count": 8,
                "closed_trade_count": 6,
                "win_rate": 0.5,
                "avg_pnl_pct": 0.02,
                "avg_hold_duration_sec": 420.0,
                "dominant_playbook": "unknown",
                "dominant_monitor_blocker": "unknown",
                "repeated_failure_pattern": [],
                "recent_success_pattern": [],
                "data_quality": {
                    "data_source": "symbol_memory",
                    "unknown_fields_ratio": 0.0,
                },
            },
        }
    )

    assert packet["override_eligible"] is False
    assert packet["override_gate_reason"] == "insufficient_pattern_quality"
    assert packet["evidence_strength"] == "thin"


def test_symbol_memory_packet_blocks_override_when_data_quality_is_poor() -> None:
    packet = build_symbol_memory_packet(
        state={
            "selected": {"symbol": "000660"},
            "selected_symbol_memory": {
                "symbol": "000660",
                "trade_count": 9,
                "closed_trade_count": 6,
                "win_rate": 0.44,
                "avg_pnl_pct": -0.03,
                "avg_hold_duration_sec": 510.0,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
                "repeated_failure_pattern": [{"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 3}],
                "recent_success_pattern": [],
                "data_quality": {
                    "data_source": "symbol_memory",
                    "unknown_fields_ratio": 0.72,
                },
            },
        }
    )

    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
            },
            "weekly_strategy_memory": {},
            "monthly_strategy_memory": {},
            "symbol_memory_packet": packet,
        },
    )

    assert packet["override_eligible"] is False
    assert packet["override_gate_reason"] == "poor_data_quality"
    assert packet["data_source"] == "symbol_memory"
    assert "symbol_memory_gate:poor_data_quality" in policy["rationale"]


def test_symbol_memory_packet_blocks_override_when_memory_is_stale() -> None:
    packet = build_symbol_memory_packet(
        state={
            "runtime_day": "2026-04-23",
            "selected": {"symbol": "000660"},
            "selected_symbol_memory": {
                "symbol": "000660",
                "trade_count": 9,
                "closed_trade_count": 6,
                "win_rate": 0.57,
                "avg_pnl_pct": 0.014,
                "avg_hold_duration_sec": 390.0,
                "last_trade_date": "2026-03-20",
                "last_status": "closed",
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
                "repeated_failure_pattern": [{"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 2}],
                "recent_success_pattern": [{"playbook": "pullback", "entry_reason": "reclaim_ready", "exit_reason": "take_profit", "count": 2}],
                "data_quality": {
                    "data_source": "symbol_memory",
                    "unknown_fields_ratio": 0.0,
                },
            },
        }
    )

    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
            },
            "weekly_strategy_memory": {},
            "monthly_strategy_memory": {},
            "symbol_memory_packet": packet,
        },
    )

    assert packet["recency_days"] == 34
    assert packet["override_eligible"] is False
    assert packet["override_gate_reason"] == "stale_symbol_memory"
    assert "symbol_memory_gate:stale_symbol_memory" in policy["rationale"]


def test_symbol_memory_packet_rejects_memory_from_a_different_refresh_target() -> None:
    packet = build_symbol_memory_packet(
        state={
            "selected": {"symbol": "233740"},
            "selected_symbol_memory": {
                "symbol": "233740",
                "trade_count": 12,
                "closed_trade_count": 10,
                "dominant_playbook": "opening_momentum",
                "recent_success_pattern": [{"playbook": "opening_momentum", "count": 4}],
                "data_quality": {"data_source": "symbol_memory", "unknown_fields_ratio": 0.0},
            },
            "commander_decision": {
                "strategist_refresh_context": {"selected_symbol": "001210"}
            },
        }
    )

    assert packet["status"] == "mismatch"
    assert packet["active"] is False
    assert packet["expected_symbol"] == "001210"
    assert packet["memory_symbol"] == "233740"
    assert packet["symbol_consistent"] is False
    assert packet["override_eligible"] is False
    assert packet["override_gate_reason"] == "symbol_memory_mismatch"


def test_commander_memory_policy_can_disable_all_memory_usage_by_env(monkeypatch) -> None:
    monkeypatch.setenv("COMMANDER_MEMORY_USAGE_DISABLED", "true")

    policy = build_commander_memory_policy(
        session_bias="active_selection",
        memory_packets={
            "daily_strategy_memory": {"status": "ok", "active": True},
            "weekly_strategy_memory": {"status": "ok", "active": True, "sample_day_count": 5},
            "monthly_strategy_memory": {"status": "ok", "active": True, "sample_day_count": 10},
            "symbol_memory_packet": {"status": "ok", "override_eligible": True},
        },
    )

    assert policy["application_mode"] == "disabled"
    assert policy["active_layers"] == []
    assert policy["scanner_bias_enabled"] is False
    assert policy["monitor_bias_enabled"] is False
    assert policy["symbol_memory_override_enabled"] is False
    assert policy["disabled_reason"] == "memory_usage_disabled_by_env"
