from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime
from libs.runtime.resilience_state import (
    RUNTIME_RESILIENCE_CONTRACT_VERSION,
    ensure_runtime_resilience_state,
)


def test_m23_1_resilience_contract_defaults_are_injected():
    out = ensure_runtime_resilience_state({})

    assert out["resilience"]["contract_version"] == RUNTIME_RESILIENCE_CONTRACT_VERSION
    assert out["resilience"]["degrade_mode"] is False
    assert out["resilience"]["degrade_reason"] == ""
    assert out["resilience"]["incident_count"] == 0
    assert out["resilience"]["cooldown_until_epoch"] == 0
    assert out["resilience"]["last_error_type"] == ""

    assert out["circuit"]["strategist"]["state"] == "unknown"
    assert out["circuit"]["strategist"]["fail_count"] == 0
    assert out["circuit"]["strategist"]["open_until_epoch"] == 0
    assert out["circuit"]["strategist"]["last_error_type"] == ""


def test_m23_1_resilience_contract_normalizes_legacy_fields():
    state: Dict[str, Any] = {
        "resilience": {
            "degrade_mode": "true",
            "incident_count": "4",
            "cooldown_until_epoch": "1234",
            "degrade_reason": "provider_failures",
            "last_error_type": "TimeoutError",
        },
        "circuit_state": "OPEN",
        "circuit_fail_count": "3",
        "circuit_open_until_epoch": "5678",
    }

    out = ensure_runtime_resilience_state(state)

    assert out["resilience"]["degrade_mode"] is True
    assert out["resilience"]["incident_count"] == 4
    assert out["resilience"]["cooldown_until_epoch"] == 1234
    assert out["resilience"]["degrade_reason"] == "provider_failures"
    assert out["resilience"]["last_error_type"] == "TimeoutError"

    assert out["circuit"]["strategist"]["state"] == "open"
    assert out["circuit"]["strategist"]["fail_count"] == 3
    assert out["circuit"]["strategist"]["open_until_epoch"] == 5678


def test_m23_1_commander_runtime_injects_resilience_contract():
    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["path"] = "graph_spine"
        return state

    out = run_commander_runtime({}, graph_runner=graph_runner)

    assert out["path"] == "graph_spine"
    assert out["resilience"]["contract_version"] == RUNTIME_RESILIENCE_CONTRACT_VERSION
    assert out["circuit"]["strategist"]["state"] == "unknown"
