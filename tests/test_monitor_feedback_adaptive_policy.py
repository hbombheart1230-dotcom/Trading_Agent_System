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
    
    assert decision["adaptive_policy"]["diversification_adjustment"] == 0.03
    assert decision["scanner_policy"]["diversification_bias"] == 0.05


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
    assert entry_control["max_priority_rank"] == 5
    assert decision["scanner_policy"]["max_priority_rank"] == 5
    assert decision["scanner_policy"]["scan_aggressiveness"] == 0.0
