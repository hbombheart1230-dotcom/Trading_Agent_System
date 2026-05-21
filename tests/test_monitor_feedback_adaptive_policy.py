import pytest
from graphs.commander_runtime import _build_commander_decision

def test_monitor_feedback_and_adaptive_policy_streak():
    state = {
        "mock_monitor_feedback": {
            "dominant_blocker": "reclaim_not_ready",
            "blocker_count": 4,
            "failure_streak": 4,
            "near_ready_flag": False,
            "avg_distance_to_ready": 0.0
        }
    }
    decision = _build_commander_decision(state, mode_value="integrated", phase_value="session", status_value="ok", path_value="")
    
    assert decision["monitor_feedback"]["dominant_blocker"] == "reclaim_not_ready"
    assert decision["adaptive_policy"]["entry_bias_adjustment"] == 0.02
    assert decision["adaptive_policy"]["scan_aggressiveness"] == 0.05
    assert decision["scanner_policy"]["entry_bias_cap"] == 0.02
    assert decision["scanner_policy"]["scan_aggressiveness"] == 0.05

def test_monitor_feedback_near_ready():
    state = {
        "mock_monitor_feedback": {
            "dominant_blocker": "reclaim_not_ready",
            "failure_streak": 1,
            "near_ready_flag": True,
        }
    }
    decision = _build_commander_decision(state, mode_value="integrated", phase_value="session", status_value="ok", path_value="")
    
    assert decision["adaptive_policy"]["entry_bias_adjustment"] == 0.015
    assert decision["adaptive_policy"]["reentry_penalty_adjustment"] == -0.02
    assert decision["scanner_policy"]["recent_symbol_penalty"] == 0.03
    assert decision["scanner_policy"]["entry_bias_cap"] == 0.015

def test_monitor_feedback_long_streak_diversification():
    state = {
        "mock_monitor_feedback": {
            "dominant_blocker": "volume_missing",
            "failure_streak": 6,
            "near_ready_flag": False,
        }
    }
    decision = _build_commander_decision(state, mode_value="integrated", phase_value="session", status_value="ok", path_value="")
    
    assert decision["entry_control"]["mode"] == "preserve_guardrail_no_trade_ok"
    assert decision["adaptive_policy"]["diversification_adjustment"] == 0.0
    assert decision["scanner_policy"]["diversification_bias"] == 0.0


