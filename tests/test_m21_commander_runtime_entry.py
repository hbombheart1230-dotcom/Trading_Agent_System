from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import (
    _hydrate_strategist_output_cache,
    _run_integrated_chain,
    resolve_runtime_mode,
    resolve_runtime_phase,
    run_commander_runtime,
)
from graphs.commander_runtime import _run_preopen_phase


def test_m21_runtime_entry_defaults_to_graph_spine():
    called = {"graph": 0, "decide": 0, "execute": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        state["path"] = "graph_spine"
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        return state

    out = run_commander_runtime(
        {"x": 1},
        graph_runner=graph_runner,
        decide=decide,
        execute=execute,
    )

    assert out["path"] == "graph_spine"
    assert out["runtime_plan"]["mode"] == "graph_spine"
    assert out["runtime_plan"]["phase"] == "session"
    assert out["runtime_plan"]["agents"] == [
        "commander_router",
        "strategist",
        "scanner",
        "monitor",
        "supervisor",
        "executor",
        "reporter",
    ]
    assert called == {"graph": 1, "decide": 0, "execute": 0}


def test_m21_runtime_entry_runs_decision_packet_mode():
    called = {"graph": 0, "decide": 0, "execute": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        state["decision_packet"] = {"intent": {"action": "NOOP"}, "risk": {}, "exec_context": {}}
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        state["execution"] = {"allowed": True}
        state["path"] = "decision_packet"
        return state

    out = run_commander_runtime(
        {"runtime_mode": "decision_packet", "allow_decision_packet_runtime": True},
        graph_runner=graph_runner,
        decide=decide,
        execute=execute,
    )

    assert out["path"] == "decision_packet"
    assert out["execution"]["allowed"] is True
    assert out["runtime_plan"]["mode"] == "decision_packet"
    assert out["runtime_plan"]["phase"] == "session"
    assert out["runtime_plan"]["agents"] == [
        "commander_router",
        "strategist",
        "supervisor",
        "executor",
        "reporter",
    ]
    assert called == {"graph": 0, "decide": 1, "execute": 1}


def test_m21_runtime_entry_invalid_mode_falls_back_to_graph_spine():
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        state["path"] = "graph_spine"
        return state

    out = run_commander_runtime(
        {"runtime_mode": "unexpected_mode"},
        graph_runner=graph_runner,
    )

    assert out["path"] == "graph_spine"
    assert called["graph"] == 1


def test_m31_runtime_entry_runs_integrated_chain_mode():
    called = {"graph": 0, "decide": 0, "execute": 0, "integrated": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        return state

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["integrated"] += 1
        state["path"] = "integrated_chain"
        state["decision"] = "approve"
        state["execution"] = {"allowed": True}
        return state

    out = run_commander_runtime(
        {"runtime_mode": "integrated_chain"},
        graph_runner=graph_runner,
        integrated_runner=integrated_runner,
        decide=decide,
        execute=execute,
    )

    assert out["path"] == "integrated_chain"
    assert out["runtime_plan"]["mode"] == "integrated_chain"
    assert out["runtime_plan"]["phase"] == "session"
    assert out["runtime_plan"]["agents"] == [
        "commander_router",
        "strategist",
        "scanner",
        "monitor",
        "decision",
        "supervisor",
        "executor",
        "reporter",
    ]
    assert called == {"graph": 0, "decide": 0, "execute": 0, "integrated": 1}


def test_m31_runtime_entry_seeds_commander_decision_for_downstream_agents():
    captured: Dict[str, Any] = {}

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        captured.update(dict(state.get("commander_decision") or {}))
        state["path"] = "integrated_chain"
        state["runtime_status"] = "ok"
        return state

    out = run_commander_runtime(
        {
            "runtime_mode": "integrated_chain",
            "runtime_phase": "session",
            "global_signal": {"score": 0.18, "fear_index": {"level": 19.0}},
        },
        integrated_runner=integrated_runner,
    )

    assert out["path"] == "integrated_chain"
    assert captured["market_regime"] == "risk_on"
    assert captured["session_bias"] == "active_selection"
    assert isinstance(captured.get("allowed_playbooks"), list)
    assert isinstance(captured.get("banned_playbooks"), list)
    assert str(captured.get("decision_summary") or "").strip()


def test_m31_runtime_entry_integrates_shadow_commander_into_commander_decision():
    captured: Dict[str, Any] = {}

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        captured.update(dict(state.get("commander_decision") or {}))
        state["path"] = "integrated_chain"
        state["runtime_status"] = "ok"
        return state

    out = run_commander_runtime(
        {
            "runtime_mode": "integrated_chain",
            "runtime_phase": "session",
            "portfolio_snapshot": {"positions": [{"symbol": "005930"}], "cash": 1000},
            "monitor": {"open_position_count": 1, "buy_blocked_open_position": True},
            "monitor_output": {"selected_symbol": "005930", "intent_side": "NOOP", "entry_exit_reason": "buy_blocked_open_position"},
            "selected": {"symbol": "005930", "score_total": 0.81},
            "commander_shadow_runtime": {
                "strategist_executed": False,
                "llm_called_by_strategist": False,
                "used_cached_strategist": False,
                "market_changed": False,
                "repeated_same_context": True,
                "monitor_decision": "NOOP",
                "executor_action": "",
                "executor_status": "",
                "prior_context": {"selected_symbol": "005930", "playbook": "pullback", "market_regime": "neutral"},
            },
        },
        integrated_runner=integrated_runner,
    )

    assert out["path"] == "integrated_chain"
    assert captured["command_intent"] == "OBSERVE_ONLY"
    assert captured["strategist_invocation"] == "SKIP"
    assert captured["llm_policy"] == "SKIP"
    assert captured["no_trade_reason_code"] == "POSITION_ALREADY_OPEN"
    assert captured["shadow_used"] is True
    assert captured["source_priority"][0] == "shadow_commander"
    assert captured["strategist_fallback_used"] is False
    assert isinstance(captured.get("observations"), dict)


def test_m31_runtime_entry_marks_strategist_fallback_when_shadow_and_runtime_lack_regime():
    captured: Dict[str, Any] = {}

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        captured.update(dict(state.get("commander_decision") or {}))
        state["path"] = "integrated_chain"
        state["runtime_status"] = "ok"
        return state

    run_commander_runtime(
        {
            "runtime_mode": "integrated_chain",
            "runtime_phase": "session",
            "strategist_output": {"market_regime": "risk_off"},
        },
        integrated_runner=integrated_runner,
    )

    assert captured["market_regime"] == "risk_off"
    assert captured["strategist_fallback_used"] is True
    assert "market_regime" in list(captured.get("source_refs", {}).get("strategist_fallback_fields") or [])


def test_m21_runtime_mode_resolution_precedence(monkeypatch):
    monkeypatch.setenv("COMMANDER_RUNTIME_MODE", "decision_packet")
    monkeypatch.setenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "true")

    # explicit beats state/env
    assert resolve_runtime_mode({"runtime_mode": "decision_packet"}, mode="graph_spine") == "graph_spine"
    # state beats env
    assert resolve_runtime_mode({"runtime_mode": "graph_spine"}) == "graph_spine"
    # env used when state missing
    assert resolve_runtime_mode({}) == "decision_packet"
    # invalid values fall back to graph_spine
    assert resolve_runtime_mode({"runtime_mode": "invalid"}) == "graph_spine"


def test_m21_runtime_phase_resolution_precedence(monkeypatch):
    monkeypatch.setenv("COMMANDER_RUNTIME_PHASE", "preopen")

    assert resolve_runtime_phase({"runtime_phase": "closeout"}, phase="session") == "session"
    assert resolve_runtime_phase({"runtime_phase": "closeout"}) == "closeout"
    assert resolve_runtime_phase({}) == "preopen"
    assert resolve_runtime_phase({"runtime_phase": "invalid"}) == "session"


def test_m21_runtime_entry_uses_env_mode_when_state_missing(monkeypatch):
    called = {"graph": 0, "decide": 0, "execute": 0}
    monkeypatch.setenv("COMMANDER_RUNTIME_MODE", "decision_packet")
    monkeypatch.setenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", "true")

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        state["path"] = "decision_packet"
        return state

    out = run_commander_runtime({}, graph_runner=graph_runner, decide=decide, execute=execute)
    assert out["path"] == "decision_packet"
    assert called == {"graph": 0, "decide": 1, "execute": 1}


def test_m21_runtime_mode_guard_blocks_decision_packet_without_activation(monkeypatch):
    monkeypatch.setenv("COMMANDER_RUNTIME_MODE", "decision_packet")
    monkeypatch.delenv("COMMANDER_RUNTIME_ALLOW_DECISION_PACKET", raising=False)

    assert resolve_runtime_mode({"runtime_mode": "decision_packet"}) == "graph_spine"
    assert resolve_runtime_mode({}) == "graph_spine"


def test_m21_runtime_transition_cancel_short_circuits_run():
    called = {"graph": 0, "decide": 0, "execute": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        return state

    out = run_commander_runtime(
        {"runtime_control": "cancel"},
        graph_runner=graph_runner,
        decide=decide,
        execute=execute,
    )

    assert out["runtime_status"] == "cancelled"
    assert out["runtime_transition"] == "cancel"
    assert called == {"graph": 0, "decide": 0, "execute": 0}


def test_m21_runtime_transition_pause_short_circuits_run():
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    out = run_commander_runtime({"runtime_control": "pause"}, graph_runner=graph_runner)

    assert out["runtime_status"] == "paused"
    assert out["runtime_transition"] == "pause"
    assert out["runtime_plan"]["mode"] == "graph_spine"
    assert called["graph"] == 0


def test_m21_runtime_transition_retry_marks_state_and_continues():
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        state["path"] = "graph_spine"
        return state

    out = run_commander_runtime(
        {"runtime_control": "retry", "runtime_retry_count": "2"},
        graph_runner=graph_runner,
    )

    assert out["runtime_status"] == "retrying"
    assert out["runtime_transition"] == "retry"
    assert out["runtime_retry_count"] == 3


def test_m21_hydrate_strategist_output_cache_normalizes_legacy_decision_policy():
    state = {
        "persisted_state": {
            "strategist_output_cache": {
                "output": {
                    "strategy_policy": {
                        "decision_policy": {
                            "use_strategy_v1_engine": True,
                            "allow_score_override": True,
                            "score_override_scope": "llm_only",
                            "strategy_v1_name": "regime_momentum_v1",
                            "buy_threshold": 0.1,
                            "news_buy_threshold": 0.2,
                        }
                    }
                },
                "generated_epoch": 123,
                "source": "legacy_cache",
            }
        }
    }

    out = _hydrate_strategist_output_cache(state)
    decision_policy = (
        (((out.get("strategist_output") or {}).get("strategy_policy") or {}).get("decision_policy") or {})
        if isinstance(out.get("strategist_output"), dict)
        else {}
    )

    assert decision_policy["use_strategy_v1_engine"] is False
    assert decision_policy["allow_score_override"] is False
    assert decision_policy["score_override_scope"] == "disabled"
    assert decision_policy["strategy_v1_name"] == ""
    assert decision_policy["strategy_variant_hint"] == "unified_ai_strategist"
    assert "buy_threshold" not in decision_policy
    assert "news_buy_threshold" not in decision_policy


class _FakeEventLogger:
    def __init__(self) -> None:
        self.rows: list[Dict[str, Any]] = []

    def log(
        self,
        *,
        run_id: str,
        stage: str,
        event: str,
        payload: Dict[str, Any],
        ts: str | None = None,
    ) -> Dict[str, Any]:
        row = {
            "run_id": run_id,
            "stage": stage,
            "event": event,
            "payload": payload,
            "ts": ts,
        }
        self.rows.append(row)
        return row


def test_m21_runtime_emits_route_and_end_events():
    logger = _FakeEventLogger()

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["path"] = "graph_spine"
        return state

    out = run_commander_runtime({"event_logger": logger}, graph_runner=graph_runner)

    router_rows = [r for r in logger.rows if r.get("stage") == "commander_router"]
    assert [r["event"] for r in router_rows][:3] == ["route", "route_selected", "end"]
    assert router_rows[-1]["event"] == "shadow_assessment"
    assert router_rows[0]["payload"]["mode"] == "graph_spine"
    assert router_rows[0]["payload"]["phase"] == "session"
    assert router_rows[2]["payload"]["path"] == "graph_spine"
    assert out.get("run_id")


def test_m21_runtime_emits_transition_for_pause_control():
    logger = _FakeEventLogger()
    called = {"graph": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    out = run_commander_runtime(
        {"runtime_control": "pause", "event_logger": logger},
        graph_runner=graph_runner,
    )

    router_rows = [r for r in logger.rows if r.get("stage") == "commander_router"]
    assert [r["event"] for r in router_rows][:4] == ["route", "route_selected", "transition", "end"]
    assert router_rows[-1]["event"] == "shadow_assessment"
    assert router_rows[2]["payload"]["transition"] == "pause"
    assert router_rows[2]["payload"]["status"] == "paused"
    assert router_rows[3]["payload"]["path"] is None
    assert called["graph"] == 0
    assert out["runtime_status"] == "paused"


def test_m21_runtime_preopen_phase_short_circuits_to_preopen_runner():
    called = {"graph": 0, "integrated": 0, "preopen": 0, "closeout": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["integrated"] += 1
        return state

    def preopen_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["preopen"] += 1
        state["path"] = "preopen_strategist"
        state["runtime_status"] = "preopen_ready"
        state["strategist_output"] = {"playbook": "defensive"}
        return state

    def closeout_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["closeout"] += 1
        return state

    out = run_commander_runtime(
        {"runtime_mode": "integrated_chain", "runtime_phase": "preopen"},
        graph_runner=graph_runner,
        integrated_runner=integrated_runner,
        preopen_runner=preopen_runner,
        closeout_runner=closeout_runner,
    )

    assert out["path"] == "preopen_strategist"
    assert out["runtime_status"] == "preopen_ready"
    assert out["runtime_plan"]["phase"] == "preopen"


def test_m21_integrated_chain_blocks_when_strategist_llm_is_required_but_failed(monkeypatch):
    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1_000_000, "positions": [], "open_positions": 0}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        state["risk_context"] = {"open_positions": 0}
        return state

    def fake_strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategist_output"] = {
            "llm_frame_blocked": True,
            "llm_frame_blocked_reason": "strategist_llm_failed",
        }
        state["strategist_blocked"] = True
        state["strategist_blocked_reason"] = "strategist_llm_failed"
        state["strategist_llm"] = {"blocked": True, "blocked_reason": "strategist_llm_failed"}
        return state

    def fail_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        raise AssertionError("scanner should not run when strategist is blocked")

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist_node)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fail_scanner)

    out = _run_integrated_chain({"run_id": "run-1"}, execute_fn=lambda state: state)

    assert out["runtime_status"] == "blocked"
    assert out["path"] == "integrated_chain_strategist_blocked"
    assert out["decision_reason"] == "strategist_llm_failed"


def test_m21_runtime_closeout_phase_short_circuits_to_closeout_runner():
    called = {"graph": 0, "decide": 0, "execute": 0, "closeout": 0}

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["graph"] += 1
        return state

    def decide(state: Dict[str, Any]) -> Dict[str, Any]:
        called["decide"] += 1
        return state

    def execute(state: Dict[str, Any]) -> Dict[str, Any]:
        called["execute"] += 1
        return state

    def closeout_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        called["closeout"] += 1
        state["path"] = "closeout_idle"
        state["runtime_status"] = "closeout_ready"
        return state

    out = run_commander_runtime(
        {"runtime_mode": "decision_packet", "runtime_phase": "closeout"},
        graph_runner=graph_runner,
        decide=decide,
        execute=execute,
        closeout_runner=closeout_runner,
    )

    assert out["path"] == "closeout_idle"
    assert out["runtime_status"] == "closeout_ready"
    assert out["runtime_plan"]["phase"] == "closeout"
    assert out["runtime_plan"]["agents"] == ["commander_router"]
    assert called == {"graph": 0, "decide": 0, "execute": 0, "closeout": 1}


def test_m31_integrated_chain_hydrates_portfolio_and_updates_execution_state(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {"cash": 1000.0, "positions": []}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        state["risk_context"] = {"open_positions": 0}
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        state["selected"] = {"symbol": "AAA"}
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = [{"symbol": "AAA", "side": "BUY", "qty": 1}]
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "approve"
        return state

    def fake_update_state_after_execution(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("update_state_after_execution")
        state["persisted_state"] = {"last_execution_ok": True}
        return state

    def fake_execute(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("execute")
        state["execution"] = {
            "allowed": True,
            "ok": True,
            "order": {"action": "BUY", "symbol": "AAA", "qty": 1},
            "payload": {"mode": "real"},
        }
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)
    monkeypatch.setattr(
        "graphs.nodes.update_state_after_execution.update_state_after_execution",
        fake_update_state_after_execution,
    )

    out = _run_integrated_chain({}, execute_fn=fake_execute)

    assert out["path"] == "integrated_chain"
    assert out["persisted_state"]["last_execution_ok"] is True
    assert isinstance(out.get("snapshots"), dict)
    assert out["snapshots"]["portfolio"] == {"cash": 1000.0, "positions": []}
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
        "execute",
        "update_state_after_execution",
    ]


def test_m31_integrated_chain_preflight_blocks_before_strategist_when_reader_error(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 0.0,
            "positions": [],
            "_health": {
                "reader_ok": False,
                "reader_error": "account_api_500",
            },
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        return state

    def fake_execute(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("execute")
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)

    out = _run_integrated_chain({}, execute_fn=fake_execute)

    assert out["path"] == "portfolio_preflight_guard"
    assert out["runtime_status"] == "preflight_blocked"
    assert out["portfolio_preflight"]["blocked"] is True
    assert out["portfolio_preflight"]["reason"] == "portfolio_snapshot_reader_error"
    assert out["execution"]["allowed"] is False
    assert calls == ["build_portfolio_snapshot"]


def test_m21_runtime_preopen_phase_preflight_blocks_before_strategist(monkeypatch):
    calls: list[str] = []
    logger = _FakeEventLogger()

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000000.0,
            "positions": [],
            "_health": {
                "reader_ok": True,
                "positions_mismatch_detected": True,
                "reconciliation_applied": False,
                "positions_source": "persisted_mock_positions",
                "reconciliation_status": "persisted_fallback",
            },
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)

    out = run_commander_runtime(
        {"runtime_mode": "integrated_chain", "runtime_phase": "preopen", "event_logger": logger},
    )

    assert out["path"] == "portfolio_preflight_guard"
    assert out["runtime_status"] == "preflight_blocked"
    assert out["portfolio_preflight"]["reason"] == "portfolio_snapshot_positions_mismatch_unresolved"
    assert calls == ["build_portfolio_snapshot"]

    end_rows = [r for r in logger.rows if r.get("stage") == "commander_router" and r.get("event") == "end"]
    assert len(end_rows) == 1
    assert end_rows[0]["payload"]["path"] == "portfolio_preflight_guard"
    assert end_rows[0]["payload"]["portfolio_preflight"]["blocked"] is True


def test_m21_preopen_phase_persists_strategist_output_cache(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["now_epoch"] = 1000
        state["strategist_output"] = {"playbook": "defensive", "monitor_guidance": "defensive_exit"}
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)

    out = _run_preopen_phase({"persisted_state": {}})

    cache = (out.get("persisted_state") or {}).get("strategist_output_cache") or {}
    assert out["path"] == "preopen_strategist"
    assert (cache.get("output") or {}).get("playbook") == "defensive"
    assert cache.get("generated_epoch") == 1000
    assert cache.get("source") == "strategist_node"
    assert calls == ["build_portfolio_snapshot", "build_risk_context", "strategist"]


def test_m31_graph_spine_preflight_blocks_before_graph_runner_when_enabled(monkeypatch):
    calls: list[str] = []
    logger = _FakeEventLogger()

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 0.0,
            "positions": [],
            "_health": {
                "reader_ok": False,
                "reader_error": "account_api_500",
            },
        }
        return state

    def graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("graph_runner")
        state["path"] = "graph_spine"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)

    out = run_commander_runtime(
        {
            "enable_graph_spine_portfolio_preflight": True,
            "event_logger": logger,
        },
        mode="graph_spine",
        graph_runner=graph_runner,
    )

    assert out["path"] == "portfolio_preflight_guard"
    assert out["runtime_status"] == "preflight_blocked"
    assert out["portfolio_preflight"]["reason"] == "portfolio_snapshot_reader_error"
    assert calls == ["build_portfolio_snapshot"]

    end_rows = [r for r in logger.rows if r.get("stage") == "commander_router" and r.get("event") == "end"]
    assert len(end_rows) == 1
    assert end_rows[0]["payload"]["path"] == "portfolio_preflight_guard"
    assert end_rows[0]["payload"]["portfolio_preflight"]["blocked"] is True


