from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import run_commander_runtime


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
        {"runtime_mode": "decision_packet"},
        graph_runner=graph_runner,
        decide=decide,
        execute=execute,
    )

    assert out["path"] == "decision_packet"
    assert out["execution"]["allowed"] is True
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

