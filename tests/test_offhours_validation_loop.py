from __future__ import annotations

import json

from graphs.pipelines.offhours_validation import run_offhours_validation_once
from libs.runtime.entrypoints.offhours_validation_loop import main as offhours_main


def test_offhours_validation_once_applies_local_mock_fill() -> None:
    def fake_load_state(state):  # type: ignore[no-untyped-def]
        state["persisted_state"] = {"mock_cash": 1000.0, "mock_positions": []}
        return state

    def fake_save_state(state):  # type: ignore[no-untyped-def]
        state["saved"] = True
        return state

    def fake_build_portfolio_snapshot(state):  # type: ignore[no-untyped-def]
        state["portfolio_snapshot"] = {"cash": 1000.0, "positions": []}
        return state

    def fake_build_risk_context(state):  # type: ignore[no-untyped-def]
        state["risk_context"] = {"open_positions": 0, "daily_pnl_ratio": 0.0}
        return state

    def fake_strategist(state):  # type: ignore[no-untyped-def]
        state["strategist_output"] = {"themes": ["semiconductor"]}
        return state

    def fake_scanner(state):  # type: ignore[no-untyped-def]
        state["selected"] = {"symbol": "AAA", "score": 0.8, "risk_score": 0.1, "confidence": 0.9}
        return state

    def fake_build_market_snapshot(state):  # type: ignore[no-untyped-def]
        state["market_snapshot"] = {"symbol": "AAA", "price": 100.0}
        return state

    def fake_monitor(state):  # type: ignore[no-untyped-def]
        state["intents"] = [{"symbol": "AAA", "side": "BUY", "qty": 2, "thesis": "test"}]
        return state

    def fake_decision(state):  # type: ignore[no-untyped-def]
        state["decision"] = "approve"
        state["decision_reason"] = "within_policy"
        return state

    def fake_execute(state):  # type: ignore[no-untyped-def]
        packet = state.get("decision_packet") if isinstance(state.get("decision_packet"), dict) else {}
        intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
        state["execution"] = {
            "ok": True,
            "allowed": True,
            "reason": "mock_ok",
            "payload": {"mode": "mock"},
            "order": dict(intent),
        }
        return state

    out = run_offhours_validation_once(
        {},
        load_state_fn=fake_load_state,
        save_state_fn=fake_save_state,
        build_portfolio_snapshot_fn=fake_build_portfolio_snapshot,
        build_risk_context_fn=fake_build_risk_context,
        strategist_fn=fake_strategist,
        scanner_fn=fake_scanner,
        build_market_snapshot_fn=fake_build_market_snapshot,
        monitor_fn=fake_monitor,
        decision_fn=fake_decision,
        execute_fn=fake_execute,
    )

    persisted = out.get("persisted_state") if isinstance(out.get("persisted_state"), dict) else {}
    assert out["path"] == "offhours_validation"
    assert str(out.get("run_id") or "").strip() != ""
    assert out["saved"] is True
    assert float(persisted.get("mock_cash") or 0.0) == 800.0
    positions = persisted.get("mock_positions") if isinstance(persisted.get("mock_positions"), list) else []
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAA"
    assert int(positions[0]["qty"]) == 2


def test_offhours_validation_loop_forces_local_mock_mode(monkeypatch, capsys, tmp_path) -> None:
    env_path = tmp_path / ".env"
    state_path = tmp_path / "offhours_state.json"
    event_log_path = tmp_path / "offhours_events.jsonl"
    env_path.write_text("EXECUTION_MODE=real\nALLOW_REAL_EXECUTION=true\n", encoding="utf-8")

    def fake_run_once(state):  # type: ignore[no-untyped-def]
        state["decision"] = "approve"
        state["selected"] = {"symbol": "AAA", "score": 0.8}
        state["intents"] = [{"symbol": "AAA", "side": "BUY", "qty": 1}]
        state["execution"] = {"allowed": True, "reason": "mock_ok"}
        state["persisted_state"] = {"mock_cash": 1000.0, "mock_positions": [{"symbol": "AAA", "qty": 1}]}
        return state

    monkeypatch.setattr("libs.runtime.entrypoints.offhours_validation_loop.run_offhours_validation_once", fake_run_once)

    rc = offhours_main(
        [
            "--env-path",
            str(env_path),
            "--state-path",
            str(state_path),
            "--event-log-path",
            str(event_log_path),
            "--once",
            "--json",
        ]
    )
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["decision"] == "approve"
    assert out["selected_symbol"] == "AAA"
    assert out["execution_allowed"] is True
    assert out["mock_position_count"] == 1
    assert str(__import__("os").environ.get("EXECUTION_MODE")) == "mock"
    assert str(__import__("os").environ.get("ALLOW_REAL_EXECUTION")) == "false"
    assert str(__import__("os").environ.get("STATE_STORE_PATH")) == str(state_path)
    assert str(__import__("os").environ.get("EVENT_LOG_PATH")) == str(event_log_path)
