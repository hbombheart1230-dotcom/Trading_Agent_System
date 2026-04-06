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