def test_commander_expands_entry_control_when_market_ok_and_repeated_overextension():
    state = {
        "global_signal": {"score": 0.22, "fear_index": {"level": 18.0}},
        "mock_monitor_feedback": {
            "dominant_blocker": "too_extended_from_vwap",
            "failure_streak": 5,
            "near_ready_flag": True,
            "avg_distance_to_ready": 0.82,
        },
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert entry_control["mode"] == "expand_when_market_ok"
    assert entry_control["decision"] == "expand_candidate_pool_and_dynamic_entry_band"
    assert entry_control["allow_dynamic_entry_band"] is True
    assert entry_control["adaptive_max_extended_from_vwap_pct"] == 0.10
    assert entry_control["max_priority_rank"] == 10
    assert decision["scanner_policy"]["max_priority_rank"] == 10
    assert decision["scanner_policy"]["scan_aggressiveness"] == 0.10


def test_commander_preserves_defensive_no_trade_when_market_is_risk_off():
    state = {
        "global_signal": {"score": -0.22, "fear_index": {"level": 31.0}},
        "mock_monitor_feedback": {
            "dominant_blocker": "too_extended_from_vwap",
            "failure_streak": 6,
            "near_ready_flag": True,
            "avg_distance_to_ready": 0.82,
        },
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert entry_control["mode"] == "preserve_defensive_no_trade_ok"
    assert entry_control["allow_dynamic_entry_band"] is False
    assert entry_control["max_priority_rank"] == 10
    assert decision["scanner_policy"]["max_priority_rank"] == 10
    assert decision["scanner_policy"]["scan_aggressiveness"] == 0.0


def test_commander_ignores_inactive_macro_stress_for_candidate_expansion():
    state = {
        "strategist_output": {
            "market_regime": "neutral",
            "market_sentiment": "bullish",
            "macro_stress_overlay": {
                "active": False,
                "stress_flags": ["dollar_strength"],
                "stress_count": 1,
            },
            "candidate_watch_policy": {
                "max_priority_rank": 5,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "reason": "watch leaders while market is constructive",
            },
        },
        "mock_monitor_feedback": {
            "dominant_blocker": "below_vwap_reclaim_not_ready",
            "failure_streak": 6,
            "near_ready_flag": True,
            "avg_distance_to_ready": 0.83,
        },
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert decision["risk_mode"] == "balanced"
    assert entry_control["market_supportive"] is True
    assert entry_control["mode"] == "expand_when_market_ok"
    assert entry_control["candidate_watch_policy_effect"] == "commander_expanded_repeated_blocker"
    assert entry_control["max_priority_rank"] == 10
    assert decision["scanner_policy"]["max_priority_rank"] == 10


def test_commander_applies_strategist_candidate_watch_policy_when_present():
    state = {
        "global_signal": {"score": 0.18, "fear_index": {"level": 18.0}},
        "strategist_output": {
            "playbook": "breakout",
            "final_playbook": "breakout",
            "tactical_strategy": "opening_range_breakout",
            "candidate_watch_policy": {
                "source": "strategist_visibility_proposal",
                "behavior_effect": "visibility_only",
                "max_priority_rank": 7,
                "max_runner_ups": 4,
                "cascade_enabled": True,
                "cascade_allowed_reasons": ["too_extended_from_vwap", "breakout_not_ready"],
                "cascade_blocked_reasons": ["cost_filter_failed", "risk_policy_block"],
                "reason": "opening breakout can watch beyond rank one",
            },
        },
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert entry_control["candidate_watch_policy_applied"] is True
    assert entry_control["candidate_watch_policy_effect"] == "commander_clamped_execution"
    assert entry_control["max_priority_rank"] == 7
    assert entry_control["max_runner_ups"] == 4
    assert entry_control["cascade_enabled"] is True
    assert decision["scanner_policy"]["max_priority_rank"] == 7
    assert decision["scanner_policy"]["max_runner_ups"] == 4


def test_commander_clamps_defensive_candidate_watch_policy_in_risk_off():
    state = {
        "global_signal": {"score": -0.22, "fear_index": {"level": 31.0}},
        "strategist_output": {
            "playbook": "breakout",
            "final_playbook": "breakout",
            "tactical_strategy": "opening_range_breakout",
            "candidate_watch_policy": {
                "max_priority_rank": 10,
                "max_runner_ups": 9,
                "cascade_enabled": True,
                "reason": "llm requested broad watch",
            },
        },
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert entry_control["candidate_watch_policy_applied"] is True
    assert entry_control["max_priority_rank"] == 3
    assert entry_control["max_runner_ups"] == 2
    assert decision["scanner_policy"]["max_priority_rank"] == 3


def test_commander_opens_defensive_top3_when_rank1_repeatedly_blocked_with_capacity():
    state = {
        "global_signal": {"score": -0.22, "fear_index": {"level": 31.0}},
        "strategist_output": {
            "playbook": "defensive",
            "final_playbook": "defensive",
            "tactical_strategy": "defensive_observe",
            "candidate_watch_policy": {
                "source": "strategist_visibility_proposal",
                "behavior_effect": "visibility_only",
                "max_priority_rank": 1,
                "max_runner_ups": 0,
                "cascade_enabled": False,
                "reason": "llm requested rank one only",
            },
        },
        "mock_monitor_feedback": {
            "dominant_blocker": "below_vwap_reclaim_not_ready",
            "failure_streak": 8,
            "near_ready_flag": True,
            "avg_distance_to_ready": 0.80,
        },
        "risk_context": {"max_positions": 3},
        "portfolio_snapshot": {"positions": []},
    }

    decision = _build_commander_decision(
        state,
        mode_value="integrated",
        phase_value="session",
        status_value="ok",
        path_value="",
    )

    entry_control = decision["entry_control"]
    assert entry_control["mode"] == "preserve_defensive_no_trade_ok"
    assert entry_control["decision"] == "defensive_top3_candidate_cascade"
    assert entry_control["max_priority_rank"] == 3
    assert entry_control["max_runner_ups"] == 2
    assert entry_control["cascade_enabled"] is True
    assert decision["scanner_policy"]["max_priority_rank"] == 3
    assert decision["scanner_policy"]["max_runner_ups"] == 2