def test_m31_integrated_chain_triggers_intraday_trade_artifacts_after_success(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = [{"side": "BUY", "symbol": "005930", "qty": 1, "price": 70000}]
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "approve"
        return state

    def fake_execute(state: Dict[str, Any]) -> Dict[str, Any]:
        state["execution"] = {
            "ok": True,
            "allowed": True,
            "order": {"action": "BUY", "symbol": "005930", "qty": 1},
            "payload": {"mode": "real"},
        }
        return state

    def fake_update_state_after_execution(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_generate_intraday_trade_artifacts(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(str((state.get("execution") or {}).get("order", {}).get("symbol") or ""))
        return {"ok": True, "status": "generated", "trade_id": "TRD_1"}

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)
    monkeypatch.setattr("graphs.nodes.update_state_after_execution.update_state_after_execution", fake_update_state_after_execution)
    monkeypatch.setattr("libs.reporting.intraday_trade_reports.generate_intraday_trade_artifacts", fake_generate_intraday_trade_artifacts)

    out = _run_integrated_chain({}, execute_fn=fake_execute)

    assert calls == ["005930"]
    assert out["intraday_trade_report"]["trade_id"] == "TRD_1"


def test_m31_integrated_chain_uses_monitor_only_fast_path_when_holding(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [{"symbol": "322000", "qty": 1, "avg_price": 100.0}],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        state["decision"] = "hold"
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    def fake_execute(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("execute")
        return state

    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {"applied_policy": {"commander": {"route": {"monitor_only_when_holding": True}}}},
        execute_fn=fake_execute,
    )

    assert out["path"] == "integrated_chain_monitor_only"
    assert out["runtime_fast_path"]["reason"] == "holding_position_monitor_only"
    assert out["commander_decision"]["reporter_feedback_mode"] == "disabled"
    assert out["commander_decision"]["reporter_feedback_mode_source"] == "commander_applied_policy"
    assert out["commander_decision"]["reporter_feedback_mode_reason"] == "monitor_only_route"
    assert ((out.get("applied_policy") or {}).get("strategist") or {}).get("reporter_feedback_mode") == "disabled"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_monitor_only_hydrates_held_symbols_before_monitor(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [{"symbol": "322000", "qty": 1, "avg_price": 100.0}],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_hydrate_monitor_symbol_features(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("hydrate_monitor_symbol_features")
        state["monitor_feature_hydration"] = {
            "applied": True,
            "symbol_count": 1,
            "symbols": ["322000"],
        }
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        assert (state.get("selected") or {}).get("symbol") == "322000"
        assert bool((state.get("selected") or {}).get("_monitor_synthetic_selected")) is True
        assert (state.get("monitor_feature_hydration") or {}).get("symbols") == ["322000"]
        state["intents"] = []
        state["decision"] = "hold"
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {"applied_policy": {"commander": {"route": {"monitor_only_when_holding": True}}}},
        execute_fn=lambda state: state,
    )

    assert out["path"] == "integrated_chain_monitor_only"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "hydrate_monitor_symbol_features",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_monitor_only_uses_position_strategy_context_when_cache_missing(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [{"symbol": "322000", "qty": 1, "avg_price": 100.0}],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_hydrate_monitor_symbol_features(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("hydrate_monitor_symbol_features")
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        strategist_output = state.get("strategist_output") or {}
        assert strategist_output.get("playbook") == "defensive"
        assert strategist_output.get("monitor_guidance") == "defensive_exit"
        meta = state.get("strategist_output_cache_meta") or {}
        assert meta.get("source") == "buy_execution"
        assert meta.get("symbol") == "322000"
        state["intents"] = []
        state["decision"] = "hold"
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "applied_policy": {"commander": {"route": {"monitor_only_when_holding": True}}},
            "persisted_state": {
                "position_strategy_context": {
                    "322000": {
                        "output": {"playbook": "defensive", "monitor_guidance": "defensive_exit"},
                        "generated_epoch": 950,
                        "source": "buy_execution",
                    }
                }
            }
        },
        execute_fn=lambda state: state,
    )

    assert out["path"] == "integrated_chain_monitor_only"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "hydrate_monitor_symbol_features",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_reuses_cached_strategist_when_flat(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "defensive"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "180")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "defensive", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 950,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain_cached_frame"
    assert out["runtime_fast_path"]["reason"] == "commander_skip_cached_strategist"
    assert out["runtime_fast_path"]["source"] == "commander_decision"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_refreshes_strategist_before_buy_when_flat_cache_is_near_entry(monkeypatch):
    calls: list[str] = []
    logged: list[Dict[str, Any]] = []
    strategist_decisions: list[Dict[str, Any]] = []

    class _Logger:
        def log(self, **kwargs: Any) -> None:
            logged.append(dict(kwargs))

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        strategist_decisions.append(dict(state.get("commander_decision") or {}))
        state["strategist_output"] = {"playbook": "fresh_entry_frame", "monitor_guidance": "tight_confirm"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "fresh_entry_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "run_id": "run-prebuy-refresh-flat",
            "event_logger": _Logger(),
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "monitor_output": {
                "selected_symbol": "000660",
                "intent_side": "NOOP",
                "entry_became_ready_this_cycle": True,
                "entry_transition_readiness_score": 0.92,
                "entry_exit_reason": "pullback_below_vwap_reclaim_not_ready",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "cached_frame", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 700,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert (out.get("commander_shadow_runtime") or {}).get("pre_buy_refresh_requested") is True
    assert (out.get("commander_shadow_runtime") or {}).get("pre_buy_refresh_reason") == "became_ready_this_cycle"
    assert strategist_decisions
    assert strategist_decisions[0]["strategist_invocation"] == "RUN_REFRESH"
    assert strategist_decisions[0]["llm_policy"] == "allow_context_refresh"
    assert strategist_decisions[0]["strategist_refresh_requested"] is True
    assert strategist_decisions[0]["strategist_refresh_reason"] == "became_ready_this_cycle"
    assert strategist_decisions[0]["source_priority"][0] == "commander_refresh_heuristic"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]
    assert any(
        str(row.get("stage") or "") == "commander_router"
        and str(row.get("event") or "") == "pre_buy_refresh"
        for row in logged
    )


def test_m31_integrated_chain_refreshes_when_selected_symbol_is_outside_cached_frame(monkeypatch):
    calls: list[str] = []
    strategist_decisions: list[Dict[str, Any]] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        strategist_decisions.append(dict(state.get("commander_decision") or {}))
        state["strategist_output"] = {"playbook": "fresh_entry_frame", "monitor_guidance": "tight_confirm"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "fresh_entry_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "run_id": "run-prebuy-refresh-frame-gap",
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "monitor_output": {
                "selected_symbol": "034020",
                "intent_side": "NOOP",
                "entry_exit_reason": "pullback_not_mature",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {
                        "playbook": "cached_frame",
                        "monitor_guidance": "defensive_exit",
                        "candidate_symbols_hint": ["005930", "000660"],
                    },
                    "generated_epoch": 700,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert strategist_decisions
    assert strategist_decisions[0]["strategist_invocation"] == "RUN_REFRESH"
    assert strategist_decisions[0]["strategist_refresh_requested"] is True
    assert strategist_decisions[0]["strategist_refresh_reason"] == "selected_symbol_outside_cached_frame"
    assert strategist_decisions[0]["strategist_refresh_context"]["selected_symbol"] == "034020"
    assert strategist_decisions[0]["strategist_refresh_context"]["selected_symbol_in_cached_frame"] is False
    assert strategist_decisions[0]["strategist_refresh_context"]["cached_candidate_hints"] == ["005930", "000660"]
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_refreshes_when_market_regime_shifted_since_cache(monkeypatch):
    calls: list[str] = []
    strategist_decisions: list[Dict[str, Any]] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        strategist_decisions.append(dict(state.get("commander_decision") or {}))
        state["strategist_output"] = {"playbook": "fresh_entry_frame", "monitor_guidance": "tight_confirm"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "run_id": "run-prebuy-refresh-regime-shift",
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "market_regime": "risk_on",
            "monitor_output": {
                "selected_symbol": "005930",
                "intent_side": "NOOP",
                "entry_exit_reason": "entry_wait",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {
                        "playbook": "cached_frame",
                        "market_regime": "risk_off",
                        "candidate_symbols_hint": ["005930", "000660"],
                    },
                    "generated_epoch": 700,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert strategist_decisions
    assert strategist_decisions[0]["strategist_invocation"] == "RUN_REFRESH"
    assert strategist_decisions[0]["strategist_refresh_reason"] == "market_regime_shifted_since_cache"
    assert strategist_decisions[0]["strategist_refresh_context"]["current_market_regime"] == "risk_on"
    assert strategist_decisions[0]["strategist_refresh_context"]["cached_market_regime"] == "risk_off"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_refreshes_when_news_query_targets_drift(monkeypatch):
    calls: list[str] = []
    strategist_decisions: list[Dict[str, Any]] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        strategist_decisions.append(dict(state.get("commander_decision") or {}))
        state["strategist_output"] = {"playbook": "fresh_entry_frame", "monitor_guidance": "tight_confirm"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "run_id": "run-prebuy-refresh-news-drift",
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "news_query_targets": ["semiconductor", "memory", "ai server"],
            "monitor_output": {
                "selected_symbol": "005930",
                "intent_side": "NOOP",
                "entry_exit_reason": "entry_wait",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {
                        "playbook": "cached_frame",
                        "market_regime": "neutral",
                        "candidate_symbols_hint": ["005930", "000660"],
                        "news_query_targets": ["semiconductor", "memory"],
                    },
                    "generated_epoch": 700,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert strategist_decisions
    assert strategist_decisions[0]["strategist_invocation"] == "RUN_REFRESH"
    assert strategist_decisions[0]["strategist_refresh_reason"] == "news_query_target_drift"
    assert strategist_decisions[0]["strategist_refresh_context"]["current_news_query_targets"] == [
        "semiconductor",
        "memory",
        "ai server",
    ]
    assert strategist_decisions[0]["strategist_refresh_context"]["cached_news_query_targets"] == [
        "semiconductor",
        "memory",
    ]
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_commander_prefers_cached_strategist_when_frame_is_reusable(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "cached_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "run_id": "run-commander-cache-preferred",
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "monitor_output": {
                "selected_symbol": "005930",
                "intent_side": "NOOP",
                "entry_exit_reason": "entry_wait",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {
                        "playbook": "cached_frame",
                        "market_regime": "neutral",
                        "candidate_symbols_hint": ["005930", "000660"],
                    },
                    "generated_epoch": 950,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain_cached_frame"
    assert out["runtime_fast_path"]["reason"] == "commander_skip_cached_strategist"
    assert out["runtime_fast_path"]["source"] == "commander_decision"
    assert (out.get("commander_decision") or {}).get("strategist_invocation") == "SKIP"
    assert (out.get("commander_decision") or {}).get("llm_policy") in {"prefer_cached_context", "SKIP"}
    assert (out.get("commander_decision") or {}).get("strategist_cache_preferred") is True
    assert (out.get("commander_decision") or {}).get("strategist_cache_preference_reason") == "commander_preferred_cached_strategist"
    assert (out.get("commander_decision") or {}).get("source_priority")[0] == "commander_cache_reuse"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_runs_fresh_strategist_when_flat_cache_exists_but_default_reuse_is_disabled(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_build_commander_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN",
            "llm_policy": "ALLOW",
            "decision_summary": "fresh strategist allowed",
            "source_priority": ["runtime_observation", "strategist_fallback"],
            "shadow_used": False,
            "strategist_fallback_used": False,
        }

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "fresh_entry_frame"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "fresh_entry_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "180")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._build_commander_decision", fake_build_commander_decision)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "now_epoch": 1000,
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "cached_frame", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 950,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_reuses_cache_when_commander_explicitly_says_skip(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_build_commander_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "SKIP",
            "llm_policy": "SKIP",
            "decision_summary": "wait for confirmation",
            "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            "shadow_used": True,
            "strategist_fallback_used": False,
        }

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "fresh_entry_frame"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "cached_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "180")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._build_commander_decision", fake_build_commander_decision)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "now_epoch": 1000,
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "cached_frame", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 950,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain_cached_frame"
    assert out["runtime_fast_path"]["reason"] == "commander_skip_cached_strategist"
    assert out["runtime_fast_path"]["source"] == "commander_decision"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_respects_commander_refresh_request_over_cache_reuse(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_build_commander_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN_REFRESH",
            "llm_policy": "allow_context_refresh",
            "decision_summary": "refresh strategist context before building a new entry frame",
            "source_priority": ["commander_refresh_heuristic", "shadow_commander"],
            "shadow_used": True,
            "strategist_fallback_used": False,
            "strategist_refresh_requested": True,
            "strategist_refresh_reason": "transition_readiness_threshold",
            "strategist_refresh_context": {
                "selected_symbol": "000660",
                "cache_age_sec": 300,
                "transition_readiness_score": 0.87,
                "refresh_signal": "transition_readiness_threshold",
            },
        }

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "fresh_entry_frame"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "fresh_entry_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._build_commander_decision", fake_build_commander_decision)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "now_epoch": 1000,
            "monitor_output": {
                "selected_symbol": "000660",
                "intent_side": "NOOP",
                "entry_transition_readiness_score": 0.87,
                "entry_exit_reason": "breakout_not_ready",
            },
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "cached_frame", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 700,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert (out.get("commander_shadow_runtime") or {}).get("pre_buy_refresh_requested") is True
    assert (out.get("commander_shadow_runtime") or {}).get("pre_buy_refresh_reason") == "transition_readiness_threshold"
    assert (out.get("commander_shadow_runtime") or {}).get("used_cached_strategist") is False
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_reuses_cache_for_ten_minutes_by_default_when_commander_skip(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_build_commander_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "SKIP",
            "llm_policy": "SKIP",
            "decision_summary": "wait for confirmation",
            "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            "shadow_used": True,
            "strategist_fallback_used": False,
        }

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "fresh_entry_frame"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        assert (state.get("strategist_output") or {}).get("playbook") == "cached_frame"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.delenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", raising=False)
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._build_commander_decision", fake_build_commander_decision)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "now_epoch": 1000,
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "cached_frame", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 650,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain_cached_frame"
    assert out["runtime_fast_path"]["reason"] == "commander_skip_cached_strategist"
    assert out["runtime_fast_path"]["reuse_sec"] == 600
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_confirms_applied_policy_from_strategist_before_scanner_and_monitor(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_build_commander_decision(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN",
            "llm_policy": "ALLOW",
            "decision_summary": "fresh strategist allowed",
            "source_priority": ["runtime_observation", "strategist_fallback"],
            "shadow_used": False,
            "strategist_fallback_used": False,
        }

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {
            "playbook": "pullback",
            "monitor_entry_policy": {
                "timeframe_minutes": 1,
                "breakout_lookback": 5,
                "volume_lookback": 5,
                "volume_ratio_min": 0.72,
                "min_extended_from_vwap_pct": -0.05,
                "max_extended_from_vwap_pct": 0.13,
                "pullback_min_pct": 0.01,
                "pullback_max_pct": 0.07,
                "reclaim_tolerance_pct": 0.001,
                "breakout_buffer_pct": 0.0,
                "intent_cooldown_sec": 60,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            },
            "policy_source": "strategist",
            "policy_validation_status": "ok",
            "policy_fallback_used": False,
            "policy_fallback_reason": "",
            "strategy_policy": {
                "market_policy": {},
                "scanner_policy": {},
                "monitor_policy": {},
                "decision_policy": {},
            },
        }
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        commander_meta = state.get("commander_applied_policy_meta") or {}
        assert commander_meta.get("policy_source") == "strategist"
        assert commander_meta.get("policy_validation_status") == "ok"
        assert commander_meta.get("policy_fallback_used") is False
        commander_decision = state.get("commander_decision") or {}
        assert commander_decision.get("applied_policy", {}).get("volume_ratio_min") == 0.72
        assert commander_decision.get("applied_policy", {}).get("threshold_policy", {}).get("volume_ratio_min") == 0.72
        assert commander_decision.get("applied_policy", {}).get("interpretation_policy", {}).get("entry_style") == "pullback"
        assert "support_holding=holding" in list(
            (commander_decision.get("applied_policy", {}).get("interpretation_policy", {}) or {}).get("preferred_checks") or []
        )
        assert "structure_hh_hl=broken" in list(
            (commander_decision.get("applied_policy", {}).get("interpretation_policy", {}) or {}).get("blockers") or []
        )
        monitor_policy = ((state.get("strategy_policy") or {}).get("monitor_policy") or {})
        assert monitor_policy.get("policy_source") == "strategist"
        assert monitor_policy.get("applied_policy", {}).get("pullback_min_pct") == 0.01
        assert monitor_policy.get("applied_policy", {}).get("interpretation_policy", {}).get("entry_style") == "pullback"
        assert (((state.get("applied_policy") or {}).get("strategist") or {}).get("reporter_feedback_mode")) == "auto"
        assert (((state.get("applied_policy") or {}).get("strategist") or {}).get("reporter_feedback_mode_source")) == "commander_applied_policy"
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        assert state.get("commander_applied_policy", {}).get("volume_ratio_min") == 0.72
        assert state.get("commander_applied_policy", {}).get("threshold_policy", {}).get("volume_ratio_min") == 0.72
        assert state.get("commander_applied_policy", {}).get("interpretation_policy", {}).get("entry_style") == "pullback"
        assert "support_holding=holding" in list(
            (state.get("commander_applied_policy", {}).get("interpretation_policy", {}) or {}).get("preferred_checks") or []
        )
        assert state.get("commander_applied_policy_meta", {}).get("policy_source") == "strategist"
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({"now_epoch": 1000}, execute_fn=lambda s: s)

    assert out["path"] == "integrated_chain"
    assert out["commander_decision"]["policy_source"] == "strategist"
    assert out["commander_decision"]["policy_validation_status"] == "ok"
    assert out["commander_decision"]["policy_fallback_used"] is False
    assert out["commander_decision"]["applied_policy"]["threshold_policy"]["volume_ratio_min"] == 0.72
    assert out["commander_decision"]["applied_policy"]["interpretation_policy"]["entry_style"] == "pullback"
    assert out["commander_decision"]["reporter_feedback_mode"] == "auto"
    assert out["commander_decision"]["reporter_feedback_mode_source"] == "commander_applied_policy"
    assert out["commander_decision"]["reporter_feedback_mode_reason"] == "full_cycle_route"
    assert "support_holding=holding" in list(
        (out["commander_decision"]["applied_policy"]["interpretation_policy"] or {}).get("preferred_checks") or []
    )
    assert out["commander_decision"]["applied_policy_source_chain"] == [
        "strategist",
        "validation",
        "commander_confirmed",
    ]
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_hydrates_held_symbols_before_monitor_after_scanner(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [{"symbol": "322000", "qty": 1, "avg_price": 100.0}],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "defensive"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_hydrate_monitor_symbol_features(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("hydrate_monitor_symbol_features")
        state["monitor_feature_hydration"] = {
            "applied": True,
            "symbol_count": 1,
            "symbols": ["322000"],
        }
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        assert (state.get("monitor_feature_hydration") or {}).get("symbols") == ["322000"]
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {"applied_policy": {"commander": {"route": {"monitor_only_when_holding": False}}}},
        execute_fn=lambda state: state,
    )

    assert out["path"] == "integrated_chain"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "hydrate_monitor_symbol_features",
        "monitor",
        "decision",
    ]


def test_m31_integrated_chain_runs_strategist_when_flat_cache_is_stale(monkeypatch):
    calls: list[str] = []

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_portfolio_snapshot")
        state["portfolio_snapshot"] = {
            "cash": 1000.0,
            "positions": [],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("build_risk_context")
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("strategist")
        state["strategist_output"] = {"playbook": "defensive"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("scanner")
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("monitor")
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "60")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
            "applied_policy": {"commander": {"route": {"cached_strategist_when_flat": True}}},
            "now_epoch": 1000,
            "persisted_state": {
                "strategist_output_cache": {
                    "output": {"playbook": "defensive", "monitor_guidance": "defensive_exit"},
                    "generated_epoch": 800,
                }
            },
        },
        execute_fn=lambda s: s,
    )

    assert out["path"] == "integrated_chain"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]
