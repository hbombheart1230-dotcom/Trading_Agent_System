from __future__ import annotations

from libs.runtime.circuit_breaker import (
    RuntimeCircuitPolicy,
    gate_runtime_circuit,
    mark_runtime_circuit_failure,
    mark_runtime_circuit_success,
)


def test_m23_2_gate_blocks_open_circuit_before_cooldown():
    state = {
        "circuit": {
            "strategist": {
                "state": "open",
                "fail_count": 2,
                "open_until_epoch": 200,
            }
        }
    }

    gate = gate_runtime_circuit(state, now_epoch=100)
    assert gate["allowed"] is False
    assert gate["reason"] == "circuit_open"
    assert gate["circuit_state"] == "open"


def test_m23_2_gate_transitions_to_half_open_after_cooldown():
    state = {
        "circuit": {
            "strategist": {
                "state": "open",
                "fail_count": 2,
                "open_until_epoch": 90,
            }
        }
    }

    gate = gate_runtime_circuit(state, now_epoch=100)
    assert gate["allowed"] is True
    assert gate["reason"] == "circuit_half_open"
    assert gate["circuit_state"] == "half_open"
    assert state["circuit"]["strategist"]["state"] == "half_open"


def test_m23_2_failure_opens_circuit_on_threshold_and_updates_resilience():
    state = {}
    policy = RuntimeCircuitPolicy(fail_threshold=2, cooldown_sec=30)

    s1 = mark_runtime_circuit_failure(
        state,
        error_type="TimeoutError",
        now_epoch=100,
        policy=policy,
    )
    assert s1["circuit_state"] == "closed"
    assert s1["fail_count"] == 1
    assert state["resilience"]["incident_count"] == 1
    assert state["resilience"]["last_error_type"] == "TimeoutError"

    s2 = mark_runtime_circuit_failure(
        state,
        error_type="TimeoutError",
        now_epoch=101,
        policy=policy,
    )
    assert s2["circuit_state"] == "open"
    assert s2["fail_count"] == 2
    assert s2["open_until_epoch"] == 131
    assert state["resilience"]["incident_count"] == 2
    assert state["resilience"]["cooldown_until_epoch"] == 131


def test_m23_2_success_closes_and_resets_circuit():
    state = {
        "circuit": {
            "strategist": {
                "state": "open",
                "fail_count": 3,
                "open_until_epoch": 200,
                "last_error_type": "TimeoutError",
            }
        }
    }

    out = mark_runtime_circuit_success(state)
    assert out["circuit_state"] == "closed"
    assert out["fail_count"] == 0
    assert out["open_until_epoch"] == 0
    assert state["circuit"]["strategist"]["state"] == "closed"
    assert state["circuit"]["strategist"]["last_error_type"] == ""

