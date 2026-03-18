from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import _run_integrated_chain, resolve_runtime_mode, resolve_runtime_phase, run_commander_runtime
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
    assert out["path"] == "graph_spine"
    assert called["graph"] == 1


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
    assert [r["event"] for r in router_rows] == ["route", "end"]
    assert router_rows[0]["payload"]["mode"] == "graph_spine"
    assert router_rows[0]["payload"]["phase"] == "session"
    assert router_rows[1]["payload"]["path"] == "graph_spine"
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
    assert [r["event"] for r in router_rows] == ["route", "transition", "end"]
    assert router_rows[1]["payload"]["transition"] == "pause"
    assert router_rows[1]["payload"]["status"] == "paused"
    assert router_rows[2]["payload"]["path"] is None
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
    assert out["runtime_plan"]["agents"] == ["commander_router", "strategist"]
    assert called == {"graph": 0, "integrated": 0, "preopen": 1, "closeout": 0}


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

    monkeypatch.setenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=fake_execute)

    assert out["path"] == "integrated_chain_monitor_only"
    assert out["runtime_fast_path"]["reason"] == "holding_position_monitor_only"
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

    monkeypatch.setenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)

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

    monkeypatch.setenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "true")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
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

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED", "true")
    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "180")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
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
    assert out["runtime_fast_path"]["reason"] == "flat_position_cached_strategist"
    assert calls == [
        "build_portfolio_snapshot",
        "build_risk_context",
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

    monkeypatch.setenv("COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED", "false")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", fake_hydrate_monitor_symbol_features)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)

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

    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED", "true")
    monkeypatch.setenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "60")
    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain(
        {
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
