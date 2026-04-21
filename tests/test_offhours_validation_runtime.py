from __future__ import annotations

import os

from libs.runtime.offhours_validation_runtime import (
    apply_runtime_paths,
    build_initial_state,
    enforce_safe_runtime,
    iteration_summary,
    normalize_symbol,
)


def test_build_initial_state_keeps_mock_runtime_mode() -> None:
    out = build_initial_state("005930")
    assert out["offhours_validation"] is True
    assert out["runtime_mode"] == "offhours_validation"
    assert out["exec_context"]["mode"] == "mock"
    assert out["symbol"] == "005930"


def test_enforce_safe_runtime_forces_mock_env(monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("ALLOW_REAL_EXECUTION", "true")
    enforce_safe_runtime()
    assert os.environ["EXECUTION_MODE"] == "mock"
    assert os.environ["ALLOW_REAL_EXECUTION"] == "false"


def test_apply_runtime_paths_sets_env(monkeypatch) -> None:
    monkeypatch.delenv("STATE_STORE_PATH", raising=False)
    monkeypatch.delenv("EVENT_LOG_PATH", raising=False)
    apply_runtime_paths(state_path="a.json", event_log_path="b.jsonl")
    assert os.environ["STATE_STORE_PATH"] == "a.json"
    assert os.environ["EVENT_LOG_PATH"] == "b.jsonl"


def test_iteration_summary_surfaces_mock_position_count() -> None:
    out = iteration_summary(
        {
            "path": "offhours_validation",
            "decision": "approve",
            "decision_reason": "within_policy",
            "selected": {"symbol": "AAA", "score": 0.8},
            "intents": [{"symbol": "AAA", "side": "BUY"}],
            "execution": {"allowed": True, "reason": "mock_ok"},
            "persisted_state": {"mock_cash": 1000.0, "mock_positions": [{"symbol": "AAA", "qty": 1}]},
        },
        iteration=3,
    )
    assert out["iteration"] == 3
    assert out["selected_symbol"] == "AAA"
    assert out["execution_allowed"] is True
    assert out["mock_position_count"] == 1


def test_normalize_symbol_uppercases() -> None:
    assert normalize_symbol(" aBc123 ") == "ABC123"
